"""
Local decision layer: between the regex fast path and Claude, offline, no AI service.

  utterance → sentence embedding (ONNX on the CPU, ~2-5 ms) → nearest example phrase in
  intents.json (cosine) → act locally only if
      best score ≥ threshold (Settings → JARVIS, default 0.70)
      and it beats the best *other* intent by ≥ GAP
      and that intent is a stark tool (not "chat" / "claude-only")
      and the request contains the intent's anchor words, if it has any ("must"), and none of
      its excluded ones ("must_not")
      and every required slot is filled (rapidfuzz against live lists, numbers / durations
      with the fast path's parser)
  otherwise the request goes to Claude exactly as before.

A decision is a list of fast-path steps ({"tool", "args", "say"}), so it runs through
Jarvis.run_steps: same confirmations, dry-run and spoken result as the fast path.

Near misses (up to ASK_BAND under an intent's threshold, a clear winner, every slot filled, not blocked,
nothing about deleting) get "Did you mean …, sir?" instead of going to Claude (Settings → JARVIS → ROUTER → Ask when unsure). Each intent's threshold is Settings → Local
confidence plus an offset calibrated from logged outcomes.

Learning (core/router_learn.py): Claude's single-tool answers, his corrections and "yes" answers become
candidate examples; they go live only through the promotion gate (the router eval at 0 wrong actions + his
own outcome history). Corrections, undo, reworded repeats, the kill switch and declined confirmations demote
learned examples and raise thresholds. Learned data lives in ~/.local/share/jarvis/learned_intents.json
(untracked), never in intents.json. Every decision is logged to jarvis_db.router_log.

Needs onnxruntime, tokenizers, huggingface_hub (already in the venv for Kokoro / whisper) and rapidfuzz.
The model files download from Hugging Face on the first start, then load offline.

Email, calendar, docs, assignment and grade requests never get here as actions: the fast
path's INTEGRATION_INTENT guard sends them to Claude first, and their intents in
intents.json are kind "claude-only", which this module can only pass through.
"""
import hashlib
import json
import random
import re
import threading
import time
from dataclasses import dataclass, field

import numpy as np

from . import config as C
from . import fastpath
from . import router_learn as L

import stark_actions as A  # noqa: E402  (mcp/ is on sys.path; see jarvis.py)

INTENTS_FILE = C.JARVIS_DIR / "intents.json"
# Chosen with tools/eval_router.py on this machine (Core Ultra 9 185H, 2026-10-27): all-MiniLM-L6-v2
# fp32 made no wrong local actions at any threshold ≥ 0.65 (≈3 ms); bge-small scores everything high,
# so only the gap separates intents, and it still acted wrongly below 0.90 (≈5 ms). q8 = fp32 here.
MODEL = "minilm"
MODELS = {   # name → (HF repo, ONNX file, pooling)
    "minilm": ("sentence-transformers/all-MiniLM-L6-v2", "onnx/model.onnx", "mean"),
    "minilm-q8": ("sentence-transformers/all-MiniLM-L6-v2", "onnx/model_quint8_avx2.onnx", "mean"),
    "bge-small": ("BAAI/bge-small-en-v1.5", "onnx/model.onnx", "cls"),
}
THREADS = 2                 # more threads barely help a 10-token sentence; onnxruntime spins otherwise
GAP = 0.05
MAX_WORDS = 16              # longer than this is a conversation, not a command
LEARN_CAP = L.LEARN_CAP
LEARN_MAX_WORDS = L.LEARN_MAX_WORDS

NEGATION = re.compile(r"\b(?:don't|dont|do not|never|not|stop (?:\w+ing))\b")
# never "Did you mean …?" when the words are about removing something (the closest intent is never that)
DESTRUCTIVE = re.compile(r"\b(?:delete|remove|erase|clear|uninstall|wipe|trash|discard|kill|close|shut)\b")
COMPOUND = re.compile(r"\s*(?:,|\band then\b|\bthen\b|\band\b|\balso\b)\s+")


# ── the embedding model ──
class Embedder:
    def __init__(self, name=MODEL):
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer
        repo, onnx_file, self.pool = MODELS[name]
        self.name = name

        def fetch(f):
            try:
                return hf_hub_download(repo, f, local_files_only=True)    # offline after the first run
            except Exception:
                return hf_hub_download(repo, f)
        self.tok = Tokenizer.from_file(fetch("tokenizer.json"))
        self.tok.no_padding()        # all-MiniLM's tokenizer.json pads to 128: 10x slower for nothing
        self.tok.enable_truncation(64)
        o = ort.SessionOptions()
        o.intra_op_num_threads, o.inter_op_num_threads = THREADS, 1
        o.add_session_config_entry("session.intra_op.allow_spinning", "0")
        o.log_severity_level = 3
        self.sess = ort.InferenceSession(fetch(onnx_file), o, providers=["CPUExecutionProvider"])
        self.inputs = {i.name for i in self.sess.get_inputs()}

    def __call__(self, texts):
        """→ (n, d) float32, L2-normalised."""
        out = []
        for t in texts:
            e = self.tok.encode(t)
            ids = np.array([e.ids], dtype=np.int64)
            feed = {"input_ids": ids, "attention_mask": np.ones_like(ids)}
            if "token_type_ids" in self.inputs:
                feed["token_type_ids"] = np.zeros_like(ids)
            h = self.sess.run(None, feed)[0][0]
            v = h.mean(0) if self.pool == "mean" else h[0]
            out.append(v / (np.linalg.norm(v) or 1.0))
        return np.asarray(out, dtype=np.float32)


# ── intents.json (tracked, hand-written) + what the router learned (untracked, core/router_learn.py) ──
def load_intents():
    return json.loads(INTENTS_FILE.read_text())


def save_intents(data):
    tmp = INTENTS_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(INTENTS_FILE)


def learned_file():
    return L.path()


def load_learned():
    """{intent: [text]} of the ACTIVE learned examples (what the router uses)."""
    return {k: [t for _, t in v] for k, v in L.active(L.read()).items()}


def migrate_learned():
    """Move any "learned" lists still inside intents.json (where they lived before 2026-10-28) into the
    learned store, as candidates the router re-checks. Returns how many moved."""
    data = load_intents()
    if not any("learned" in it for it in data["intents"].values()):
        return 0
    moved = 0
    with L.edit() as store:
        for name, it in data["intents"].items():
            for ex in it.pop("learned", None) or []:
                t = norm_text(ex)
                if not L.find(store, name, t):
                    L.add_record(store, name, t, "legacy", confirms=1)
                    moved += 1
    save_intents(data)
    return moved


LEAD = re.compile(r"^(?:hey )?friday\s+")      # "Friday, pause" = "Jarvis, pause": one store for both personas


def norm_text(s):
    return LEAD.sub("", " ".join(fastpath.norm(s).split()))


def clean(text):
    """The words the router compares: no lead-in, no wake word, no "please" / "sir" tail."""
    return norm_text(fastpath.TRAILER.sub("", fastpath.FILLER.sub("", norm_text(text))))


# ── slots ──
VERBS = set("""open launch start run fire up bring pull show load boot get me the my a an please can could you would
will jarvis hey sir app application program for go to switch set put change make it now""".split())
NUMWORDS = set(fastpath.UNITS) - {"a", "an"} | set(fastpath.TENS)


def _spans(words, max_n=4):
    for n in range(min(max_n, len(words)), 0, -1):
        for i in range(len(words) - n + 1):
            yield " ".join(words[i:i + n])


def _fuzzy(t, choices, key=lambda c: c, cutoff=86, strip=VERBS):
    """Best choice for any 1-4 word span of t (rapidfuzz ratio ≥ cutoff); longer choices win ties."""
    from rapidfuzz import fuzz
    words = [w for w in t.split() if w not in strip]
    keyed = [(key(c), c) for c in choices if c]
    best, best_s = None, 0.0
    for span in _spans(words):
        ks = key(span)
        for k, c in keyed:
            if len(k) < 2:
                continue
            s = fuzz.ratio(ks, k)
            if s >= cutoff and (s, len(k)) > (best_s, len(key(best)) if best else 0):
                best, best_s = c, s
    return best


def _numbers(t, homophones=False):
    """Numbers said in t, in order: digits, number words ("thirty five"), homophones only if asked."""
    words, out, i = t.replace("%", " ").split(), [], 0
    while i < len(words):
        w = words[i]
        two = " ".join(words[i:i + 2])
        if len(words) > i + 1 and words[i] in fastpath.TENS and words[i + 1] in fastpath.UNITS and words[i + 1] not in ("a", "an"):
            out.append(fastpath.to_num(two))
            i += 2
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", w) or w in NUMWORDS or (homophones and w in fastpath.HOMOPHONES):
            out.append(fastpath.to_num(w))
        i += 1
    return [n for n in out if n is not None]


def _duration(t):
    words = t.split()
    for n in range(len(words), 0, -1):
        for i in range(len(words) - n + 1):
            m = fastpath.duration_minutes(" ".join(words[i:i + n]))
            if m:
                return m
    return None


def _launcher_names():
    try:
        apps = json.loads(C.HUD_SETTINGS.read_text()).get("launcherApps") or []
        return [a["name"].lower() for a in apps if a.get("name")]
    except (OSError, ValueError):
        return []


def slot_app(t):
    names = set(A.ALIASES) | set(A.apps()) | {n for n in _launcher_names() if A.find_app(n)[0]}
    return _fuzzy(t, names, key=lambda s: s.replace(" ", ""))


def slot_theme(t):
    return _fuzzy(t, A.theme_presets() or ["STARK", "MARK III", "VIBRANIUM", "MATRIX", "ARCTIC", "SOLAR"],
                  key=A._preset_key, strip=VERBS | {"theme", "preset", "colors", "colours", "hud", "look", "mode"})


def slot_percent(t):
    n = _numbers(t)
    if not n:
        if re.search(r"\b(?:half|halfway)\b", t):
            return 50
        if re.search(r"\b(?:max|maximum|full)\b", t):
            return 100
        return None
    v = n[-1]
    return int(v) if 0 <= v <= 100 else None


def slot_workspace(t):
    n = _numbers(t) or _numbers(t.split("workspace")[-1] if "workspace" in t else t, homophones=True)
    return int(n[-1]) if n and 1 <= n[-1] <= 10 and float(n[-1]).is_integer() else None


def slot_minutes(t):
    m = _duration(t)
    return round(m, 3) if m and 0.1 <= m <= 1440 else None


def slot_timer_label(t):
    m = re.search(r"\b(?:a |an |the |my )?([a-z]+) timer\b", t)
    if m and m.group(1) not in {"a", "an", "the", "my", "set", "start", "quick", "new", "another", "minute", "second",
                                "hour", "countdown", "kitchen", "simple", "timer"} | NUMWORDS:
        return m.group(1)
    m = re.search(r"\bfor (?:the |my )?([a-z]+(?: [a-z]+)?)$", t)
    if m and not _duration(m.group(1)) and not _numbers(m.group(1)):
        return m.group(1)
    return ""


def slot_screen(t):
    for span in _spans(t.split(), 3):
        role = A.norm_screen(span)
        if role:                         # "" = here; only an explicit screen counts
            return span
    return ""


def slot_role_screen(t):
    """set_screen_role's screen: tv | laptop | monitor 2 | main | diag; "" = the one in use."""
    for span in _spans(t.split(), 3):
        tok = A.norm_role_screen(span)
        if tok and tok != "current":
            return tok
    return ""


def slot_screen_role(t):
    for span in _spans(t.split(), 3):
        r = A.norm_role(span)
        if r:
            return r
    return ""


def slot_position(t):
    for span in _spans(t.split(), 3):
        if A.norm_position(span):
            return A.norm_position(span)
    return ""


def slot_tz(t):
    m = re.search(r"\b(?:in|for|of) ([a-z ]+?)(?: time| on .*| at .*)?$", t)
    if m and A.city_tz(m.group(1)):
        return m.group(1)
    return _fuzzy(t, list(A.CITY_TZ), cutoff=90, strip=VERBS | {"clock", "time", "widget"}) or ""


def slot_place(t):
    m = re.search(r"\b(?:in|for|at) ([a-z][a-z ]+?)(?: today| tonight| tomorrow| right now| now| this week)?$", t)
    when = {"here", "home", "today", "tonight", "tomorrow", "now", "the morning", "the afternoon", "the evening",
            "the weekend", "this week", "tomorrow morning", "tomorrow afternoon", "tomorrow night"}
    return m.group(1) if m and m.group(1) not in when else ""


def slot_onoff(t):
    if re.search(r"\b(?:toggle|flip|switch them)\b", t):
        return "toggle"
    if re.search(r"\b(?:off|kill|cut|out|shut)\b", t):
        return "off"
    if re.search(r"\b(?:on|back)\b", t):
        return "on"
    return None


def slot_light_mode(t):
    for mode, pat in (("music", r"music|sync|beat|react"), ("theme", r"theme|match(?:ing)? the (?:hud|colors?)"),
                      ("auto", r"auto(?:matic)?|normal|default")):
        if re.search(rf"\b(?:{pat})\b", t):
            return mode
    return None


def slot_mute(t):
    if re.search(r"\bun ?mute\b|\bsound back\b|\bturn the sound (?:back )?on\b", t):
        return "unmute"
    if re.search(r"\bmute\b|\bsilence\b|\bsound off\b|\bkill the sound\b", t):
        return "mute"
    return None


def slot_vpn(t):
    if re.search(r"\b(?:off|disconnect|drop|kill|stop|disable|turn off|shut)\b", t):
        return "disconnect"
    if re.search(r"\bproton\b", t):
        return "connect_proton"
    if re.search(r"\b(?:school|waterloo|uw|campus|university|uni)\b", t):
        return "open_school_login"
    return None


def slot_power(t):
    for action, pat in (("reboot", r"reboot|restart"), ("shutdown", r"shut ?down|power (?:off|down)|turn off (?:the |my )?(?:computer|pc|laptop|system|machine)"),
                        ("suspend", r"suspend|sleep|hibernate"), ("logout", r"log ?(?:me )?out|sign ?(?:me )?out")):
        if re.search(rf"\b(?:{pat})\b", t):
            return action
    return None


def slot_uwcs_host(t):
    m = re.search(r"\b(?:0{0,2}([1-9]|1[0-2])|00(\d))\b", t)
    if m:
        h = (m.group(1) or m.group(2)).zfill(3)
        return h if h in A.uwcs_hosts() else None
    return ""


AUDIO_DEV = (r"head ?phones?|head ?sets?|ear ?buds?|ear ?phones?|air ?pods?|google home|nest|"
             r"(?:room |bluetooth |laptop |built in |computer |monitor |tv )?speakers?|laptop|built in|usb|tv|television|hdmi|bluetooth")


def slot_audio_out(t):
    m = re.search(rf"\b({AUDIO_DEV})\b", t)
    return m.group(1) if m else None


def slot_audio_in(t):
    m = re.search(r"\b(head ?sets?|head ?phones?|laptop|built in|internal|usb|bluetooth|ear ?buds?)\b", t)
    return m.group(1) if m else None


def slot_shuffle(t):
    return "shuffle_off" if re.search(r"\b(?:off|stop|no more|disable|don't)\b", t) else "shuffle_on"


SLOTS = {"app": slot_app, "theme": slot_theme, "percent": slot_percent, "workspace": slot_workspace,
         "minutes": slot_minutes, "timer_label": slot_timer_label, "screen": slot_screen, "position": slot_position,
         "tz": slot_tz, "place": slot_place, "onoff": slot_onoff, "light_mode": slot_light_mode, "mute": slot_mute,
         "vpn": slot_vpn, "power": slot_power, "uwcs_host": slot_uwcs_host,
         "role_screen": slot_role_screen, "screen_role": slot_screen_role,
         "audio_out": slot_audio_out, "audio_in": slot_audio_in, "shuffle": slot_shuffle}
# Slot types whose values are a closed set (used to map Claude's calls back to an intent)
DOMAINS = {"screen_role": set(A.SCREEN_ROLES), "onoff": {"on", "off"}, "light_mode": {"music", "theme", "auto"}, "mute": {"mute", "unmute"},
           "vpn": {"disconnect", "connect_proton", "open_school_login"},
           "power": {"suspend", "shutdown", "reboot", "logout"}, "shuffle": {"shuffle_on", "shuffle_off"}}


def fill_slots(spec, t):
    """spec {arg: "type" | "type?"} → (args, missing names). "?" = optional."""
    args, missing = {}, []
    for name, typ in (spec or {}).items():
        optional = typ.endswith("?")
        v = SLOTS[typ.rstrip("?")](t)
        if v in (None, "toggle") or (v == "" and not optional):
            if not optional:
                missing.append(name)
            continue
        if v != "":
            args[name] = v
    return args, missing


# ── spoken replies ──
def _fmt(template, args):
    vals = {k: (A.match_preset(str(v)) or str(v).upper() if k == "preset" else
                str(v).title() if isinstance(v, str) else f"{v:g}" if isinstance(v, float) else v) for k, v in args.items()}
    try:
        return template.format(**vals)
    except (KeyError, IndexError, ValueError):
        return template.split("{")[0].strip() or "Done, sir."


RESULT_SAY = {   # "@name" in intents.json: replies built from the tool's result
    "now_playing": fastpath._now_playing, "vpn_status": fastpath._vpn_status, "timers": fastpath._timers,
    "battery": fastpath._battery, "cpu_temp": fastpath._cpu_temp, "weather_now": fastpath._weather_now,
    "weather_tomorrow": fastpath._weather_tomorrow,
    "system": lambda r: (f"CPU at {r.get('cpu_percent', 0):g}%, memory at {r.get('ram_percent', 0):g}%"
                         + (f", battery {r['battery']['percent']}%" if r.get("battery") else "") + ". All nominal, sir."),
    "opened": lambda r: "Right away, sir." if "is up" not in str(r.get("result", "")) else "It's already up, sir.",
    "voice_volume": lambda r: (random.choice(["Is this better, sir? I'm at {p} percent.", "{p} percent, sir. How's this?",
                                              "Speaking at {p} percent, sir."]).format(p=r["percent"])
                               if r.get("percent") != r.get("was") or r.get("dry_run") else
                               f"I'm already at {r['percent']} percent, sir."),
    "say": lambda r: r.get("say") or "Done, sir.",           # Spotify / DJ results carry their own line
    "audio_out": lambda r: A.audio_said(r),
    "audio_in": lambda r: A.audio_said(r, mic=True),
    "widgets": lambda r: (f"{len(r.get('widgets') or [])} widget{'s' if len(r.get('widgets') or []) != 1 else ''} up, sir."
                          if r.get("widgets") else "No widgets up, sir."),
}


def say_for(intent, args):
    say = intent.get("say") or ["Done, sir."]
    if isinstance(say, str) and say.startswith("@"):
        return RESULT_SAY[say[1:]]
    return _fmt(random.choice(say if isinstance(say, list) else [say]), args)


# ── "Did you mean …?" ──
DESCRIBE = {
    "open_app": "open {name}", "switch_workspace": "switch to workspace {n}", "set_theme": "switch the theme to {preset}",
    "lights.power": "turn the lights {action}", "lights.brightness": "set the lights to {value} percent",
    "lights.mode": "put the lights in {value} mode", "media.play": "play the music", "media.pause": "pause the music",
    "media.next": "skip to the next track", "media.previous": "go back a track", "media.volume_up": "turn the music up",
    "media.volume_down": "turn the music down", "media.set_volume": "set the music volume to {value} percent",
    "media.mute": "{action} the sound", "voice.volume_down": "speak more quietly", "voice.volume_up": "speak up",
    "voice.set_volume": "set my voice to {percent} percent", "what_is_playing": "tell you what's playing",
    "status.overview": "give you a system status", "status.battery": "check the battery",
    "status.temperature": "check the CPU temperature", "vpn.status": "check the VPN", "open_uwcs": "open the UW CS servers",
    "screenshot.region": "screenshot a region", "screenshot.screen": "screenshot this screen",
    "screenshot.window": "screenshot this window", "screenshot.annotate": "take a screenshot to annotate",
    "set_timer": "set a {minutes} minute timer", "list_reminders": "check your timers", "weather.now": "check the weather",
    "weather.tomorrow": "check tomorrow's weather", "widget.clock": "add a clock widget", "widget.stats": "add a stats widget",
    "widget.stopwatch": "start a stopwatch", "widget.media": "add a media widget", "widget.list": "list your widgets",
    "screen.role": "show {role} on that screen", "set_audio_output": "switch the sound to the {device}",
    "set_audio_input": "switch the microphone to the {device}", "spotify.like": "save this song to your library",
    "dj.start": "start DJ mode", "dj.stop": "stop DJ mode", "dj.more": "play more like this", "dj.less": "play less like this",
    "dj.keep": "keep this vibe going", "spotify.shuffle": "turn shuffle {action}",
}


def describe(name, args):
    vals = {}
    for k, v in args.items():
        if k == "preset":
            v = A.match_preset(str(v)) or str(v).upper()
        elif isinstance(v, float):
            v = f"{v:g}"
        vals[k] = str(v).replace("shuffle_", "").replace("_", " ")
    try:
        return DESCRIBE[name].format(**vals)
    except (KeyError, IndexError, ValueError):
        return name.replace(".", " ").replace("_", " ")


# ── decisions ──
@dataclass
class Decision:
    path: str                       # "local" | "ask" | "claude:<why>"
    intent: str = ""
    top3: list = field(default_factory=list)
    slots: dict = field(default_factory=dict)
    steps: list = None              # fast-path style steps when path is local / ask
    ms: float = 0.0
    score: float = 0.0              # the top intent's similarity
    threshold: float = 0.0          # that intent's threshold (Settings value + its calibrated offset)
    example: str = ""               # id of the learned example that matched ("" = a built-in one)
    text: str = ""                  # the words compared (clean())
    ask: str = ""                   # "Did you mean …, sir?" when path == "ask"

    def info(self):
        """What a later outcome needs to know about this decision."""
        return {"text": self.text, "intent": self.intent, "score": self.score, "example": self.example}


def _eval_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("jarvis_eval_router", C.JARVIS_DIR / "tools" / "eval_router.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


STOP = VERBS | {"to", "of", "in", "on", "is", "this", "that", "and", "with", "some", "what", "what's", "how", "how's",
                "i", "i'm", "me", "be", "do", "is", "are", "you", "your", "there", "here", "kind", "like", "just", "one"}


def content_words(t):
    return {w for w in t.split() if w not in STOP and len(w) > 1}


class LocalRouter:
    def __init__(self, cfg, model=MODEL, log=print, record=True, settle=False):
        """settle: tidy the learned store and re-check candidates now (the voice loop does it, in a thread);
        eval / CLI / tests leave the store alone."""
        self.cfg, self.log, self.record = cfg, log, record
        self.lock = threading.Lock()            # the vectors
        self.learn_lock = threading.Lock()      # one learning step at a time (each may run the gate)
        self.frozen = False                     # a shadow copy for the gate: never reloads
        self.emb = Embedder(model)
        self._load()
        if settle:
            self.settle()

    def _load(self):
        if migrate_learned():
            self.log("JARVIS: moved learned router examples to " + str(learned_file()))
        self.data = load_intents()
        self.store_mtime = L.mtime()
        self.store = L.read()
        act = L.active(self.store)
        labels, texts, ids = [], [], []
        for name, it in self.data["intents"].items():
            for ex in it.get("examples", []):
                labels.append(name)
                texts.append(norm_text(ex))
                ids.append("")
            for rid, ex in act.get(name, []):
                labels.append(name)
                texts.append(norm_text(ex))
                ids.append(rid)
        h = hashlib.sha1(("\n".join(f"{l}\t{t}" for l, t in zip(labels, texts)) + self.emb.name).encode()).hexdigest()[:16]
        cache = C.DATA_DIR / f"router-{self.emb.name}.npz"
        vecs = None
        try:
            z = np.load(cache)
            if str(z["hash"]) == h:
                vecs = z["vecs"]
        except (OSError, KeyError, ValueError):
            pass
        if vecs is None:
            # only embed what's new (a learned example adds one), reusing the vectors already in memory
            old = dict(zip(zip(self.labels, self.texts), self.vecs)) if hasattr(self, "vecs") else {}
            todo = [i for i, k in enumerate(zip(labels, texts)) if k not in old]
            new = dict(zip(todo, self.emb([texts[i] for i in todo]))) if todo else {}
            vecs = np.asarray([new[i] if i in new else old[k] for i, k in enumerate(zip(labels, texts))], dtype=np.float32)
            C.DATA_DIR.mkdir(parents=True, exist_ok=True)
            np.savez(cache, vecs=vecs, hash=np.array(h))
        self.labels, self.texts, self.ids, self.vecs = np.array(labels), texts, ids, vecs
        self.names = list(self.data["intents"])

    def _reload_if_changed(self):
        """Another process (`jarvis router forget`, the app, Settings) edited the learned store."""
        if not self.frozen and L.mtime() != self.store_mtime:
            with self.lock:
                self._load()

    def warm(self):
        self.emb(["warm up"])

    def scores(self, t, vec=None):
        """Best cosine per intent, highest first: [(intent, score, index of the example that scored it)]."""
        sims = self.vecs @ (self.emb([t])[0] if vec is None else vec)
        best = {}
        for i, (lab, s) in enumerate(zip(self.labels, sims)):
            if s > best.get(lab, (-1, 0))[0]:
                best[lab] = (float(s), i)
        return sorted(((k, s, i) for k, (s, i) in best.items()), key=lambda x: -x[1])

    def similarity(self, a, b):
        va, vb = self.emb([clean(a), clean(b)])
        return float(va @ vb)

    def threshold_for(self, name, base):
        off = float(self.store["offsets"].get(name, 0.0))
        if L.blocked(name, self.data["intents"].get(name)):
            off = max(off, 0.0)
        return round(base + off, 3)

    def decide(self, text, threshold=None):
        self._reload_if_changed()
        t0 = time.perf_counter()
        d = self._decide(text, threshold)
        d.ms = round((time.perf_counter() - t0) * 1000, 2)
        if self.record:
            threading.Thread(target=self._log, args=(text, d), daemon=True).start()
        return d

    def _log(self, text, d):
        try:
            import jarvis_db as db
            db.log_decision(text, d.path, d.intent, d.top3, d.slots, d.ms)
        except Exception as e:
            self.log(f"JARVIS: router log failed: {e}")

    def _decide(self, text, threshold):
        base = float(threshold if threshold is not None else self.cfg["jarvisRouterThreshold"])
        t = clean(text)
        if not t:
            return Decision("claude:empty")
        if fastpath.is_integration_intent(text):           # phase 2 rule, before anything else
            return Decision("claude:claude-only", intent="integration", text=t)
        with self.lock:
            ranked = self.scores(t)
        top3 = [[str(n), round(s, 3)] for n, s, _ in ranked[:3]]
        name, best, idx = ranked[0]
        # the runner-up only counts if it could act on this text at all: an intent whose anchors rule it
        # out ("set your volume" is never the music volume) can't make the winner ambiguous
        second = next((s for n, s, _ in ranked[1:] if self._eligible(self.data["intents"][n], t)), 0.0)
        intent = self.data["intents"][name]
        th = self.threshold_for(name, base)
        d = Decision("claude:?", intent=name, top3=top3, score=round(best, 4), threshold=th, example=self.ids[idx], text=t)
        kind = intent.get("kind", "tool")
        near, tight = best < th, best - second < GAP
        if kind == "claude-only":
            d.path = "claude:claude-only"
        elif kind == "chat":
            d.path = "claude:other"
        elif name in self.store["negatives"].get(t, ()):
            d.path = "claude:unlearned"                   # he corrected exactly these words before
        elif best < th - L.ASK_BAND or (near and not self._may_ask(name, t)):
            d.path = "claude:below-threshold"
        elif tight:                                       # two intents this close: a question would be a guess too
            d.path = "claude:small-gap"
        elif len(t.split()) > MAX_WORDS:
            d.path = "claude:long"
        elif NEGATION.search(t):
            d.path = "claude:negation"
        elif not self._eligible(intent, t):
            d.path = "claude:anchor"
        elif len([p for p in COMPOUND.split(t) if p.strip()]) > 1 and not intent.get("compound_ok"):
            d.path = "claude:compound"
        else:
            args, missing = fill_slots(intent.get("slots"), t)
            d.slots = args
            if missing:
                d.path = "claude:slots:" + ",".join(missing)
            else:
                full = dict(intent.get("args", {}), **args)
                d.steps = [fastpath.step(intent["tool"], say_for(intent, full), **full)]
                if near:                                  # a near miss: ask instead of guessing
                    d.path = "ask"
                    d.ask = f"Did you mean {describe(name, args)}, sir?"
                else:
                    d.path = "local"
        return d

    def _may_ask(self, name, t):
        return (bool(self.cfg["jarvisRouterAsk"]) and not L.blocked(name, self.data["intents"].get(name))
                and not DESTRUCTIVE.search(t))

    @staticmethod
    def _eligible(intent, t):
        if intent.get("kind", "tool") != "tool":
            return True                       # chat / claude-only always compete
        return not ((intent.get("must") and not re.search(intent["must"], t))
                    or (intent.get("must_not") and re.search(intent["must_not"], t)))

    # ── learning: evidence → candidate → gate → active ──
    def learn(self, text, tool, args, source="claude"):
        """`text` was handled by exactly one stark call tool(**args) (Claude's, or what a correction
        resolved to). Counts as one confirm for the one intent that covers it, if this router can pull the
        same arguments out of the words. → the intent, or None."""
        t = clean(text)
        if (not t or len(t.split()) > LEARN_MAX_WORDS or fastpath.is_integration_intent(text)
                or NEGATION.search(t) or len([p for p in COMPOUND.split(t) if p.strip()]) > 1):
            return None
        target = self._intent_for(tool, args, t)
        if not target or L.blocked(target, self.data["intents"][target]):
            return None
        return self.add_evidence(target, t, source, confirm=True)

    def add_evidence(self, target, t, source, confirm=False):
        """One more sighting of words t meaning intent target. → target if it's (now) known, else None."""
        it = self.data["intents"].get(target)
        if not it or L.blocked(target, it) or target in self.store["forgotten"].get(t, ()):
            return None
        with self.learn_lock:
            vec = self.emb([t])[0]
            with self.lock:
                mask = self.labels == target
                sims = np.where(mask, self.vecs @ vec, -1.0)
            j = int(np.argmax(sims))
            dup = sims[j] >= L.DUP_COS
            if dup and self.ids[j] == "":
                return target                             # a built-in example already says this
            with L.edit() as st:
                rec = st["examples"].get(self.ids[j]) if dup else L.find(st, target, t)
                if rec:
                    rec["seen"] += 1
                    rec["confirms"] += int(confirm)
                    rec["updated"] = time.time()
                else:
                    rec = L.add_record(st, target, t, source, confirms=int(confirm))
                rid, state = rec["id"], rec["state"]
            if state == "active":
                self._reload_if_changed()
                return target
            self.log(f'JARVIS: router candidate "{t}" → {target} ({source})')
            ok = self._try_promote(rid, vec)
        self._reload_if_changed()
        return target if ok else None

    def _supported(self, name, t):
        """Do the words themselves point at the intent? A filled required slot does; otherwise at least one
        content word must appear in its hand-written examples ("get it" → next track: no)."""
        it = self.data["intents"][name]
        spec = it.get("slots") or {}
        if any(not typ.endswith("?") for typ in spec.values()) and not fill_slots(spec, t)[1]:
            return True
        vocab = set()
        for ex in it.get("examples", []):
            vocab |= content_words(norm_text(ex))
        return bool(content_words(t) & vocab)

    def _check(self, rec, vec=None, force=False):
        """→ (ok, why). force (his approval) skips the word checks, never the gate."""
        name, t = rec["intent"], rec["text"]
        it = self.data["intents"].get(name)
        if not it:
            return False, "that intent is no longer in intents.json"
        if L.blocked(name, it):
            return False, "never learned for this intent"
        if NEGATION.search(t) or fastpath.is_integration_intent(t):
            return False, "negated or an email / calendar / docs request"
        if name in self.store["negatives"].get(t, ()) and not force:
            return False, "you corrected these words before"
        vec = self.emb([t])[0] if vec is None else vec
        if not force:
            if not self._supported(name, t):
                return False, f"its words don't point at {name}"
            own = float(np.max(np.where((self.labels == name) & np.array([i == "" for i in self.ids]), self.vecs @ vec, -1.0)))
            if own < L.MIN_OWN_SIM:
                return False, f"too unlike {name}'s examples ({own:.2f})"
        return self.gate(self._shadow(add=[(name, t, rec["id"], vec)]))

    def _try_promote(self, rid, vec=None):
        rec = L.read()["examples"].get(rid)
        if not rec or not L.ready(rec):
            return False
        ok, why = self._check(rec, vec)
        with L.edit() as st:
            r = st["examples"].get(rid)
            if not r:
                return False
            r["updated"] = time.time()
            if ok:
                r.update(state="active", promoted=time.time(), why="")
                L.event(st, "promoted", r, r["intent"], why)
            else:
                r.update(state="rejected", why=why)
                L.event(st, "rejected", r, r["intent"], why)
            L.tidy(st)
        self.log(f'JARVIS: router {"promoted" if ok else "rejected"} "{rec["text"]}" → {rec["intent"]}: {why}')
        return ok

    def approve(self, rid):
        """His approval from Settings / `jarvis router approve`: skips the evidence and word checks, never the gate."""
        rec = L.read()["examples"].get(str(rid))
        if not rec:
            return False, "no such id"
        if rec["state"] == "active":
            return True, f'"{rec["text"]}" → {rec["intent"]} is already active'
        with self.learn_lock:
            ok, why = self._check(rec, force=True)
            with L.edit() as st:
                r = st["examples"].get(rec["id"])
                if r:
                    if ok:
                        r.update(state="active", promoted=time.time(), neg=0, why="", updated=time.time())
                        r["confirms"] += 1
                        for k in (r["text"],):
                            st["negatives"][k] = [i for i in st["negatives"].get(k, []) if i != r["intent"]]
                    else:
                        r["why"] = why
                    L.event(st, "approved" if ok else "rejected", r, r["intent"], why if not ok else "approved by you")
        self._reload_if_changed()
        return ok, f'"{rec["text"]}" → {rec["intent"]}' + ("" if ok else f": {why}")

    def settle(self):
        """Startup: tidy, then re-check every candidate that has enough evidence (e.g. after the migration)."""
        with L.edit() as st:
            n = L.tidy(st)
        if n:
            self.log(f"JARVIS: router dropped {n} stale learned examples")
        with self.learn_lock:
            for rid, r in L.read()["examples"].items():
                if L.ready(r):
                    self._try_promote(rid)
        self._reload_if_changed()

    # ── the gate ──
    def _shadow(self, add=(), offsets=None):
        """A frozen copy with extra examples [(intent, text, id, vec)] and/or other offsets, for the gate."""
        import copy
        sh = copy.copy(self)
        sh.record, sh.frozen = False, True
        with self.lock:
            labels, texts, ids, vecs = list(self.labels), list(self.texts), list(self.ids), self.vecs
        if add:
            labels += [a[0] for a in add]
            texts += [a[1] for a in add]
            ids += [a[2] for a in add]
            vecs = np.vstack([vecs] + [np.asarray(a[3], dtype=np.float32)[None, :] for a in add])
        sh.labels, sh.texts, sh.ids, sh.vecs = np.array(labels), texts, ids, vecs
        sh.lock = threading.Lock()
        sh.store = dict(self.store)
        if offsets is not None:
            sh.store["offsets"] = offsets
        return sh

    def gate(self, shadow):
        """A change may go live only if the router eval still makes 0 wrong actions and none of his own
        logged outcomes gets worse than it is now (a corrected request acting again, a good one changing intent)."""
        base = float(self.cfg["jarvisRouterThreshold"])
        r = _eval_module().run(shadow, base)
        if r["wrong"]:
            return False, f"the router eval would make {r['wrong']} wrong action{'s' if r['wrong'] != 1 else ''}"
        try:
            import jarvis_db as db
            outs = db.router_outcomes(90)
        except Exception:
            outs = []
        seen = set()
        for o in reversed(outs):
            k = (o["request"], o["intent"], o["outcome"])
            if k in seen:
                continue
            seen.add(k)
            bad = self._worse(shadow._decide(o["request"], base), o)
            if bad and not self._worse(self._decide(o["request"], base), o):     # only what this change breaks
                return False, bad
        return True, "eval 0 wrong, your history unchanged"

    @staticmethod
    def _worse(d, o):
        """Why decision d goes against logged outcome o, or ""."""
        if d.path != "local":
            return ""
        if o["outcome"] in ("neg", "ask_no") and d.intent == o["intent"]:
            return f'"{o["request"]}" would act as {o["intent"]} again, which you corrected'
        if o["outcome"] in ("pos", "ask_yes") and d.intent != o["intent"]:
            return f'"{o["request"]}" would change from {o["intent"]} to {d.intent}'
        return ""

    # ── outcomes: what happened after a local action / a question ──
    def outcome(self, info, outcome, why=""):
        """info: Decision.info() (or the same keys). outcome: pos | neg | ask_yes | ask_no."""
        if not info or not info.get("intent") or not info.get("text"):
            return
        import jarvis_db as db
        db.log_outcome(info["text"], info["intent"], info.get("score") or 0.0, info.get("example", ""), outcome, why)
        name, t, rid = info["intent"], info["text"], info.get("example", "")
        with self.learn_lock:
            with L.edit() as st:
                r = st["examples"].get(rid) if rid else None
                if outcome == "neg":
                    if name not in st["negatives"].get(t, []):
                        st["negatives"].setdefault(t, []).append(name)
                    L.event(st, "corrected", r, name, f'{why}: "{t}"')
                    if r:
                        r["neg"] += 1
                        r["updated"] = time.time()
                        if r["neg"] >= 2 or r["state"] != "active":
                            L.event(st, "deleted", r, name, f"{r['neg']} corrections")
                            del st["examples"][rid]
                        else:
                            r["state"], r["why"] = "candidate", f"demoted: {why}"
                            L.event(st, "demoted", r, name, why)
                elif outcome in ("pos", "ask_yes") and r:
                    r["pos"] += 1
                    r["last_used"] = time.time()
            self._recalibrate(name)
        self._reload_if_changed()

    def _recalibrate(self, name):
        import jarvis_db as db
        base = float(self.cfg["jarvisRouterThreshold"])
        outs = [(o["score"], o["outcome"] in ("pos", "ask_yes")) for o in db.router_outcomes(90, name)]
        new = L.calibrate(outs, base, may_lower=not L.blocked(name, self.data["intents"].get(name)))
        cur = float(L.read()["offsets"].get(name, 0.0))
        if abs(new - cur) < 1e-9:
            return
        why = f"{base + cur:.2f} → {base + new:.2f} from {len(outs)} outcomes"
        if new < cur:                                   # lowering acts on more requests: gate it
            offs = dict(self.store["offsets"], **{name: new})
            ok, gwhy = self.gate(self._shadow(offsets=offs))
            if not ok:
                with L.edit() as st:
                    L.event(st, "kept", None, name, f"threshold stays {base + cur:.2f}: {gwhy}")
                return
        with L.edit() as st:
            st["offsets"][name] = round(new, 2)
            L.event(st, "threshold", None, name, why)
        self.log(f"JARVIS: router threshold {name} {why}")

    def known_intent(self, text):
        """The intent this exact phrasing is an example of, hand-written or learned (e.g. a "Panel or
        widget?" answer → "choice.panel"), or None."""
        t = clean(text)
        self._reload_if_changed()
        with self.lock:
            for name, it in self.data["intents"].items():
                if t in {norm_text(x) for x in it.get("examples", [])}:
                    return name
            for name, items in L.active(self.store).items():
                if t in {norm_text(x) for _, x in items}:
                    return name
            for pick, texts in self.store["choices"].items():
                if t in texts:
                    return f"choice.{pick}"
        return None

    def remember_choice(self, text, pick, tool, args):
        """Trevor answered "Panel or widget?" with pick (panel | widget) for `text`, which runs tool(**args).
        Evidence for that tool's intent when there is one; otherwise kept under choices[pick] (not embedded,
        only read by known_intent) so the same words don't ask again."""
        t = clean(text)
        if not t or self.known_intent(t) or self.learn(text, tool, args, source="choice"):
            return
        with L.edit() as st:
            if t not in st["choices"].setdefault(pick, []):
                st["choices"][pick] = (st["choices"][pick] + [t])[-LEARN_CAP:]
        self._reload_if_changed()
        self.log(f'JARVIS: remembered "{t}" → {pick}')

    def intent_for_call(self, text, tool, args):
        """Which intent a stark call tool(**args) for these words was (None if none / ambiguous)."""
        return self._intent_for(tool, args, clean(text))

    def _intent_for(self, tool, args, t):
        lower = lambda v: str(v).strip().lower()
        found = []
        for name, it in self.data["intents"].items():
            if it.get("tool") != tool or it.get("kind", "tool") != "tool":
                continue
            if not self._eligible(it, t):
                continue
            fixed = it.get("args", {})
            if any(lower(args.get(k)) != lower(v) for k, v in fixed.items()):
                continue
            spec = it.get("slots") or {}
            if any(typ.rstrip("?") in DOMAINS and k in args and lower(args[k]) not in DOMAINS[typ.rstrip("?")]
                   for k, typ in spec.items()):
                continue
            got, missing = fill_slots(spec, t)
            if missing:
                continue
            same = all(self._same(k, got.get(k), args.get(k)) for k, typ in spec.items() if not typ.endswith("?"))
            if same:
                found.append(name)
        return found[0] if len(found) == 1 else None

    @staticmethod
    def _same(k, mine, theirs):
        if mine is None or theirs is None:
            return False
        if k == "preset":
            return A._preset_key(str(mine)) == A._preset_key(str(theirs))
        if k == "name":
            return A.find_app(str(mine))[0] == A.find_app(str(theirs))[0]
        try:
            return abs(float(mine) - float(theirs)) < 1e-6
        except (TypeError, ValueError):
            return str(mine).strip().lower() == str(theirs).strip().lower()


# ── `jarvis intents …` (no model needed); learned examples: `jarvis router …` (core/router_learn.py) ──
def cli(argv):
    migrate_learned()
    data, store = load_intents(), load_learned()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        for name, it in data["intents"].items():
            n = len(store.get(name, []))
            print(f"{name:<24} {it.get('kind', 'tool'):<12} {len(it.get('examples', [])):>3} examples"
                  f"{'  + ' + str(n) + ' learned' if n else ''}{'  (never learned)' if L.blocked(name, it) else ''}")
        print(f"learned examples: {learned_file()} · jarvis router review")
        return 0
    if cmd == "log":
        import jarvis_db as db
        for r in reversed(db.recent_decisions(int(argv[1]) if len(argv) > 1 else 30)):
            top = " ".join(f"{n}:{s:.2f}" for n, s in json.loads(r["top3"]))
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(r['ts']))}  {r['path']:<26} {r['ms'] or 0:>6.1f} ms  "
                  f"{r['request'][:50]:<50}  {top}")
        return 0
    if cmd in ("review", "remove", "forget", "stats", "approve", "reset-learned"):
        return L.cli(["forget" if cmd == "remove" else cmd] + argv[1:])
    print("usage: jarvis intents [list | log [N]] · learned examples: jarvis router stats | review | approve ID | forget ID | reset-learned")
    return 2
