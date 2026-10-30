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

Self-learning: when a request falls through and Claude calls exactly one stark tool whose
arguments this module can also pull out of the transcript, the transcript becomes a new
learned example for that intent (deduplicated, capped). Learned examples live in
~/.local/share/jarvis/learned_intents.json (untracked), not in intents.json; both are
merged at load. `jarvis intents review` lists and removes them. Every decision is logged
to jarvis_db.router_log.

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
LEARN_CAP = 25              # learned examples kept per intent (oldest dropped)
LEARN_MAX_WORDS = 12

NEGATION = re.compile(r"\b(?:don't|dont|do not|never|not|stop (?:\w+ing))\b")
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


# ── intents.json (tracked, hand-written) + learned_intents.json (untracked, self-learned) ──
LEARNED_DOC = ("Router examples Jarvis learned from Claude's single-tool answers (core/router_local.py), "
               "merged with ~/.config/jarvis/intents.json at load. Review: jarvis intents review.")


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def load_intents():
    return json.loads(INTENTS_FILE.read_text())


def save_intents(data):
    _write_json(INTENTS_FILE, data)


def learned_file():
    return C.DATA_DIR / "learned_intents.json"       # looked up each time: tests point DATA_DIR elsewhere


def load_learned():
    """{intent: [examples]}"""
    try:
        return json.loads(learned_file().read_text()).get("learned", {})
    except (OSError, ValueError):
        return {}


def save_learned(learned):
    _write_json(learned_file(), {"_doc": LEARNED_DOC, "learned": {k: v for k, v in learned.items() if v}})


def migrate_learned():
    """Move any "learned" lists still inside intents.json (where they lived before 2026-10-28) into
    the untracked learned file. Returns how many examples moved; rewrites intents.json only if needed."""
    data = load_intents()
    if not any("learned" in it for it in data["intents"].values()):
        return 0
    learned, moved = load_learned(), 0
    for name, it in data["intents"].items():
        for ex in it.pop("learned", None) or []:
            if norm_text(ex) not in {norm_text(x) for x in learned.get(name, [])}:
                learned.setdefault(name, []).append(ex)
                moved += 1
    if moved:
        save_learned(learned)
    save_intents(data)
    return moved


def norm_text(s):
    return " ".join(fastpath.norm(s).split())


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


SLOTS = {"app": slot_app, "theme": slot_theme, "percent": slot_percent, "workspace": slot_workspace,
         "minutes": slot_minutes, "timer_label": slot_timer_label, "screen": slot_screen, "position": slot_position,
         "tz": slot_tz, "place": slot_place, "onoff": slot_onoff, "light_mode": slot_light_mode, "mute": slot_mute,
         "vpn": slot_vpn, "power": slot_power, "uwcs_host": slot_uwcs_host}
# Slot types whose values are a closed set (used to map Claude's calls back to an intent)
DOMAINS = {"onoff": {"on", "off"}, "light_mode": {"music", "theme", "auto"}, "mute": {"mute", "unmute"},
           "vpn": {"disconnect", "connect_proton", "open_school_login"},
           "power": {"suspend", "shutdown", "reboot", "logout"}}


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
    "widgets": lambda r: (f"{len(r.get('widgets') or [])} widget{'s' if len(r.get('widgets') or []) != 1 else ''} up, sir."
                          if r.get("widgets") else "No widgets up, sir."),
}


def say_for(intent, args):
    say = intent.get("say") or ["Done, sir."]
    if isinstance(say, str) and say.startswith("@"):
        return RESULT_SAY[say[1:]]
    return _fmt(random.choice(say if isinstance(say, list) else [say]), args)


# ── decisions ──
@dataclass
class Decision:
    path: str                       # "local" or "claude:<why>"
    intent: str = ""
    top3: list = field(default_factory=list)
    slots: dict = field(default_factory=dict)
    steps: list = None              # fast-path style steps when path == "local"
    ms: float = 0.0


class LocalRouter:
    def __init__(self, cfg, model=MODEL, log=print, record=True):
        self.cfg, self.log, self.record = cfg, log, record
        self.lock = threading.Lock()
        self.emb = Embedder(model)
        self._load()

    def _load(self):
        if migrate_learned():
            self.log("JARVIS: moved learned router examples to " + str(learned_file()))
        self.data = load_intents()
        self.learned = load_learned()
        labels, texts = [], []
        for name, it in self.data["intents"].items():
            for ex in it.get("examples", []) + self.learned.get(name, []):
                labels.append(name)
                texts.append(norm_text(ex))
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
        self.labels, self.texts, self.vecs = np.array(labels), texts, vecs
        self.names = list(self.data["intents"])

    def warm(self):
        self.emb(["warm up"])

    def scores(self, t):
        """Best cosine per intent, highest first: [(intent, score)]."""
        sims = self.vecs @ self.emb([t])[0]
        best = {}
        for lab, s in zip(self.labels, sims):
            if s > best.get(lab, -1):
                best[lab] = float(s)
        return sorted(best.items(), key=lambda kv: -kv[1])

    def decide(self, text, threshold=None):
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
        threshold = float(threshold if threshold is not None else self.cfg["jarvisRouterThreshold"])
        t = norm_text(fastpath.TRAILER.sub("", fastpath.FILLER.sub("", fastpath.norm(text))))
        if not t:
            return Decision("claude:empty")
        if fastpath.is_integration_intent(text):           # phase 2 rule, before anything else
            return Decision("claude:claude-only", intent="integration")
        with self.lock:
            ranked = self.scores(t)
        top3 = [[str(n), round(s, 3)] for n, s in ranked[:3]]
        name, best = ranked[0]
        # the runner-up only counts if it could act on this text at all: an intent whose anchors rule it
        # out ("set your volume" is never the music volume) can't make the winner ambiguous
        second = next((s for n, s in ranked[1:] if self._eligible(self.data["intents"][n], t)), 0.0)
        intent = self.data["intents"][name]
        d = Decision("claude:?", intent=name, top3=top3)
        kind = intent.get("kind", "tool")
        if kind == "claude-only":
            d.path = "claude:claude-only"
        elif kind == "chat":
            d.path = "claude:other"
        elif best < threshold:
            d.path = "claude:below-threshold"
        elif best - second < GAP:
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
                d.path = "local"
        return d

    @staticmethod
    def _eligible(intent, t):
        if intent.get("kind", "tool") != "tool":
            return True                       # chat / claude-only always compete
        return not ((intent.get("must") and not re.search(intent["must"], t))
                    or (intent.get("must_not") and re.search(intent["must_not"], t)))

    # ── self-learning ──
    def learn(self, text, tool, args):
        """Claude handled `text` with exactly one stark call tool(**args). Add it as an example of the
        one intent that matches, if this router can pull the same arguments out of the text."""
        t = norm_text(fastpath.TRAILER.sub("", fastpath.FILLER.sub("", fastpath.norm(text))))
        if (not t or len(t.split()) > LEARN_MAX_WORDS or fastpath.is_integration_intent(text)
                or NEGATION.search(t) or len([p for p in COMPOUND.split(t) if p.strip()]) > 1):
            return None
        target = self._intent_for(tool, args, t)
        if not target:
            return None
        with self.lock:
            learned = load_learned()
            known = {norm_text(x) for x in self.data["intents"][target].get("examples", []) + learned.get(target, [])}
            if t in known:
                return None
            learned[target] = (learned.get(target, []) + [t])[-LEARN_CAP:]
            save_learned(learned)
            self._load()
        self.log(f'JARVIS: learned "{t}" → {target}')
        return target

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


# ── `jarvis intents …` (no model needed) ──
def cli(argv):
    migrate_learned()
    data, store = load_intents(), load_learned()
    learned = [(name, i, ex) for name, exs in store.items() for i, ex in enumerate(exs)]
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        for name, it in data["intents"].items():
            n = len(store.get(name, []))
            print(f"{name:<24} {it.get('kind', 'tool'):<12} {len(it.get('examples', [])):>3} examples"
                  f"{'  + ' + str(n) + ' learned' if n else ''}")
        print(f"learned examples: {learned_file()}")
        return 0
    if cmd == "log":
        import jarvis_db as db
        for r in reversed(db.recent_decisions(int(argv[1]) if len(argv) > 1 else 30)):
            top = " ".join(f"{n}:{s:.2f}" for n, s in json.loads(r["top3"]))
            print(f"{time.strftime('%m-%d %H:%M', time.localtime(r['ts']))}  {r['path']:<26} {r['ms'] or 0:>6.1f} ms  "
                  f"{r['request'][:50]:<50}  {top}")
        return 0
    if cmd not in ("review", "remove"):
        print("usage: jarvis intents [list | log [N] | review | remove N…]")
        return 2
    if not learned:
        print("No learned examples yet.")
        return 0
    if cmd == "review":
        for n, (name, _, ex) in enumerate(learned, 1):
            print(f"{n:>3}  {name:<24} {ex}{'   (intent no longer in intents.json)' if name not in data['intents'] else ''}")
        import sys
        if not sys.stdin.isatty():
            return 0
        picks = input("Numbers to remove (space-separated, Enter = keep all): ").split()
    else:
        picks = argv[1:]
    try:
        drop = {learned[int(p) - 1][:2] for p in picks}
    except (ValueError, IndexError):
        print("Pick numbers from the list.")
        return 2
    save_learned({name: [ex for i, ex in enumerate(exs) if (name, i) not in drop] for name, exs in store.items()})
    print(f"Removed {len(drop)}.")
    return 0
