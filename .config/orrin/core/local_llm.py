"""
Orrin's local model tier: between the local router (core/router_local.py) and Claude.

  regex fast path → embedding router → LOCAL MODEL → Claude

The model: Qwen3.5-9B (Q4_K_M) in llama.cpp's llama-server on the Arc iGPU (Vulkan), as orrin-llm.service:
loopback only, API key in ~/.config/llama-server/api-key, model files in ~/.local/share/llama.cpp/models
(outside the repo). Picked 2026-11-15 from the stage-1 benchmark (~/.local/share/orrin/bench/results/
stage1-2026-11-15): no wrong argument values on 24 real requests, first action ~4 s (Claude Haiku with tools:
4.2 s median). Thinking off for voice, on for typed requests (the ORRIN app, Super+J), which can wait.

What it may do. Only requests the router passed on for being unsure (below its threshold, a tie, a missing
slot, an anchor), never:
  - email / calendar / docs / assignment / grade / tracker requests or anything that sends (Claude only, as before),
  - two-part requests ("restart the song and raise the volume"): Claude. "Open Steam on workspace one" is one
    call (open_app's workspace argument), not two,
  - "check / look at / see if / monitor …": Claude, until the router has learned those words,
  - anything over 20 words.
It gets the allowlisted alchemos tools (devices, HUD, music, screens; no window control, nothing that asks
first or that the router never learns: router_learn.BLOCKED_TOOLS) plus `escalate`, and must answer with exactly
one call, decoded against the tool's JSON schema (llama-server's grammar). Then Orrin checks the arguments
itself (the app exists, the theme exists, the audio device resolves, the place is in places.json, numbers in
range). Anything else (no call, a question back, escalate, two calls, a bad argument, a timeout, the server not
warm) → Claude, as if this tier weren't there. Nothing is executed before that check, so there's no partial
work to hand over: the escalation reason is logged.

It never writes what Orrin says: the call is mapped to its intent in intents.json and spoken with that intent's
fixed line (or the line built from the tool's result: weather, now playing, status…), which core/persona.py
then says in SELENE's manner when she's answering. Tools without an intent use the "say" line their result
carries, else "Done, sir."

Trust, per intent (stored with the router's learning, core/router_learn.py "llm"):
  shadow   the local model proposes on every eligible request but Claude still acts; the two are compared
           (same tool, same arguments after checking) and logged (orrin_db.llm_log).
           orrinLocalPromote agreements in a row (default 5) → the intent is earned ("live").
  live     with `orrin brain shadow off`, earned intents run locally. Orrin waits for the proposal only when the
           router's top guesses include an earned intent; otherwise Claude runs at once and the proposal is
           compared in the background. A correction, undo, reworded repeat, the opposite command, the kill switch,
           a declined confirmation or a failed call sends the intent back to shadow with its streak at 0.
`orrin brain shadow on` (the default) keeps everything in shadow: nothing local runs, intents still earn trust.

CLI (dispatched from orrin.py before the heavy imports):
  orrin brain status                  mode, service state, earned intents
  orrin brain shadow on | off | report
  orrin brain bench [--think both|on|off] [--reps N] [--cases 0,3,7]
                                      rerun the benchmark (~/.local/share/orrin/bench)
"""
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from . import config as C
from . import router_learn as L

UNIT = "orrin-llm.service"
PORT = 8181
URL = f"http://127.0.0.1:{PORT}"
KEY_FILE = C.HOME / ".config/llama-server/api-key"
BENCH_DIR = C.DATA_DIR / "bench"
PLACES_FILE = C.ORRIN_DIR / "places.json"
SLOT_DIR = C.HOME / ".cache/orrin-llm/slots"     # orrin-llm.service --slot-save-path: the saved prompt cache

MAX_WORDS = 20
BUDGET = {"voice": 8.0, "typed": 60.0}         # seconds Orrin waits for a proposal it means to act on
MAX_TOKENS = {False: 300, True: 2048}           # thinking off / on
THINK = {"voice": False, "typed": True}

# What the local model may call. Anything in router_learn.BLOCKED_TOOLS is dropped on top of this.
ALLOW_TOOLS = ("open_app", "switch_workspace", "set_theme", "lights", "media", "what_is_playing", "system_status",
               "screenshot", "set_timer", "list_reminders", "widget_add", "widget_list", "set_screen_role",
               "orrin_volume", "set_audio_output", "set_audio_input", "spotify_play", "spotify_queue",
               "spotify_player", "spotify_like", "spotify_now_playing", "dj_start", "dj_adjust", "dj_control",
               "weather")
# Claude's lookups before acting (it lists the devices, then switches): not the action itself
LOOKUPS = {"list_audio_devices", "list_windows", "widget_list", "spotify_devices", "watch_list", "list_reminders",
           "spotify_now_playing", "what_is_playing", "system_status"}
FREE_TEXT = {"mood", "query", "text", "label", "note", "tz"}   # compared loosely
IGNORED = {"label", "note"}                                     # optional extras that don't change what happens
# the router's "not sure" paths; claude-only / negation / compound / long / unlearned / other never come here
ELIGIBLE = ("claude:below-threshold", "claude:small-gap", "claude:anchor", "claude:slots:")

ESCALATE = {"type": "function", "function": {
    "name": "escalate",
    "description": "Hand this request to the bigger assistant. Use it when no tool here fits, the request needs email, "
                   "calendar, documents, assignments or grades, reading or clicking inside a window, more than one "
                   "action, or when you are not sure what he means.",
    "parameters": {"type": "object", "properties": {"reason": {"type": "string"}}, "required": ["reason"]}}}

SYSTEM = """You are the quick local half of ORRIN, the voice assistant of Trevor's Linux desktop, AlchemOS. You never talk: you either call exactly ONE tool for his request, or call escalate.
The request is a speech transcript and may be misheard ("AlkeneOS" = AlchemOS, "time" = timer, "workplace" = workspace, "VVN" = VPN).
Themes: AURUM gold, ARGENT silver, IRON red, VERDIGRIS copper-teal, MERCURY cyan, LEAD violet-grey; the legacy names STARK, MARK III, VIBRANIUM, MATRIX, ARCTIC, SOLAR also work.
"Your volume" or "your voice" = orrin_volume; the music or the system volume = media.
Music: a named song, album, artist or playlist → spotify_play; a taste or an activity → dj_start with his words as the mood; more or less like this → dj_adjust.
An app on a workspace ("open Steam on workspace one") is one open_app call with workspace set.
Weather: leave place empty for home or anywhere around campus; only name a place he names.
Call escalate when no tool fits, when it needs email, calendar, documents, assignments or grades, reading or clicking in a window, more than one action, or when you are not sure what he means. Never guess. Never ask him a question."""

VERBS = {"open", "close", "launch", "start", "stop", "play", "pause", "resume", "skip", "switch", "change", "set",
         "turn", "put", "move", "raise", "lower", "increase", "decrease", "mute", "unmute", "show", "hide", "add",
         "remove", "take", "make", "go", "restart", "dim", "brighten", "connect", "disconnect", "queue", "like",
         "save", "lock", "check", "bring", "kill", "shuffle", "repeat"}
SPLIT = re.compile(r"\s*(?:,|;|\band then\b|\bthen\b|\band\b|\balso\b|\bplus\b)\s+")
CHECK = re.compile(r"^(?:(?:can|could|would|will) you |please |hey |okay |ok |so |and )*"
                   r"(?:check|look (?:at|in|for|into)|see (?:if|whether|what|who|how)|monitor|watch|keep (?:an )?eye|scan|read|find)\b")
SENDS = re.compile(r"\b(?:send|e-?mail|text|message|dm|reply|respond|post|tweet|share|forward|call|invite|book|buy|"
                   r"pay|order|submit|upload|tracker|assignment|grade|calendar|meeting|doc|docs|document)\b")
WORD = re.compile(r"[a-z0-9']+")


def words(t):
    return WORD.findall(t.lower())


def two_part(t):
    """Two requests in one breath ("restart the song and raise the volume"): each part has its own verb."""
    parts = [p for p in SPLIT.split(t.lower()) if p.strip()]
    return sum(1 for p in parts if set(words(p)) & VERBS) >= 2


# ── the server ──
def _systemctl(*args, timeout=20):
    try:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as e:
        return subprocess.CompletedProcess(args, 1, "", str(e))


def unit_state():
    return _systemctl("is-active", UNIT).stdout.strip() or "unknown"


def api_key():
    try:
        return KEY_FILE.read_text().strip()
    except OSError:
        return ""


def request(path, body=None, timeout=10):
    """JSON in, JSON out, with the API key. Raises OSError (URLError, timeouts) / ValueError on failure."""
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(URL + path, data, {"Content-Type": "application/json",
                                                    "Authorization": "Bearer " + api_key()})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def healthy(timeout=1.0):
    try:
        return request("/health", timeout=timeout).get("status") == "ok"
    except (OSError, ValueError):
        return False


def model_name():
    try:
        return os.path.basename(request("/v1/models", timeout=2)["data"][0]["id"])
    except (OSError, ValueError, KeyError, IndexError):
        return ""


# ── settings (quickshell/settings.json, the HUD reloads it) ──
_settings_lock = threading.Lock()


def write_setting(key, value):
    with _settings_lock:
        try:
            data = json.loads(C.HUD_SETTINGS.read_text())
        except (OSError, ValueError):
            data = {}
        if data.get(key) == value:
            return False
        data[key] = value
        tmp = C.HUD_SETTINGS.with_suffix(".brain.tmp")
        tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n")
        tmp.replace(C.HUD_SETTINGS)
        return True


# ── places for the weather ──
_places = None


def places():
    global _places
    if _places is None:
        try:
            _places = json.loads(PLACES_FILE.read_text())
        except (OSError, ValueError):
            _places = {"home": ["home", "here"], "places": {}}
    return _places


def canon_place(p):
    """→ "" (home), a known place's full name, or None (not known: Claude decides)."""
    t = " ".join(words(str(p or "").replace(",", " ")))
    t = re.sub(r"^(?:in|at|for|around|near|the) ", "", t)
    if not t:
        return ""
    pl = places()
    if t in pl.get("home", ()):
        return ""
    if t in pl.get("places", {}):
        return pl["places"][t]
    city = t.split(" ontario")[0].strip()
    return pl["places"].get(city) if city in pl.get("places", {}) else ("" if city in pl.get("home", ()) else None)


# ── trust per intent (learned_intents.json "llm") ──
def _blank():
    return {"state": "shadow", "streak": 0, "agree": 0, "disagree": 0, "escalated": 0, "live_ok": 0, "live_neg": 0,
            "updated": 0}


def trust():
    return L.read().get("llm", {})


def is_live(intent):
    return trust().get(intent, {}).get("state") == "live"


def _bump(intent, verdict, promote_at, why=""):
    """One shadow verdict for intent: agree / disagree / escalated. → the new state."""
    if not intent:
        return None
    with L.edit() as st:
        rec = st.setdefault("llm", {}).setdefault(intent, _blank())
        rec["updated"] = time.time()
        if verdict == "agree":
            rec["agree"] += 1
            rec["streak"] += 1
            if rec["state"] != "live" and rec["streak"] >= promote_at:
                rec["state"] = "live"
                L.event(st, "llm-live", None, intent, f"{rec['streak']} agreements with Claude in a row")
        elif verdict == "disagree":
            rec["disagree"] += 1
            was = rec["state"]
            rec["streak"], rec["state"] = 0, "shadow"
            if was == "live":
                L.event(st, "llm-demoted", None, intent, why or "Claude did something else")
        elif verdict == "escalated":
            rec["escalated"] += 1
        return rec["state"]


def _live_outcome(intent, ok, why=""):
    if not intent:
        return
    with L.edit() as st:
        rec = st.setdefault("llm", {}).setdefault(intent, _blank())
        rec["updated"] = time.time()
        if ok:
            rec["live_ok"] += 1
            return
        rec["live_neg"] += 1
        was = rec["state"]
        rec["streak"], rec["state"] = 0, "shadow"
        if was == "live":
            L.event(st, "llm-demoted", None, intent, why or "corrected")


# ── a proposal ──
@dataclass
class Proposal:
    text: str
    source: str = "voice"
    think: bool = False
    tool: str = ""
    args: dict = field(default_factory=dict)
    intent: str = ""
    escalate: str = ""                        # why it goes to Claude; "" = a checked plan
    raw: list = field(default_factory=list)   # [[tool, args]] as the model returned them
    ms: float = 0.0
    steps: list = None                        # fast-path steps, ready for Orrin.run_steps
    queued: float = 0.0                       # time.monotonic() when Orrin handed it over (≈ the request's start)
    done: float = 0.0                         # … and when the proposal was checked

    @property
    def ok(self):
        return not self.escalate and bool(self.steps)

    def info(self):
        """For Orrin's outcome watch (same keys as router_local.Decision.info())."""
        return {"text": self.text, "intent": self.intent, "score": 0.0, "example": "", "tier": "llm"}


class LocalTier:
    def __init__(self, cfg, router=None, log=print, record=True):
        """record: write verdicts / trust / llm_log (off for dry runs)."""
        self.cfg, self.router, self.log, self.record = cfg, router, log, record
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="orrin-llm")
        self.warm = False                     # the system prompt + tools are in the server's prompt cache
        self.warm_from = ""                   # "restored from disk" | "computed and saved"
        self.power = None                     # Power, in the voice process
        self._tools = None
        self._intents = None
        self._lock = threading.Lock()

    # ── switches ──
    def enabled(self):
        return self.cfg["orrinBrain"] != "claude"

    def shadow_only(self):
        return bool(self.cfg["orrinBrainShadow"])

    def ready(self):
        return self.enabled() and self.warm and healthy(0.3)

    @staticmethod
    def is_live(intent):
        return is_live(intent)

    @staticmethod
    def budget(source):
        return BUDGET.get(source, BUDGET["voice"])

    # ── what it may see ──
    def intents(self):
        if self.router is not None:
            return self.router.data["intents"]
        if self._intents is None:
            self._intents = json.loads((C.ORRIN_DIR / "intents.json").read_text())["intents"]
        return self._intents

    def tools(self):
        with self._lock:
            if self._tools is None:
                self._tools = load_tools()
            return self._tools

    def allowed(self):
        return {t["function"]["name"] for t in self.tools()} - {"escalate"}

    def eligible(self, text, d=None):
        """→ (ok, why). d: the router's decision (None when the router is off)."""
        if not self.enabled():
            return False, "off"
        if d is not None and not d.path.startswith(ELIGIBLE):
            return False, d.path
        t = " ".join(words(text))
        if not t:
            return False, "empty"
        from . import fastpath
        if fastpath.is_integration_intent(text) or SENDS.search(t):
            return False, "account or sending"
        if len(t.split()) > MAX_WORDS:
            return False, "long"
        if CHECK.search(t):
            return False, "check"
        if two_part(t):
            return False, "two-part"
        return True, ""

    # ── asking it ──
    def prefix_file(self):
        """The saved prompt cache's name: a hash of everything before his words, so a changed prompt, tool list or
        model never restores a stale one."""
        import hashlib
        key = json.dumps({"system": SYSTEM, "tools": self.tools(), "model": model_name()}, sort_keys=True)
        return f"orrin-prefix-{hashlib.sha1(key.encode()).hexdigest()[:16]}.bin"

    def warm_up(self, timeout=180):
        """Put the system prompt + tools into the server's prompt cache. From the saved copy when there is one
        (~0.1 s); otherwise compute it (~33 s cold on the iGPU: ~4.2k tokens at ~130 tokens/s) and save it for the
        next start. → True when warm."""
        name, restored = self.prefix_file(), False
        try:
            if (SLOT_DIR / name).exists():
                request("/slots/0?action=restore", {"filename": name}, timeout=60)
                restored = True
        except (OSError, ValueError) as e:
            self.log(f"ORRIN: local model: saved prompt cache not restored ({e})")
        try:
            j = request("/v1/chat/completions", self._body("warm up", False, max_tokens=1), timeout=timeout)
            self.warm = True
        except (OSError, ValueError) as e:
            self.warm = False
            self.log(f"ORRIN: local model warm-up failed: {e}")
            return False
        computed = int((j.get("timings") or {}).get("prompt_n") or 0)
        self.warm_from = "restored from disk" if restored and computed < 100 else "computed and saved"
        if computed >= 100:                         # it had to compute the prefix: keep it for the next start
            try:
                request("/slots/0?action=save", {"filename": name}, timeout=60)
                for old in SLOT_DIR.glob("orrin-prefix-*.bin"):
                    if old.name != name:
                        old.unlink(missing_ok=True)
            except (OSError, ValueError) as e:
                self.log(f"ORRIN: local model: couldn't save the prompt cache ({e})")
        return True

    def _body(self, text, think, max_tokens=None):
        return {"messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}],
                "tools": self.tools(), "tool_choice": "auto", "parallel_tool_calls": False, "stream": False,
                "max_tokens": max_tokens or MAX_TOKENS[think], "temperature": 0.2, "top_p": 0.9,
                "chat_template_kwargs": {"enable_thinking": think}}

    def submit(self, text, d=None, source="voice"):
        """Non-blocking: the proposal runs on this tier's own worker thread; Orrin goes on to Claude at once."""
        return self.pool.submit(self.propose, text, d, source, time.monotonic())

    def propose(self, text, d=None, source="voice", queued=None):
        think = THINK.get(source, False)
        p = Proposal(text=text, source=source, think=think, queued=queued or time.monotonic())
        t0 = time.monotonic()
        try:
            j = request("/v1/chat/completions", self._body(text, think), timeout=BUDGET.get(source, 8.0) + 30)
            msg = j["choices"][0]["message"]
        except (OSError, ValueError, KeyError, IndexError) as e:
            p.escalate, p.ms = f"server: {type(e).__name__}", (time.monotonic() - t0) * 1000
            p.done = time.monotonic()
            return p
        p.ms = (time.monotonic() - t0) * 1000
        for tc in msg.get("tool_calls") or []:
            f = tc.get("function", {})
            try:
                a = json.loads(f.get("arguments") or "{}")
            except ValueError:
                a = None
            p.raw.append([f.get("name", ""), a])
        self.check(p, d)
        p.done = time.monotonic()
        return p

    def check(self, p, d=None):
        """The model's answer → a checked plan (p.tool, p.args, p.intent, p.steps), or p.escalate."""
        if not p.raw:
            p.escalate = "no call"
            return p
        if len(p.raw) > 1:
            p.escalate = "several calls"
            return p
        tool, args = p.raw[0]
        if tool == "escalate":
            p.escalate = "model: " + str((args or {}).get("reason", ""))[:120]
            return p
        if tool not in self.allowed():
            p.escalate = f"not allowed: {tool}"
            return p
        if not isinstance(args, dict):
            p.escalate = "bad arguments"
            return p
        ok, why, args = validate(tool, args)
        if not ok:
            p.escalate = f"invalid: {why}"
            return p
        why = numbers_said(tool, args, p.text)
        if why:
            p.escalate = f"numbers: {why}"
            return p
        p.tool, p.args = tool, args
        p.intent = intent_of(self.intents(), tool, args, d)
        p.steps = [steps_for(self.intents(), p.intent, tool, args)]
        return p

    # ── shadow ──
    def should_wait(self, d):
        """Act locally only with shadow mode off, and only wait (≈4 s) when an earned intent is likely."""
        if self.shadow_only():
            return False
        live = {k for k, v in trust().items() if v.get("state") == "live"}
        if not live:
            return False
        if any(k.startswith("llm.") for k in live):
            return True
        guesses = {n for n, _ in (d.top3 if d is not None else [])}
        return bool(guesses & live)

    def compare_later(self, fut, reply):
        """Claude has answered (reply: core.brain.Reply); log how the proposal compares once it's in. Never waits:
        the comparison runs on the tier's worker when the proposal finishes."""
        replied = time.monotonic()

        def done(f):
            try:
                self.record_shadow(f.result(), reply, replied)
            except Exception as e:                          # never let a log take down a turn
                self.log(f"ORRIN: local model shadow log: {type(e).__name__}: {e}")
        fut.add_done_callback(done)

    def record_shadow(self, p, reply, replied=None):
        import orrin_db as db
        if not self.record:
            return
        target = claude_action(reply)
        c_intent = ""
        if target and target[0] != "none":
            c_intent = intent_of(self.intents(), target[0], target[1], None)
        if target is None:
            verdict, why = "unknown", "Claude failed, was interrupted or did several things"
        elif p.escalate:
            verdict, why = "escalated", p.escalate
        elif target[0] == "none":
            verdict, why = "disagree", "Claude didn't act"
        elif target[0] == p.tool and same_args(p.tool, p.args, target[1]):
            verdict, why = "agree", ""
        else:
            verdict, why = "disagree", f"Claude: {target[0]}"
        state = None
        if verdict in ("agree", "disagree"):
            state = _bump(p.intent, verdict, int(self.cfg["orrinLocalPromote"]), why)
        elif verdict == "escalated" and c_intent:
            _bump(c_intent, "escalated", int(self.cfg["orrinLocalPromote"]))
        db.log_llm(p.text, p.source, "shadow", p.intent, [p.tool, p.args] if p.tool else p.raw[:1] or None,
                   None if target is None else ([] if target[0] == "none" else list(target)), c_intent,
                   verdict, why, round(p.ms, 1), p.think)
        timing = f" · proposal {p.ms / 1000:.1f} s, ready at +{p.done - p.queued:.1f} s"
        if replied:
            timing += f"; Claude replied at +{replied - p.queued:.1f} s without waiting for it"
        self.log(f"  ◇ local model {verdict}: {p.intent or '-'}" + (f" ({why})" if why else "") +
                 (f" → now {state}" if state == "live" and verdict == "agree" else "") + timing)

    # ── live ──
    def record_live(self, p, tools):
        import orrin_db as db
        if not self.record:
            return
        failed = any(t.endswith("[failed]") for t in tools)
        if failed:
            _live_outcome(p.intent, False, "the call failed")
        db.log_llm(p.text, p.source, "live", p.intent, [p.tool, p.args], None, "", "live-failed" if failed else "live",
                   "", round(p.ms, 1), p.think)

    def outcome(self, info, outcome, why=""):
        """What came after a live local action (Orrin's watch): pos | neg."""
        if self.record:
            _live_outcome(info.get("intent"), outcome == "pos", why)


LAPTOP_IDLE_S = 600          # laptop mode: stop the model after this long without an eligible request
CHECK_S = 3                  # how often Power looks at the service


class Power:
    """orrin-llm.service follows Orrin's power rules. VoiceLoop calls tick() every pass of its loop (also while
    paused for combat mode):
      docked              running and warm (the prompt cache holds the system prompt + tools: ~1-2 s to a first
                          token instead of ~40 s)
      laptop mode         started by the first eligible request (that one goes to Claude), stopped after
                          LAPTOP_IDLE_S without one
      combat mode         stopped, so games get the iGPU (whether or not the wake word pauses); back after
      orrinBrain claude   stopped
      Orrin off           stopped with it (PartOf=orrin.service): the toggle, battery under 20 % in laptop mode
                          (quickshell/OrrinState.qml), log-out
    A restarted server (new pid) is warmed again."""

    def __init__(self, tier, laptop, log=print):
        self.tier, self.laptop, self.log = tier, laptop, log
        tier.power = self
        self.last_use = 0.0
        self.last_check = 0.0
        self.pid = None
        self.warming = False
        self.why = ""

    def demand(self):
        self.last_use = time.monotonic()

    def wanted(self, combat):
        if not self.tier.enabled():
            return False, "off in Settings"
        if combat:
            return False, "combat mode"
        if not self.laptop:
            return True, "docked"
        if self.last_use and time.monotonic() - self.last_use < LAPTOP_IDLE_S:
            return True, "asked for (laptop mode)"
        return False, "idle (laptop mode)"

    def tick(self, combat, force=False):
        now = time.monotonic()
        if not force and now - self.last_check < CHECK_S:
            return
        self.last_check = now
        want, why = self.wanted(combat)
        pid = _systemctl("show", "-P", "MainPID", UNIT).stdout.strip()
        running = pid not in ("", "0")
        if want and not running:
            self.log(f"ORRIN: starting the local model ({why})")
            _systemctl("start", "--no-block", UNIT)
            self.tier.warm, self.pid = False, None
        elif not want and running:
            self.log(f"ORRIN: stopping the local model ({why})")
            _systemctl("stop", "--no-block", UNIT)
            self.tier.warm, self.pid = False, None
        elif want and running and pid != self.pid and not self.warming:
            self.pid = pid                            # new (or restarted) server: fill its prompt cache
            self.tier.warm = False
            self.warming = True
            threading.Thread(target=self._warm, daemon=True).start()
        self.why = why

    def _warm(self):
        try:
            t0 = time.monotonic()
            while time.monotonic() - t0 < 120 and not healthy(1.0):
                time.sleep(1)
            if self.tier.warm_up():
                self.log(f"ORRIN: local model warm ({time.monotonic() - t0:.1f} s after start, prompt cache "
                         f"{getattr(self.tier, 'warm_from', '?')})")
            else:
                self.pid = None                       # try again on a later tick
        finally:
            self.warming = False


# ── tools ──
def load_tools():
    """The allowlisted alchemos tools as OpenAI function schemas, from the MCP server itself (the same schemas
    Claude gets), plus escalate. Read in a child process: inside Orrin, ~/.config/orrin is first on sys.path, so
    its mcp/ folder would shadow the real `mcp` package."""
    code = ("import asyncio, json, sys; sys.path.append(sys.argv[1]); import alchemos_tools as T; "
            "print(json.dumps([t.model_dump() for t in asyncio.run(T.mcp.list_tools())]))")
    r = subprocess.run([sys.executable, "-c", code, str(C.ORRIN_DIR / "mcp")], cwd="/", capture_output=True,
                       text=True, timeout=60)
    if r.returncode != 0:
        raise RuntimeError("couldn't read the tool schemas: " + r.stderr.strip()[-300:])
    allow = set(ALLOW_TOOLS) - L.BLOCKED_TOOLS
    out = []
    for d in json.loads(r.stdout.strip().splitlines()[-1]):
        if d["name"] in allow:
            out.append({"type": "function", "function": {"name": d["name"], "description": d.get("description") or "",
                                                          "parameters": d.get("inputSchema") or d.get("input_schema")}})
    out.sort(key=lambda x: ALLOW_TOOLS.index(x["function"]["name"]))   # a stable prompt: the cache depends on it
    return out + [ESCALATE]


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate(tool, args):
    """Orrin's own check of the model's arguments, before anything runs. → (ok, why, cleaned args)."""
    import alchemos_actions as A
    a = {k: v for k, v in args.items() if v not in (None, "")}
    if tool == "open_app":
        if not A.find_app(str(a.get("name", "")))[0]:
            return False, f"no app {a.get('name')!r}", a
        ws = _num(a.get("workspace", 0))
        if ws is None or not 0 <= ws <= 10 or ws != int(ws):
            return False, "workspace", a
        a["workspace"] = int(ws)
        if not a["workspace"]:
            a.pop("workspace")
    elif tool == "switch_workspace":
        n = _num(a.get("n"))
        if n is None or not 1 <= n <= 10 or n != int(n):
            return False, "workspace", a
        a["n"] = int(n)
    elif tool == "set_theme":
        if not A.match_preset(str(a.get("preset", ""))):
            return False, f"no theme {a.get('preset')!r}", a
    elif tool == "set_timer":
        m = _num(a.get("minutes"))
        if m is None or not 0 < m <= 24 * 60:
            return False, "minutes", a
        a["minutes"] = int(m) if m == int(m) else m
    elif tool == "weather":
        place = canon_place(a.get("place", ""))
        if place is None:
            return False, f"unknown place {a.get('place')!r}", a
        a["place"] = place
        if not place:
            a.pop("place")
    elif tool in ("media", "orrin_volume"):
        for k in ("value", "percent"):
            if k in a:
                v = _num(a[k])
                if v is None or not 0 <= v <= 100:
                    return False, k, a
                a[k] = int(v)
        if tool == "orrin_volume" and a.get("action") == "set" and "percent" not in a:
            return False, "percent", a
        if tool == "media" and a.get("action") == "set_volume" and "value" not in a:
            return False, "value", a
    elif tool in ("set_audio_output", "set_audio_input"):
        import audio_devices as AD
        state, _ = AD.resolve(str(a.get("device", "")), "out" if tool == "set_audio_output" else "in")
        if state == "none":
            return False, f"no device {a.get('device')!r}", a
    elif tool in ("spotify_play", "spotify_queue"):
        if not str(a.get("query", "")).strip():
            return False, "query", a
    return True, "", a


NUMERIC = {"open_app": ("workspace",), "switch_workspace": ("n",), "media": ("value",), "orrin_volume": ("percent",),
           "lights": ("value",), "spotify_player": ("value",)}


def numbers_said(tool, args, text):
    """Every number the model passes must come from his words (the stage-2 trial set "one hour 29 minute" as 69):
    a timer must match the router's own duration parser, other numbers must be said. → why not, or ""."""
    from .router_local import _numbers, clean, slot_minutes, slot_percent
    t = clean(text)
    if tool == "set_timer":
        m = slot_minutes(t)
        if m is None:
            return "no duration in the words"
        if abs(float(args["minutes"]) - m) > 0.01:
            return f"{args['minutes']} minutes, but the words say {m:g}"
        return ""
    said = set(_numbers(t, homophones=True))
    pct = slot_percent(t)
    for k in NUMERIC.get(tool, ()):
        v = _num(args.get(k))
        if v is None or (k == "workspace" and v == 0):
            continue
        if tool == "lights" and str(args.get("action")) != "brightness":
            continue                                        # lights value is a mode name then
        if v not in said and v != pct:
            return f"{k}={v:g} isn't in the words"
    return ""


def _fixed_ok(it, args):
    """The intent's fixed args match, and its slot values are in their domain (media.mute is only mute / unmute)."""
    from .router_local import DOMAINS
    if not all(v in ("", None) or str(args.get(k, "")).lower() == str(v).lower() for k, v in (it.get("args") or {}).items()):
        return False
    for k, typ in (it.get("slots") or {}).items():
        dom = DOMAINS.get(typ.rstrip("?"))
        if dom and k in args and str(args[k]).lower() not in dom:
            return False
    return True


def intent_of(intents, tool, args, d=None):
    """The intents.json intent a call is, so trust and spoken lines are shared with the router. The router's own
    guess wins a tie (system_status is status.overview / battery / temperature). None fits → "llm.<tool>[.action]"."""
    cands = [n for n, it in intents.items() if it.get("kind", "tool") == "tool" and it.get("tool") == tool
             and _fixed_ok(it, args)]
    if not cands:
        act = args.get("action") or args.get("direction") or args.get("type")
        return f"llm.{tool}" + (f".{act}" if act else "")
    hints = [n for n, _ in (d.top3 if d is not None else [])]
    for h in hints:
        if h in cands:
            return h
    # the most specific: most fixed args that matched
    return max(cands, key=lambda n: (len([v for v in (intents[n].get("args") or {}).values() if v not in ("", None)]),
                                     -list(intents).index(n)))


def steps_for(intents, intent, tool, args):
    """One fast-path step with the intent's fixed line (persona.style() makes it SELENE's when she speaks)."""
    from . import fastpath
    it = intents.get(intent)
    if it:
        from .router_local import say_for
        say = say_for(it, args)
    else:
        say = lambda r: r.get("say") or "Done, sir."              # Spotify / DJ results carry their own line
    return fastpath.step(tool, say, **args)


def claude_action(reply):
    """What Claude did, for the comparison: (tool, args), ("none", {}) if it only talked, or None if it can't be
    compared (an error, an interruption, a declined call, several actions, or not an alchemos tool)."""
    if reply is None or getattr(reply, "error", "") or getattr(reply, "interrupted", False):
        return None
    if any(t.endswith(("[declined]", "[failed]", "[read-only]", "[refused]")) for t in reply.tools):
        return None
    calls = [(s, t, a) for s, t, a in reply.calls]
    if not calls:
        return ("none", {})
    acts = [c for c in calls if c[1] not in LOOKUPS]
    if not acts:                        # only lookups: the last one is what answered him
        acts = calls[-1:]
    if len(acts) != 1 or acts[0][0] != "alchemos":
        return None
    return acts[0][1], dict(acts[0][2] or {})


def _loose(a, b):
    from rapidfuzz import fuzz
    return fuzz.token_set_ratio(str(a).lower(), str(b).lower()) >= 80


def same_args(tool, mine, theirs):
    import alchemos_actions as A
    ok_t, _, theirs = validate(tool, dict(theirs))
    keys = (set(mine) | set(theirs)) - IGNORED
    for k in keys:
        x, y = mine.get(k), theirs.get(k)
        if x in (None, "", 0, False) and y in (None, "", 0, False):
            continue
        if x in (None, "") or y in (None, ""):
            return False
        if k == "preset":
            if A._preset_key(A.match_preset(str(x)) or str(x)) != A._preset_key(A.match_preset(str(y)) or str(y)):
                return False
        elif k == "name":
            if A.find_app(str(x))[0] != A.find_app(str(y))[0]:
                return False
        elif k == "device":
            if str(x).lower() != str(y).lower():
                import audio_devices as AD
                d = "out" if tool == "set_audio_output" else "in"
                rx, ry = AD.resolve(str(x), d), AD.resolve(str(y), d)
                if not (rx[0] == ry[0] == "ok" and rx[1]["name"] == ry[1]["name"]):
                    return False
        elif k in FREE_TEXT:
            if not _loose(x, y):
                return False
        elif _num(x) is not None and _num(y) is not None:
            if abs(_num(x) - _num(y)) > 1e-6:
                return False
        elif str(x).strip().lower() != str(y).strip().lower():
            return False
    return True


# ── CLI ──
USAGE = "usage: orrin brain status | shadow on|off|report [DAYS] | bench [--think both|on|off] [--reps N] [--cases 0,3,7]"


def cli(argv):
    cmd = argv[0] if argv else "status"
    if cmd == "status":
        return status()
    if cmd == "shadow" and argv[1:2] in (["on"], ["off"]):
        on = argv[1] == "on"
        write_setting("orrinBrainShadow", on)
        print("Shadow mode on: the local model only proposes, Claude acts." if on else
              "Shadow mode off: intents the local model has earned run locally; the rest still go to Claude.")
        return 0
    if cmd == "shadow" and argv[1:2] == ["report"]:
        return report(int(argv[2]) if len(argv) > 2 and argv[2].isdigit() else 14)
    if cmd == "bench":
        return bench(argv[1:])
    print(USAGE)
    return 2


def status():
    cfg = C.Config()
    st = unit_state()
    mode = ("off (Claude only)" if cfg["orrinBrain"] == "claude" else
            "shadow (proposes only, Claude acts)" if cfg["orrinBrainShadow"] else "live for earned intents")
    line = f"local model: {mode} · {UNIT} {st}"
    if st == "active":
        line += " · " + (f"ready, {model_name()}" if healthy() else "loading")
    print(line)
    tr = trust()
    live = sorted(k for k, v in tr.items() if v.get("state") == "live")
    n = int(cfg["orrinLocalPromote"])
    near = sorted(((k, v["streak"]) for k, v in tr.items() if v.get("state") != "live" and v.get("streak")), key=lambda x: -x[1])
    print("earned: " + (", ".join(live) if live else "none yet") + f"  (an intent earns it with {n} agreements in a row)")
    if near:
        print("on the way: " + ", ".join(f"{k} {s}/{n}" for k, s in near[:8]))
    return 0


def report(days=14):
    import statistics
    sys.path.append(str(C.ORRIN_DIR / "mcp"))
    import orrin_db as db
    rows = db.llm_log(days)
    if not rows:
        print(f"No local model decisions in the last {days} days.")
        return 0
    by = {}
    for r in rows:
        by.setdefault(r["verdict"], []).append(r)
    shadow = [r for r in rows if r["mode"] == "shadow" and r["verdict"] != "unknown"]
    agree = len(by.get("agree", []))
    print(f"last {days} days: {len(rows)} eligible requests · shadow {len(shadow)} (agree {agree}, disagree "
          f"{len(by.get('disagree', []))}, escalated {len(by.get('escalated', []))}) · live {len(by.get('live', []))}"
          f" (failed {len(by.get('live-failed', []))})")
    ms = [r["ms"] for r in rows if r["ms"]]
    if ms:
        print(f"proposal time: median {statistics.median(ms) / 1000:.1f} s, slowest {max(ms) / 1000:.1f} s")
    tr = trust()
    n = int(C.Config()["orrinLocalPromote"])
    names = sorted(set(tr) | {r["intent"] for r in rows if r["intent"]})
    if names:
        print(f"\n{'intent':<26}{'state':<8}{'streak':>7}{'agree':>7}{'disagree':>9}{'escalated':>10}{'live ok/neg':>13}")
    for k in names:
        v = tr.get(k, _blank())
        print(f"{k:<26}{v['state']:<8}{str(v['streak']) + '/' + str(n):>7}{v['agree']:>7}{v['disagree']:>9}{v['escalated']:>10}"
              f"{str(v['live_ok']) + '/' + str(v['live_neg']):>13}")
    bad = by.get("disagree", [])[-8:]
    if bad:
        print("\nlatest disagreements:")
        for r in bad:
            print(f"  {time.strftime('%m-%d %H:%M', time.localtime(r['ts']))}  {r['request'][:44]:<44}  local {r['call'] or '-'}"
                  f"  · Claude {r['claude'] or '-'}")
    esc = {}
    for r in by.get("escalated", []):
        k = r["why"].split(":")[0]
        esc[k] = esc.get(k, 0) + 1
    if esc:
        print("\nwhy it escalated: " + ", ".join(f"{k} {v}" for k, v in sorted(esc.items(), key=lambda x: -x[1])))
    return 0


def bench(args):
    """Refresh the tool schemas from the live MCP servers (needs Orrin's venv), then run the harness with
    the system Python in isolated mode (it only needs the standard library)."""
    harness = BENCH_DIR / "bench.py"
    if not harness.exists():
        print(f"no benchmark at {harness}")
        return 1
    dump = subprocess.run([sys.executable, str(BENCH_DIR / "dump_tools.py"), str(BENCH_DIR / "tools_all.json")],
                          cwd=BENCH_DIR, capture_output=True, text=True)
    if dump.returncode != 0:
        print("couldn't read the tool schemas:\n" + dump.stderr[-800:])
        return 1
    print(f"tool schemas refreshed ({dump.stdout.split()[0]} tools). Running the benchmark: this stops {UNIT} "
          "for an idle-power baseline and takes 15-30 minutes.", flush=True)
    t0 = time.time()
    rc = subprocess.run(["python3", "-I", str(harness), *args], cwd=BENCH_DIR).returncode
    print(f"bench finished in {(time.time() - t0) / 60:.0f} min (exit {rc})")
    return rc
