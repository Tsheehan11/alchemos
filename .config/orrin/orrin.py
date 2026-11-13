#!/usr/bin/env python3
"""
JARVIS: Claude-powered voice assistant for the desktop (AlchemOS; STARK OS in the legacy skin).

  "Hey Jarvis" → chime, LISTENING on the HUD, music turned down → the command
    (from just before the wake word, so a one-breath "hey Jarvis dim the lights"
    keeps its first word; see core/hearing.py) → faster-whisper → fast path
    (local rules, no AI: media, lock, workspaces, lights, VPN, apps, themes,
    timers, weather) → local router (core/router_local.py: sentence embedding vs
    intents.json, acts only when sure and every slot is filled) → Claude (Agent SDK on the Pro login, tools from MCP
    servers in servers.json, reply spoken sentence by sentence as it streams)
    → spoken reply (Kokoro) + HUD toast.
  Anything that goes wrong after the chime gets a short spoken line and the
  reason on the toast; it never goes quiet on you.
  After a reply it listens ~8 s for a follow-up without the wake word.
  "Hey Jarvis" while it's talking or thinking interrupts it.
  Combat mode pauses the wake word (frees the mic); reminders still fire.

Started by the HUD (quickshell/OrrinState.qml) only while docked.

Text mode / testing:
  orrin --text "set the theme to matrix and dim the lights"
  orrin --text "..." --dry-run      validate + print tool calls, change nothing
  orrin --text "suspend" --confirm no     answer the confirmation question
  orrin --misses | --log | --facts | --reminders | --say "text"
  orrin --trace          follow each exchange stage by stage (wake score, VAD, STT, route, TTS)
  orrin --record [MIN]   also keep WAVs of each exchange for tuning (~/.local/state/orrin/rec)

Phase-2 integrations (servers.json, core/integrations.py, docs/phase2-*.md):
  orrin integrations [--json]       CONNECTED / NOT CONNECTED for each
  orrin connect google | microsoft | learn-ical [URL]
  orrin disconnect google | microsoft | learn-ical

ORRIN app (Super + J, quickshell/OrrinApp.qml; core/appserver.py, conversations.py, tasks.py):
  orrin control stop | status | log    window control: kill switch (Super+Shift+Escape runs "stop"), state, history
  orrin app-data threads [QUERY] [--quick] | thread ID | tasks | task ID | watchers | usage   history as JSON

SE tracker sheet (mcp/tracker.py, docs/orrin-app.md):
  orrin tracker find [ID] | show | pending [DAYS] | diff | log [N] | undo
Calendar writes (mcp/google_api.CalendarWriter):
  orrin calendar log [N] | undo

Window reading (core/screen.py; ~/.config/kitty/orrin-rc-*.{sh,py}):
  orrin kitty-rc [status | setup | rotate]   kitty's get-text-only password in the keyring

Spotify + DJ mode (mcp/spotify_api.py, core/dj.py, core/spotify_cli.py):
  orrin spotify connect | status [--json] | devices | now | disconnect
  orrin dj start [MOOD] | stop | status | more | less | keep | chatter off|rare|normal | save NAME | moods

Local router (intents.json, tools/eval_router.py):
  orrin intents [list | log [N]]                        intents, recent decisions
  orrin router stats | review | approve ID | forget ID | reset-learned   what it learned (core/router_learn.py)
"""
import argparse
import asyncio
import atexit
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

ORRIN_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ORRIN_DIR / "mcp"))
sys.path.insert(0, str(ORRIN_DIR))
os.environ.pop("ANTHROPIC_API_KEY", None)   # Pro login only, never an API key

if __name__ == "__main__" and sys.argv[1:2] in (["connect"], ["disconnect"], ["integrations"]):
    from core import integrations          # before the heavy imports: Settings polls `integrations --json`
    sys.exit(integrations.main(sys.argv[1:]))
if __name__ == "__main__" and sys.argv[1:2] == ["control"]:
    from core import control
    sys.exit(control.cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["kitty-rc"]:
    from core import screen                # status / setup / rotate of the kitty get-text password
    sys.exit(screen.kitty_rc_cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["app-data"]:
    from core import conversations         # the app reads history this way while Orrin is off (undocked)
    sys.exit(conversations.app_data(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["tracker"]:
    sys.path.insert(0, str(ORRIN_DIR / "mcp"))
    import tracker                         # find / show / pending / diff / log / undo: no models needed
    sys.exit(tracker.cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["calendar"]:
    sys.path.insert(0, str(ORRIN_DIR / "mcp"))
    import google_api                      # log / undo of Orrin's calendar writes
    sys.exit(google_api.calendar_cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["wake"]:
    from core import wake                  # status / record / test / enable / disable custom wake words
    sys.exit(wake.cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["feed"]:
    from core import feed                  # calendar / due / weather data for the HUD widgets (no Claude)
    sys.exit(feed.main(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["audio"]:
    import audio_devices                   # list / output / input: Settings → AUDIO picks go through here
    sys.exit(audio_devices.cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] in (["spotify"], ["dj"]):
    from core import spotify_cli           # connect / status / disconnect / devices; dj start|stop|status (no models)
    sys.exit(spotify_cli.main(sys.argv[1:]))
if __name__ == "__main__" and sys.argv[1:2] == ["secrets"]:
    from core import secrets               # migrate [--prune]: move the pre-AlchemOS "jarvis:" keyring entries to "orrin:"
    if sys.argv[2:3] != ["migrate"]:
        sys.exit("usage: orrin secrets migrate [--prune]")
    print("\n".join(secrets.migrate(prune="--prune" in sys.argv[3:])))
    sys.exit(0)
if __name__ == "__main__" and sys.argv[1:2] == ["usage"]:
    from core import usage                 # whole-account Claude usage for the HUD (no Claude, no tokens)
    sys.exit(usage.main(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["router"]:
    sys.path.insert(0, str(ORRIN_DIR / "mcp"))
    from core import router_learn          # stats / review / forget / reset-learned need no model (approve loads it)
    sys.exit(router_learn.cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["intents"]:
    sys.path.insert(0, str(ORRIN_DIR / "mcp"))
    from core import router_local          # list / review / remove need no model
    sys.exit(router_local.cli(sys.argv[2:]))

import orrin_db as db  # noqa: E402
import alchemos_actions as A  # noqa: E402
from core import control, fastpath, hearing, hud, persona, secrets, trace  # noqa: E402
from core import config as C  # noqa: E402

# ── Wake word / speech-to-text ──────────────────
WAKEWORD = "hey_jarvis"
# Custom openWakeWord models (tools/wakeword/, installed by `orrin wake enable`): DATA_DIR/wake/<word>.onnx,
# each with its threshold + persona in <word>.json (core/wake.installed()). "hey Jarvis" is always loaded
# as well and stays the fallback; a persona without a word of its own answers it (the active one does).
WAKE_PERSONA = {"hey_jarvis": "orrin"}         # load() adds the installed words
NEAR_MISS = 0.15           # wake scores above this (but under THRESHOLD) are traced as near misses
THRESHOLD = 0.4            # real "hey Jarvis" at the desk peaks at 0.83-1.0; nothing else got past 0.25
BARGE_THRESHOLD = 0.3      # over its own voice (which never scored above 0.21) "hey Jarvis" is harder to hear
COOLDOWN_S = 0.5           # after a conversation ends (the model is reset, so it can't refire on itself)
# base.en + vocabulary prompt: 0.3 s per command on this CPU. small.en was barely more accurate
# on Trevor's recordings (1-2 words in 28 commands) for 0.95 s; distil-small.en was worse.
WHISPER_MODEL = "base.en"
NO_SPEECH_TIMEOUT_S = 4.0  # nothing said after the wake word → "Sorry sir, I didn't catch that."
CONFIRM_TIMEOUT_S = 6.0
CHOICE_TTL_S = 60         # "Panel or widget?" can be answered this long after it was asked
RATE = hearing.RATE
CHUNK = hearing.CHUNK      # 80 ms
NOT_HEARD = "Sorry sir, I didn't catch that."
SYNC_S = 15 * 60           # Outlook calendar link + LEARN feed + grade notices, while docked

YES = re.compile(r"\b(yes|yeah|yep|yup|confirm(ed)?|do it|go ahead|affirmative|proceed|sure|please do|correct)\b")
ALLOW_TASK = re.compile(r"\ballow (it |this |the )?(for )?(the |this |whole )?task\b")
# "stop" while Orrin works a window (or just after the kill switch): it lets go, nothing else (not "stop the music")
STOP_CONTROL = re.compile(r"^\s*(?:(?:hey )?(?:orrin|selene|jarvis|friday),? )?(?:stop|stop it|stop that|stop now|halt|abort|let go|hands off|"
                          r"stop (?:control|controlling|clicking|typing))\s*(?:,? (?:orrin|selene|jarvis|friday))?[.!]*\s*$", re.I)
NO = re.compile(r"\b(no|nope|don't|do not|cancel|stop|negative|never ?mind|wait)\b")

REWORD_SIM = 0.6          # this similar to the request just before = the same request reworded (core/router_learn.py)
L_OUTCOME_S = 30          # router_learn.OUTCOME_S (not imported here: the CLI paths above must stay light)


def _refused(tools):
    """A tool call that was declined, refused or failed: nothing to learn from it."""
    return any(t.endswith(("[declined]", "[failed]", "[read-only]")) for t in tools)


LOG_FILE = None   # voice mode: ~/.local/share/orrin/orrin.log (the HUD discards stdout)


def log(*a):
    print(*a, flush=True)
    if LOG_FILE:
        LOG_FILE.write(datetime.now().strftime("%m-%d %H:%M:%S ") + " ".join(map(str, a)) + "\n")
        LOG_FILE.flush()


def open_log():
    global LOG_FILE
    path = C.DATA_DIR / "orrin.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1_000_000:
        path.replace(path.with_suffix(".log.old"))
    LOG_FILE = open(path, "a", encoding="utf-8")


def govee_pulse():
    """A small light swell on the strip with the chime (alchemos-govee skips it if the strip is off or busy).
    Straight to the daemon's Unix socket, fire and forget: no process, never delays listening."""
    import socket
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "alchemos-govee.sock")

    def send():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(path)
                s.sendall(b"anim listen\n")
        except OSError:
            pass                                   # no strip / daemon: nothing to do
    threading.Thread(target=send, daemon=True).start()


def spoken_prompt(prompt):
    """A window-control plan is shown in full (console / HUD); only its first line is said."""
    return prompt.split("\n", 1)[0]


def is_yes(text):
    t = text.lower()
    return bool(YES.search(t)) and not NO.search(t)


# Why a request failed, as the toast shows it (Brain.ERRORS has the spoken lines)
ERROR_LABELS = {"limit": "USAGE LIMIT", "offline": "NO NETWORK", "timeout": "TIMED OUT", "auth": "LOGIN EXPIRED",
                "failed": "CLAUDE ERROR", "tools": "TOO MANY STEPS", "noreply": "CLAUDE NOT RESPONDING",
                "tool": "ACTION FAILED", "heard": "DIDN'T CATCH THAT", "crash": "INTERNAL ERROR"}


# ── The assistant, shared by voice and text mode ─
class Orrin:
    def __init__(self, cfg, dry_run=False, confirm_sync=None, speak=None):
        self.cfg = cfg
        self.dry_run = dry_run
        A.set_dry_run(dry_run)
        self.confirm_sync = confirm_sync      # (prompt) -> bool, runs on the main thread
        self.speak = speak                    # unused here; voice mode speaks replies itself
        self.last_query = ""
        self.pending_choice = None             # ("Panel or widget?" choice, asked at): the next request may answer it
        self.confirm_q = queue.Queue()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        from core.brain import Brain, is_usage_question
        self.is_usage_question = is_usage_question
        self.brain = Brain(cfg, self._confirm_async, self._on_tool, dry_run=dry_run, log=log)
        self.router = None
        self.watch = None                      # the last local action, until it's judged (core/router_learn.py)
        self.watch_lock = threading.Lock()
        self._resolved = None                  # (tool, args) of the one alchemos call the last request came to, if any
        self.learning = []                     # learn() threads; text mode waits for them before exiting
        # The ORRIN app (core/appserver.py, voice mode only): voice and typed requests take turns on
        # one brain, every exchange is recorded in a thread, and tool labels / confirmations reach the app.
        from core.conversations import Confirmations, Conversations
        self.notify = lambda ev: None          # set by AppBridge once the socket is up
        self.status = None                     # core.status.Status (voice mode): the widgets' state file
        self.turn_lock = threading.RLock()
        self.surface = "voice"                 # who's asking right now: voice (HUD toast) | typed (app only)
        self.busy = False
        self.conv = Conversations(lambda ev: self.notify(ev))
        self.confirms = Confirmations(lambda ev: self.notify(ev))
        try:                                   # load once, keep warm (≈0.2 s with cached vectors)
            from core.router_local import LocalRouter
            self.router = LocalRouter(cfg, log=log)
            self.router.warm()
            if not dry_run:                    # tidy + re-check candidates (runs the gate) without delaying startup
                th = threading.Thread(target=self.router.settle, daemon=True)
                th.start()
                self.learning.append(th)
        except Exception as e:                 # no model files and offline, bad intents.json…: Claude only
            log(f"ORRIN: local router unavailable ({type(e).__name__}: {e}); using Claude only")

    # Brain (asyncio thread) asks; the main thread answers (it owns the mic / terminal)
    async def _confirm_async(self, prompt):
        fut = self.loop.create_future()
        self.confirm_q.put((prompt, lambda ok: self.loop.call_soon_threadsafe(fut.set_result, ok)))
        return await fut

    def _on_tool(self, label):
        log(f"  ◆ {label}")
        trace.t("tool", label=label)
        if self.surface == "voice":
            hud.tool(label)
        self.notify({"ev": "tool", "label": label})

    def warm(self):
        """Start the Claude client now so the first question is fast."""
        return asyncio.run_coroutine_threadsafe(self.brain.connect(), self.loop)

    def run_steps(self, steps, confirm=None):
        """Fast-path steps → (spoken text, tool log). Confirmations first, one at a
        time; then the approved steps run side by side ("theme X and dim the lights"
        costs the slower of the two, not the sum)."""
        confirm = confirm or self.confirm_sync
        said, tools, approved = [], [], []
        for s in steps:
            if s["tool"] is None:
                continue
            self._on_tool(A.tool_label(s["tool"], s["args"]))
            prompt = A.confirmation_prompt(s["tool"], s["args"])
            if prompt and not confirm(prompt):
                s["declined"] = True
            else:
                approved.append(s)
        with ThreadPoolExecutor(max_workers=4) as pool:
            results = dict(zip(map(id, approved), pool.map(lambda s: A.TOOLS[s["tool"]](**s["args"]), approved)))
        for s in steps:
            if s["tool"] is None:
                said.append(s["say"])
                continue
            call = f"{s['tool']}({', '.join(f'{k}={v}' for k, v in s['args'].items())})"
            if s.get("declined"):
                tools.append(call + " [declined]")
                said.append("Very well, sir.")
                continue
            r = results[id(s)]
            tools.append(call + ("" if r.get("ok") else " [failed]"))
            if self.dry_run:
                log(f"  [dry-run] {r.get('would') or r.get('error') or r}")
            if not r.get("ok"):
                said.append(r.get("say") or f"I couldn't: {r.get('error', 'unknown error')}.")
            elif callable(s["say"]):
                said.append(s["say"](r))
            else:
                said.append(s["say"])
        if len(steps) > 1 and all(not callable(s["say"]) for s in steps) and not any("couldn't" in x or "Very well" in x for x in said):
            return "Done, sir.", tools
        return " ".join(said), tools

    def handle(self, text, wait=None, on_sentence=None, source="voice", confirm=None):
        """One request → reply text. wait(future) blocks until the Claude future is done
        (voice mode watches the mic for barge-in meanwhile); returns None if interrupted.
        on_sentence(s): Claude's reply as it streams, one sentence at a time.
        source: voice | typed | cli. confirm(prompt) → bool answers this request's questions
        (default: confirm_sync, i.e. out loud). The exchange is recorded in the current thread.
        self.error: why it failed (a key of ERROR_LABELS), "" if it didn't."""
        from core.conversations import NEW_TOPIC
        if NEW_TOPIC.match(text):                 # "new topic" / "new chat": a fresh thread, nothing recorded
            self.conv.new()
            self.brain.history = ""
            asyncio.run_coroutine_threadsafe(self.brain.reset(), self.loop)
            return "Fresh start, sir."
        with self.turn_lock:
            carry = self.conv.carry_on()
            if carry and not self.brain.history:  # same thread, but Claude's context has dropped since
                self.brain.history = carry
            self.surface = "typed" if source == "typed" else "voice"
            self.busy = True
            self.notify({"ev": "busy", "on": True, "source": source, "text": text})
            reply = None
            try:
                reply = self._handle(text, wait, on_sentence, confirm or self.confirm_sync)
                return reply
            finally:
                try:
                    self.conv.record(text, source, reply if reply is not None else "(interrupted)",
                                     self._last_tools, self._last_tier)
                except Exception as e:
                    log(f"ORRIN: thread record failed: {e}")
                if self.status:
                    try:
                        self.status.last(text, reply, self._last_tier, source)
                        self.status.usage(self.brain)
                    except Exception as e:
                        log(f"ORRIN: status: {e}")
                self.busy = False
                self.notify({"ev": "busy", "on": False})
                self.surface = "voice"

    def _thinking(self):
        if self.surface == "voice":
            hud.thinking()

    def _handle(self, text, wait, on_sentence, confirm):
        t0 = time.monotonic()
        self.error = ""
        self._last_tools, self._last_tier = [], ""
        if STOP_CONTROL.match(text) and (control.active() or control.stopped_recently(20)):
            control.stop_all("voice")
            self._last_tier = "control:stop"
            return "Stopped, sir. I've let go of the window."
        self._resolved = None
        prev = self._take_watch()             # the local action just before this, if it's still being judged
        if prev and (c := self._correction(text, prev)):
            if c[0] != "meant":
                self._last_tier = "router:correction"
                reply = "My mistake, sir. I won't take those words that way again."
                self._log_action(text, "router:correction", [], reply, int((time.monotonic() - t0) * 1000))
                return reply
            reply = self._handle(c[1], wait, on_sentence, confirm)       # "no, I meant X": do X
            if self._resolved:                                         # … and learn that the first words meant X
                self._bg(lambda r=self._resolved: self.router.learn(prev["raw"], r[0], r[1], source="correction"))
            return reply
        steps = self._choice_answer(text)
        if steps is None:
            steps = fastpath.match(text, self.last_query)
            if steps and steps[0].get("choice"):
                steps = self._panel_or_widget(text, steps)
        if steps is not None:
            trace.t("route", to="fast", steps=",".join(s["tool"] or "say" for s in steps))
            reply, tools = self.run_steps(steps, confirm)
            tier = "fast"
        elif self.is_usage_question(text) and not fastpath.is_integration_intent(text):
            trace.t("route", to="usage")
            self._thinking()
            self._on_tool("CLAUDE USAGE")
            reply, tools = asyncio.run_coroutine_threadsafe(self.brain.usage_report(), self.loop).result(), ["usage"]
            tier = "usage"
        elif (d := self.route_local(text)) and (d.path == "local" or (d.path == "ask" and self._ask(d, confirm))):
            trace.t("route", to=d.path, intent=d.intent, score=d.top3[0][1], ms=d.ms)
            steps = d.steps
            reply, tools = self.run_steps(steps, confirm)
            tier = f"{d.path}:{d.intent}"
            self._after_local(text, d, tools)
        else:
            trace.t("route", to="claude", **({"why": d.path.split(":", 1)[1]} if d else {}))
            self._thinking()
            self.last_query = text
            src = "typed" if self.surface == "typed" else "voice"
            fut = asyncio.run_coroutine_threadsafe(self.brain.ask(text, on_sentence, source=src), self.loop)
            r = wait(fut) if wait else self.wait_text(fut, confirm)
            if r is None or r.interrupted:
                self._last_tools, self._last_tier = (r.tools if r else []), "claude:interrupted"
                self._log_action(text, "claude:interrupted", r.tools if r else [], "", int((time.monotonic() - t0) * 1000))
                return None
            reply, tools = r.text, r.tools
            tier = r.tier if not r.error else f"error:{r.error}"
            self.error = r.error
            if not r.error and len(r.calls) == 1 and r.calls[0][0] == "alchemos" and not _refused(tools):
                self._resolved = (r.calls[0][1], r.calls[0][2])
            if d and not r.error:
                self._learn(text, d, r)
        if steps is not None and any(t.endswith("[failed]") for t in tools):
            self.error = "tool"
        if steps is not None and len([s for s in steps if s["tool"]]) == 1 and not _refused(tools):
            s = next(s for s in steps if s["tool"])
            self._resolved = (s["tool"], dict(s["args"]))
        if prev:
            self._judge_next(prev, text, d if tier.startswith(("local:", "ask:")) else None, self._resolved)
        ms = int((time.monotonic() - t0) * 1000)
        self._last_tools, self._last_tier = tools, tier
        self._log_action(text, tier, tools, reply, ms)
        log(f"  [{tier} · {ms} ms]")
        trace.t("reply", tier=tier, ms=ms, tools=len(tools), text=reply)
        return reply

    # "put music on monitor 2": the screen's panel (set_screen_role) or a widget? Asked once per phrasing;
    # the answer is learned by the router (learned_intents.json), so the same words act straight away next time.
    def _panel_or_widget(self, text, steps):
        c = steps[0]["choice"]
        known = self.router.known_intent(text) if self.router else None
        if known in ("screen.role", "choice.panel"):
            return c["panel"]
        if known and (known.startswith("widget.") or known == "choice.widget"):
            return c["widget"]
        self.pending_choice = (c, time.monotonic())
        return steps                           # "Panel or widget, sir?"

    def _choice_answer(self, text):
        """The reply to "Panel or widget?" → the chosen steps (and teach the router); None if it isn't one."""
        pend, self.pending_choice = self.pending_choice, None
        if not pend or time.monotonic() - pend[1] > CHOICE_TTL_S:
            return None
        pick = fastpath.choice_answer(text)
        if not pick:
            return None
        c = pend[0]
        steps = c[pick]
        if self.router and not self.dry_run and len(steps) == 1:
            s = steps[0]
            th = threading.Thread(target=lambda: self.router.remember_choice(c["text"], pick, s["tool"], s["args"]),
                                  daemon=True)
            th.start()
            self.learning.append(th)
        return steps

    def route_local(self, text):
        """The local router's decision, or None when it's off (Settings → ORRIN → DECISIONS) or not loaded."""
        if not self.router or self.cfg["orrinDecisions"] != "local":
            return None
        try:
            return self.router.decide(text)
        except Exception as e:
            log(f"ORRIN: local router failed: {type(e).__name__}: {e}")
            return None

    def _learn(self, text, d, r):
        """Claude answered with exactly one alchemos tool call that went through: evidence for the intent that
        covers it (core/router_learn.py decides whether it ever goes live)."""
        if (self.dry_run or d.path in ("claude:claude-only", "claude:empty") or len(r.calls) != 1
                or _refused(r.tools) or len(r.tools) != 1):
            return
        server, tool, args = r.calls[0]
        if server != "alchemos":
            return
        self._bg(lambda: self.router.learn(text, tool, args))

    # ── learning from him (core/router_learn.py): what happens right after a local action ──
    def _bg(self, fn):
        def run():
            try:
                fn()
            except Exception as e:
                log(f"ORRIN: router learning: {type(e).__name__}: {e}")
        th = threading.Thread(target=run, daemon=True)
        th.start()
        self.learning = [t for t in self.learning if t.is_alive()] + [th]

    def _ask(self, d, confirm):
        """A near miss: "Did you mean …?" Yes runs it and counts as a confirm for these words; no sends the
        request to Claude and teaches nothing."""
        ok = bool(confirm(d.ask))
        if not self.dry_run:
            info = d.info()
            self._bg(lambda: self.router.outcome(info, "ask_yes" if ok else "ask_no", "asked"))
            if ok:
                self._bg(lambda: self.router.add_evidence(info["intent"], info["text"], "ask", confirm=True))
        return ok

    def _after_local(self, text, d, tools):
        """A local action ran: a declined confirmation is a negative now; otherwise watch what comes next."""
        if self.dry_run or not self.router:
            return
        if any("[declined]" in t for t in tools):
            info = d.info()
            self._bg(lambda: self.router.outcome(info, "neg", "declined"))
            return
        if any(t.endswith("[failed]") for t in tools):
            return
        w = {"info": d.info(), "raw": text, "ts": time.monotonic(), "wall": time.time()}
        w["timer"] = threading.Timer(L_OUTCOME_S, self._expire, args=(w,))
        w["timer"].daemon = True
        with self.watch_lock:
            old, self.watch = self.watch, w
        if old:
            old["timer"].cancel()
            self._bg(lambda: self._finish(old))
        w["timer"].start()

    def _take_watch(self):
        """The previous local action if it's still within its 30 s (it's judged by this request), else None."""
        if not self.router or self.dry_run:
            return None
        with self.watch_lock:
            w, self.watch = self.watch, None
        if not w:
            return None
        w["timer"].cancel()
        if time.monotonic() - w["ts"] > L_OUTCOME_S:
            self._bg(lambda: self._finish(w))
            return None
        return w

    def _expire(self, w):
        with self.watch_lock:
            if self.watch is not w:
                return
            self.watch = None
        self._finish(w)

    def _finish(self, w):
        """No correction came: a weak positive, unless the kill switch went after it."""
        try:
            stopped = control.STOP_FLAG.stat().st_mtime > w["wall"]
        except OSError:
            stopped = False
        self.router.outcome(w["info"], "neg" if stopped else "pos", "kill-switch" if stopped else "weak-positive")

    def _correction(self, text, prev):
        """ "undo" / "that's wrong" / "no, I meant X" right after a local action → (kind, X), and the
        action counts as a negative."""
        from core import router_learn as L
        from core.router_local import clean
        c = L.correction(clean(text))
        if c:
            info = prev["info"]
            self._bg(lambda: self.router.outcome(info, "neg", "undo" if c[0] == "undo" else "correction"))
        return c

    def _judge_next(self, prev, text, d, resolved):
        """The request after a local action: the opposite command within 10 s, or the same request reworded
        that came to a different intent, means the local action was wrong (and the reword teaches the right
        one). Anything else: the local action stood."""
        from core import router_learn as L
        dt = time.monotonic() - prev["ts"]

        def judge():
            info = prev["info"]
            now = d.intent if d else (self.router.intent_for_call(text, *resolved) if resolved else None)
            why = None
            if now and now != info["intent"]:
                if L.INVERSE.get(info["intent"]) == now and dt <= L.INVERSE_S:
                    why = "inverse"
                elif self.router.similarity(text, prev["raw"]) >= REWORD_SIM:
                    why = "reworded"
            if not why:
                self._finish(prev)
                return
            self.router.outcome(info, "neg", why)
            if why == "reworded" and resolved:
                self.router.learn(prev["raw"], resolved[0], resolved[1], source="correction")
        self._bg(judge)

    def _log_action(self, *row):
        """SQLite write off the critical path (it was ~50 ms before the reply could play)."""
        def write():
            try:
                db.log_action(*row)
            except Exception as e:
                log(f"ORRIN: log failed: {e}")
        threading.Thread(target=write, daemon=True).start()

    def wait_text(self, fut, confirm=None):
        confirm = confirm or self.confirm_sync
        while True:
            try:
                prompt, answer = self.confirm_q.get(timeout=0.05)
                answer(confirm(prompt))
            except queue.Empty:
                pass
            if fut.done():
                return fut.result()


# ── Text mode ──────────────────────────────────
def text_mode(args):
    cfg = C.Config()
    hud.ENABLED = not args.no_hud

    def confirm(prompt):
        log(f"  ? {prompt}")
        hud.confirm(prompt)
        if args.confirm in ("yes", "no"):
            log(f"  > {args.confirm}")
            return args.confirm == "yes"
        if sys.stdin.isatty():
            return is_yes(input("  > "))
        return False

    j = Orrin(cfg, dry_run=args.dry_run, confirm_sync=confirm)
    voice = None
    if args.speak:
        from core.voice import Voice
        voice = Voice(cfg)
    for request in args.text:
        log(f'> {request}')
        hud.transcript(request)
        reply = j.handle(request, source="cli")
        if reply:
            log(f"ORRIN: {reply}")
            hud.reply(reply)
            if voice:
                voice.speak(reply)
    for th in j.learning:                     # onnxruntime aborts if the interpreter exits mid-inference
        th.join(10)
    asyncio.run_coroutine_threadsafe(j.brain.disconnect(), j.loop).result(10)


# ── Voice mode ─────────────────────────────────
class Mic:
    """pw-record → 80 ms chunks on a queue (a reader thread keeps the pipe drained).

    Which microphone: Settings → ORRIN → INPUT DEVICE (orrinMic):
      "auto"     the laptop's digital mic, always: the headset stays plugged in most of the time, so its
                 mic is used only when it's picked here by name (and a Bluetooth one would switch the
                 headphones from A2DP to call quality for as long as Orrin listens)
      "default"  (or "") the system default input
      a node     that PipeWire source (e.g. the headset), while it exists (else AUTO's pick)
    A watcher (pactl subscribe, no polling) re-picks on any source / card change and every few
    seconds for a settings change; a new pick restarts pw-record in place. The queue isn't flushed,
    and the voice loop's 2 s pre-wake buffer lives in VoiceLoop, so neither is lost."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.target = None            # node pw-record is on ("" = default input)
        self.on = False               # wanted running (False while paused for combat mode)
        self.q = queue.Queue(maxsize=400)
        self._lock = threading.RLock()
        self._kick = threading.Event()
        self._deaths = []
        self.status_cb = None         # called with (setting, node, label) after each (re)start
        self._watching = False

    # ── which source ──
    def pick(self):
        """→ (node name or "" for the default input, label)."""
        import audio_devices as AD
        want = str(self.cfg["orrinMic"] or "").strip()
        if want.lower() in ("", "default"):
            return "", "system default"
        devs = [d for d in AD.devices("in") if d["available"]]
        if want.lower() != "auto":
            hit = next((d for d in devs if d["name"] == want), None)
            if hit:
                return hit["name"], hit["label"]
        dmic = [d for d in devs if d["kind"] == "laptop"]
        dmic.sort(key=lambda d: not re.search(r"digital|mic1", d["name"] + d["label"], re.I))
        if dmic:
            return dmic[0]["name"], dmic[0]["label"]
        return "", "system default"

    def start(self):
        with self._lock:
            self.on = True
            if not self._watching:
                self._watching = True
                threading.Thread(target=self._watch, daemon=True).start()
            if self.proc:
                return
            self._spawn()

    def _spawn(self):
        try:
            target, label = self.pick()
        except Exception as e:
            log(f"ORRIN: mic pick failed ({type(e).__name__}: {e}); using the default input")
            target, label = "", "system default"
        # --raw: without it pw-record ≥ 1.6.10 writes an AU stream to stdout (header + big-endian)
        cmd = ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16",
               "-P", "media.name=Orrin wake word"]
        if target:
            cmd += ["--target", target]
        self.target = target
        self.proc = subprocess.Popen(cmd + ["-"], stdout=subprocess.PIPE)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()
        log(f"ORRIN: microphone → {label}")
        trace.t("mic", node=target or "default", label=label)
        if self.status_cb:
            try:
                self.status_cb(str(self.cfg["orrinMic"] or "auto"), target, label)
            except Exception:
                pass

    def _kill(self):
        p, self.proc = self.proc, None
        if p:
            p.terminate()
            try:
                p.wait(3)
            except subprocess.TimeoutExpired:
                p.kill()

    def stop(self):
        with self._lock:
            self.on = False
            self._kill()
        self.flush()

    def restart(self, why=""):
        """Switch pw-record to the current pick (nothing happens if it's the same source)."""
        with self._lock:
            if not self.on:
                return
            try:
                target, _ = self.pick()
            except Exception:
                return
            if self.proc and self.proc.poll() is None and target == self.target:
                return
            log(f"ORRIN: microphone change ({why or 'device change'})")
            self._kill()
            self._spawn()

    def flush(self):
        while not self.q.empty():
            self.q.get_nowait()

    def _watch(self):
        """Device events from `pactl subscribe` → debounce → restart(); settings checked every 3 s."""
        def events():
            while True:
                try:
                    p = subprocess.Popen(["pactl", "subscribe"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                    for line in p.stdout:
                        if re.search(r"'(?:new|remove|change)' on (?:source|card|server)", line) and "source-output" not in line:
                            self._kick.set()
                    p.wait()
                except OSError:
                    pass
                time.sleep(5)            # PipeWire restarting: subscribe again
        threading.Thread(target=events, daemon=True).start()
        last_setting = None
        while True:
            fired = self._kick.wait(3.0)
            setting = (self.cfg["orrinMic"], self.cfg["orrinMicBluetooth"])
            if fired:
                time.sleep(1.0)          # a dock / headset brings several events: settle first
                self._kick.clear()
                self.restart("device plugged / unplugged")
            elif last_setting is not None and setting != last_setting:
                self.restart("Settings → INPUT DEVICE")
            last_setting = setting

    def _reader(self, proc):
        import numpy as np
        n = CHUNK * 2
        while True:
            data = proc.stdout.read(n)
            if not data or len(data) < n:
                if self.proc is proc and self.on:     # not a deliberate stop: the source went away?
                    now = time.monotonic()
                    self._deaths = [t for t in self._deaths if now - t < 30] + [now]
                    if len(self._deaths) > 3:
                        log("ORRIN: microphone stream keeps ending")
                        os._exit(1)                   # systemd restarts Orrin (Restart=on-failure)
                    log("ORRIN: microphone stream ended, picking again")
                    threading.Thread(target=self._respawn, args=(proc,), daemon=True).start()
                return
            try:
                self.q.put(np.frombuffer(data, dtype=np.int16), timeout=1)
            except queue.Full:
                pass

    def _respawn(self, dead):
        time.sleep(0.5)
        with self._lock:
            if self.proc is dead and self.on:
                self.proc = None
                self._spawn()

    def read(self, timeout=1.0):
        try:
            return self.q.get(timeout=timeout)
        except queue.Empty:
            return None


def _db(x):
    import numpy as np
    if not len(x):
        return -99.0
    return round(20 * np.log10(max(1.0, float(np.sqrt(np.mean(np.square(x.astype(np.float64))))))) - 90.3, 1)


class VoiceLoop:
    def __init__(self):
        self.cfg = C.Config()
        self.mic = Mic(self.cfg)
        self.paused = False
        self.barge = False
        self.last_reminder_check = 0.0
        self.last_academic_check = 0.0
        from collections import deque
        self.pre = deque(maxlen=int(2.0 * RATE / CHUNK))   # the last 2 s before the wake word
        self.bg = queue.Queue()                           # ("ask", Pending) | ("say", title, line): tasks / watchers, while idle
        self.owed = threading.Event()                     # a task stored a line to say (core.tasks.Announcer)
        self.owed.set()                                   # lines owed from before a restart
        self.last_owed_check = 0.0
        self.announcer = None
        self.near = 0.0                                   # peak of a wake score that didn't reach THRESHOLD
        self.spec = None                                  # listen()'s early transcription, if still valid
        self.thresholds = {WAKEWORD: THRESHOLD}           # per wake model (load() adds the custom words)
        self.woke_as = None
        self.woke_model, self.woke_raw, self.wake_clip = "", 0.0, None

    def load(self):
        import openwakeword
        from openwakeword.model import Model
        from openwakeword.vad import VAD
        from core.voice import Voice
        if C.LAPTOP:
            log("ORRIN: laptop mode (switched on undocked): no academic sync, watchers or room speaker")
        log("ORRIN: loading models…")
        openwakeword.utils.download_models([WAKEWORD])
        from core import wake
        models, self.thresholds, verifiers = [WAKEWORD], {WAKEWORD: THRESHOLD}, {}
        for w in wake.installed():
            models.append(w["path"])
            self.thresholds[w["name"]] = w["threshold"]
            WAKE_PERSONA[w["name"]] = w["persona"]
            if w["verifier"]:
                verifiers[w["name"]] = w["verifier"]
            log(f"ORRIN: wake word {w['name']} loaded for {w['persona']} (threshold {w['threshold']}"
                f"{', custom verifier' if w['verifier'] else ''})")
        kw = {"custom_verifier_models": verifiers, "custom_verifier_threshold": wake.VERIFIER_THRESHOLD} if verifiers else {}
        self.wake = Model(wakeword_models=models, inference_framework="onnx", **kw)
        self.woke_model, self.woke_raw = "", 0.0   # which model fired last, at what score of its own
        self.wake_clip = None          # trace.save_wake() file of this wake (renamed if it was a false wake)
        self.woke_as = None            # persona the last wake word named (None: only "hey Jarvis" is known)
        self.vad = VAD()
        self.stt = hearing.STT(WHISPER_MODEL)
        self.voice = Voice(self.cfg, log=log, prewarm=True)
        self.voice.progress = lambda start, end, total, ms: (hud.speech_done() if start is None
                                                             else hud.speak(start, end, total, ms))
        self.voice.warm()
        A.apps()
        self.j = Orrin(self.cfg, confirm_sync=self.confirm)
        from core.status import Status
        self.status = self.j.status = Status(log=log)
        self.mic.status_cb = self.status.mic
        self.status.set("wake", list(dict.fromkeys(["orrin"] + [WAKE_PERSONA[k] for k in self.thresholds if k != WAKEWORD])))
        atexit.register(self.status.close)
        try:
            self.status.usage(self.j.brain)
        except Exception as e:
            log(f"ORRIN: status: {e}")
        self.j.warm()
        try:
            self.app = AppBridge(self)
        except Exception as e:                 # the console is optional: voice keeps working without it
            log(f"ORRIN: app socket unavailable: {type(e).__name__}: {e}")
        try:
            from core.dj import DJ
            self.dj = DJ(self.cfg, log=log)    # DJ mode: follows Spotify, hands lines to check_dj
        except Exception as e:
            self.dj = None
            log(f"ORRIN: DJ unavailable: {type(e).__name__}: {e}")

    # ── hearing ──
    def read(self, timeout):
        """Next mic chunk; the last 2 s are kept so a command said in the same breath as
        "hey Jarvis" (waking it or interrupting it) keeps its first words."""
        a = self.mic.read(timeout)
        if a is not None:
            self.pre.append(a)
        return a

    def woke(self, a, where="idle"):
        """Score of a wake word that fired (0.0 if none); self.woke_as = the persona it named. Each model is
        judged against its own threshold (over Orrin's own voice: scaled down like BARGE_THRESHOLD)."""
        preds = self.wake.predict(a)
        scale = 1.0 if where in ("idle", "listening") else BARGE_THRESHOLD / THRESHOLD
        rel = {k: v / (self.thresholds.get(k, THRESHOLD) * scale) for k, v in preds.items()}
        best = max(rel, key=rel.get)
        score = preds[best] * THRESHOLD / self.thresholds.get(best, THRESHOLD)    # in "hey Jarvis" units
        if rel[best] >= 1.0:
            self.woke_as = WAKE_PERSONA.get(best) if len(preds) > 1 else None
            self.woke_model, self.woke_raw = best, float(preds[best])
            if where != "idle":
                trace.t("barge", during=where, score=round(score, 2))
            self.near = 0.0
            return score
        if score >= NEAR_MISS:
            self.near = max(self.near, score)
        elif self.near:                     # a near miss just ended
            trace.t("wake.near", score=round(self.near, 2), during=where, threshold=THRESHOLD)
            if where == "idle":
                import numpy as np
                trace.save("near", np.concatenate(list(self.pre)))
            self.near = 0.0
        return 0.0

    def listen(self, no_speech_s, kind="command", pre=(), stop=None):
        """Record one command → float32 audio, or None if nothing was said.
        A fresh "hey Jarvis" in the middle starts the command over from there.
        stop(): checked every chunk; True ends listening with nothing heard (answered in the app)."""
        import numpy as np
        from collections import deque
        trace.t("listen", kind=kind, wait=no_speech_s)
        ep = hearing.Endpointer(self.vad, no_speech_s, pre)
        recent = deque(list(pre)[-int(hearing.PRE_ROLL_S * RATE / CHUNK):], maxlen=int(hearing.PRE_ROLL_S * RATE / CHUNK))
        if pre and ep.speech:
            trace.t("vad.start", at=0, p=round(max(ep.probs or [1.0]), 2), via="pre-roll")
        restarts = 0
        spec = None                          # (frames it covers, future)
        while True:
            a = self.read(2.0)
            if a is None:
                why = "mic-stalled"
                break
            if stop and stop():
                why = "answered-elsewhere"
                ep.speech = False
                break
            recent.append(a)
            if ep.elapsed > 0.3 and restarts < 2 and self.woke(a, "listening"):
                restarts += 1                # "hey Jarvis … (pause) … pause music": start again from here
                self.wake.reset()
                self.voice.chime()
                hud.listening()
                ep = hearing.Endpointer(self.vad, NO_SPEECH_TIMEOUT_S, list(recent))
                continue
            was = ep.speech
            why = ep.feed(a)
            if ep.speech and not was:
                trace.t("vad.start", at=round(ep.elapsed, 2), p=round(ep.probs[-1], 2))
            if ep.speech and ep.last == len(ep.frames):
                trace.mark("speech_end")
                spec = None                  # still talking: any early guess is stale
            elif ep.speech and spec is None and ep.silent >= hearing.SPECULATE_S and kind != "confirm":
                spec = (ep.last, self.stt.speculate(ep.audio().astype(np.float32) / 32768.0))
            if why:
                break
        audio = ep.audio()
        step = CHUNK / RATE
        voiced = np.concatenate(ep.frames[ep.first:ep.last]) if ep.speech else audio
        trace.t("vad.end", reason=why, len=round(ep.elapsed, 2),
                speech=round((ep.last - ep.first) * step, 2) if ep.speech else 0,
                p_max=round(max(ep.probs, default=0), 2), level_db=_db(audio[ep.n_pre * CHUNK:]), voice_db=_db(voiced))
        saved = trace.save(kind, audio)
        if saved:
            trace.t("saved", file=saved.name)
        self.spec = spec[1] if spec and spec[0] == ep.last and why == "silence" else None
        return audio.astype(np.float32) / 32768.0 if ep.speech else None

    def transcribe(self, audio, spec=None, barged=False):
        """→ (command with any "hey Jarvis" removed, raw transcript). spec: listen()'s early
        transcription of the same speech, if it's still valid."""
        if spec is not None:
            raw, info = spec.result()
            info["early"] = True
        else:
            raw, info = self.stt.transcribe(audio)
        text = hearing.correct(hearing.strip_wake(raw, anywhere=barged))
        trace.t("stt", model=WHISPER_MODEL, audio_s=round(len(audio) / RATE, 2), text=raw,
                **({"command": text} if text != raw else {}), **info)
        return text, raw

    # ── speaking ──
    def play(self, u, where="speaking"):
        """Wait for an Utterance to finish while watching for "hey Jarvis". True if interrupted."""
        self.wake.reset()
        self.pre.clear()
        interrupted = False
        while not u.done.is_set():
            a = self.read(0.2)
            if a is not None and not interrupted and self.woke(a, where):
                log("ORRIN: interrupted while speaking")
                interrupted = True
                u.stop()
        self.wake.reset()
        if u.fell_back:
            hud.note("SPEAKER UNREACHABLE → LAPTOP")
        return interrupted

    def say(self, text):
        """Speak while watching for "hey Jarvis". True if it interrupted."""
        hud.reply(text)
        if not self.cfg["orrinSpeak"]:
            return False
        u = self.voice.utterance()
        u.add(text)
        u.finish()
        return self.play(u)

    def fail(self, why, line):
        """Something went wrong after the chime: say so, and show why."""
        trace.t("fail", why=why, line=line)
        log(f"ORRIN: {ERROR_LABELS.get(why, why)} — {line}")
        hud.error(ERROR_LABELS.get(why, why.upper()), line)
        if self.cfg["orrinSpeak"]:
            u = self.voice.utterance()
            u.add(line)
            u.finish()
            self.play(u)

    def confirm(self, prompt):
        log(f"  ? {prompt}")
        hud.confirm(prompt)
        if self.cfg["orrinSpeak"]:
            u = self.voice.utterance()
            u.add(spoken_prompt(prompt))
            u.finish()
            self.play(u)
        self.mic.flush()
        audio = self.listen(CONFIRM_TIMEOUT_S, kind="confirm")
        answer = self.transcribe(audio)[0] if audio is not None else ""
        log(f'  > "{answer}"')
        ok = is_yes(answer) or bool(ALLOW_TASK.search(answer.lower()))
        if ok:
            hud.thinking()
        return ok

    def wait(self, fut, u=None):
        """Wait for Claude, answering confirmations; "hey Jarvis" interrupts (and silences
        any sentences it has already started saying)."""
        self.wake.reset()
        self.pre.clear()
        while True:
            try:
                prompt, answer = self.j.confirm_q.get_nowait()
                answer(self.confirm(prompt))
                self.wake.reset()
            except queue.Empty:
                pass
            if fut.done():
                return fut.result()
            a = self.read(0.1)
            if a is not None and self.woke(a, "thinking"):
                log("ORRIN: interrupted while thinking")
                if u:
                    u.stop()
                asyncio.run_coroutine_threadsafe(self.j.brain.interrupt(), self.j.loop)
                try:
                    fut.result(5)
                except Exception:
                    pass
                self.wake.reset()
                self.barge = True
                return None

    def check_persona(self):
        """The default persona changed from outside (Settings, `qs ipc call orrin persona …`, a Claude
        tool call): the new one introduces itself, in its own voice."""
        who = persona.switched(self.cfg)
        if not who:
            return
        log(f"ORRIN: persona → {who}")
        self.voice.warm()                         # her stock lines, in her voice
        if self.paused:
            return
        hud.answering("")
        self.say(persona.announce_line(who))
        hud.idle()

    def check_combat(self):
        want = self.cfg["gameOrrin"] and A.combat_mode()
        if want != self.paused:
            self.paused = want
            if want:
                log("ORRIN: combat mode, wake word paused")
                self.mic.stop()
            else:
                log("ORRIN: combat mode over, listening again")
                self.mic.start()
                self.wake.reset()
            hud.paused(want)

    def check_dj(self):
        """A DJ line (core/dj.py), said between conversations with the music faded to DUCK_DJ and back.
        Never in combat mode, never while a Discord (or other) call has the mic, never with spoken
        replies off. It plays on the sink Spotify is playing on; when Spotify is on another Connect
        device (the Google Home), that device's volume is lowered through the Web API instead."""
        dj = getattr(self, "dj", None)
        if not dj:
            return
        item = dj.pop_line()
        if not item:
            return
        import audio_devices as AD
        why = ("combat" if self.paused or A.combat_mode() else "call" if AD.voice_call()
               else "spoken replies off" if not self.cfg["orrinSpeak"] else "")
        if why:
            trace.t("dj.quiet", why=why)
            log(f"ORRIN: DJ line skipped ({why}): {item['text']}")
            return
        from core.voice import DJ_RAMP_S, DUCK_DJ
        idx, sink = AD.music_stream()
        remote = dj.duck_remote(DUCK_DJ) if idx is None else None
        log(f"ORRIN: DJ: {item['text']}")
        trace.t("dj.line", kind=item["kind"], sink=sink or "default", remote=bool(remote))
        hud.reply(item["text"])
        ducked = self.voice.ducker.duck(DUCK_DJ, ramp_s=DJ_RAMP_S) if idx is not None else False
        try:
            u = self.voice.utterance(target=sink)
            u.add(item["text"])
            u.finish()
            self.play(u, where="dj")
        finally:
            if ducked:
                self.voice.ducker.restore(ramp_s=DJ_RAMP_S, level=DUCK_DJ)
            if remote:
                remote()

    def check_reminders(self):
        now = time.time()
        if now - self.last_reminder_check < 1.0:
            return
        self.last_reminder_check = now
        try:
            due = db.due_reminders(now)
        except Exception as e:
            log(f"ORRIN: reminders: {e}")
            return
        for r in due:
            db.mark_fired(r["id"])
            late = now - r["due"] > 120
            if r["kind"] == "timer":
                msg = f"Your {r['text']} timer is done, sir." if r["text"] != "timer" else "Your timer is done, sir."
            else:
                msg = f"A reminder, sir: {r['text']}."
            if late:
                msg = f"While I was away, sir — {msg[0].lower()}{msg[1:]}"
            log(f"ORRIN: {msg}")
            hud.toast("TIMER" if r["kind"] == "timer" else "REMINDER", r["text"].upper())
            if not self.paused:
                self.say(msg)
            else:
                self.voice.speak(msg)

    def check_academic(self):
        """Grade notices and tracker updates queued by the academic sync ("Sir, your CS 137 A5 has been
        graded"), then one tracker offer (AUTO-UPDATE TRACKER off, or a change it wasn't sure of):
        asked out loud and on the HUD, written only on a yes. The voice loop only runs while docked,
        so they wait for the desk (and for combat mode to end)."""
        now = time.time()
        if now - self.last_academic_check < 60 or self.paused:
            return
        self.last_academic_check = now
        try:
            import academic
            import academic_sync
            lines = academic.pop_announcements()
        except Exception as e:
            log(f"ORRIN: academic: {e}")
            return
        for line in lines:
            log(f"ORRIN: {line}")
            hud.toast("LEARN" if "tracker" not in line else "TRACKER", line.upper())
            if not self.paused:
                self.say(line)
        try:
            offer = academic_sync.pop_tracker_offer()
        except Exception as e:
            log(f"ORRIN: tracker offer: {e}")
            return
        if offer:
            self.offer_tracker(offer)

    def check_background(self):
        """Task announcements, and a task's question asked out loud (the app can answer it too). Announcements
        are stored in the db by the task runner and said here when Orrin is free: in combat mode they wait,
        and a restart doesn't lose them (core.tasks.Announcer)."""
        if self.paused:
            return
        now = time.time()
        if self.owed.is_set() or now - self.last_owed_check > 30:
            self.owed.clear()
            self.last_owed_check = now
            if self.announcer is None:
                from core.tasks import Announcer
                self.announcer = Announcer(self.say, hud.toast, log=log)
            self.announcer.deliver()
        while True:
            try:
                item = self.bg.get_nowait()
            except queue.Empty:
                return
            if item[0] == "say":                          # a watcher's news (it pauses in combat mode itself)
                _, title, line = item
                log(f"ORRIN: {line}")
                hud.toast(title, line.upper()[:300])
                try:
                    self.say(line)
                except Exception as e:
                    log(f"ORRIN: couldn't say it: {type(e).__name__}: {e}")
            elif item[0] == "ask" and not item[1].answered:
                self.ask_pending(item[1])

    def ask_pending(self, p):
        """Ask a background task's question out loud. A clear yes / no answers it; silence leaves it
        waiting in the app."""
        self.voice.chime()
        prompt = f"For the {p.title.lower()} task: {p.prompt}" if p.title else p.prompt
        if p.allow_task:
            prompt = prompt.replace(" Go ahead, sir?", " Go ahead, sir? You can also say allow this task.", 1)
        log(f"  ? {prompt}")
        hud.confirm(prompt)
        if self.cfg["orrinSpeak"]:
            u = self.voice.utterance()
            u.add(spoken_prompt(prompt))
            u.finish()
            self.play(u)
        if p.answered:
            hud.idle()
            return
        self.mic.flush()
        audio = self.listen(CONFIRM_TIMEOUT_S, kind="confirm", stop=lambda: p.answered)
        answer = self.transcribe(audio)[0] if audio is not None else ""
        log(f'  > "{answer}"')
        if answer and not p.answered and p.allow_task and ALLOW_TASK.search(answer.lower()):
            self.j.confirms.answer(p.id, "task")
        elif answer and not p.answered and (is_yes(answer) or NO.search(answer.lower())):
            self.j.confirms.answer(p.id, is_yes(answer))
            self.say("Very good, sir." if is_yes(answer) else "Very well, sir.")
        else:
            hud.idle()

    def offer_tracker(self, offer):
        import tracker
        self.voice.chime()
        ok = self.confirm(offer["prompt"])
        if not ok:
            log("ORRIN: tracker offer declined")
            hud.idle()
            return
        if offer.get("calendar"):                # a sheet change AUTO-UPDATE made: its event, now he said yes
            try:
                import sheet_calendar
                cal, did = sheet_calendar.SheetCalendar(), []
                for before, after in offer["calendar"]:
                    did += cal.follow(tracker.row_from_json(before), tracker.row_from_json(after))["did"]
            except Exception as e:
                log(f"ORRIN: calendar follow failed: {type(e).__name__}: {e}")
                self.fail("tool", getattr(e, "say", None) or "I couldn't reach your calendar, sir.")
                return
            self.say(f"Done, sir: I {' and '.join(did)}." if did else "Its calendar event was already right, sir.")
            return
        try:
            t = tracker.Tracker()
            res = t.apply(offer["changes"], offer["source"], calendar=True)
        except Exception as e:
            log(f"ORRIN: tracker write failed: {type(e).__name__}: {e}")
            self.fail("tool", "I couldn't reach your tracker, sir.")
            return
        bad = [r for r in res if not r["ok"]]
        for r in bad:
            log(f"ORRIN: tracker: {r['error']}")
        for n in t.calendar_report["notes"]:
            log(f"ORRIN: tracker calendar: {n}")
        did = t.calendar_report["did"]
        self.say(bad[0]["say"] if bad else "Done, sir. It's in your tracker" + (f", and I {' and '.join(did)}." if did else "."))

    def _sync_loop(self):
        """Every SYNC_S while docked (this process only runs docked): the Outlook calendar link, the LEARN
        feed, grade notices in Gmail, and with AUTO-ADD the "STARK – Assignments" calendar
        (mcp/academic_sync.py). Off the main thread, so the wake word never waits on the network."""
        if C.LAPTOP:
            log("ORRIN: laptop mode: academic sync paused until docked")
            return
        time.sleep(30)
        while True:
            try:
                import academic_sync
                import outlook_ical
                if outlook_ical.url():
                    m = outlook_ical.fetch()
                    if not m.get("ok"):
                        log(f"ORRIN: Outlook calendar link: {m.get('error')}")
                if secrets.has("learn", "ical_url"):
                    r = academic_sync.sync(self.cfg, log=log)
                    busy = {k: v for k, v in r.items() if v and k != "learn"
                            and not (isinstance(v, dict) and set(v) == {"skipped"})} | (
                        {"learn": r["learn"]} if r.get("learn", {}).get("new") or r.get("learn", {}).get("changed") else {})
                    if busy:
                        log(f"ORRIN: academic sync {busy}")
            except Exception as e:
                log(f"ORRIN: sync failed: {type(e).__name__}: {e}")
            time.sleep(SYNC_S)

    # ── one exchange ──
    def converse(self):
        """Listen → answer → follow-ups. Returns when the conversation goes idle."""
        no_speech, kind, pre = NO_SPEECH_TIMEOUT_S, "command", list(self.pre)
        lone_wake = barged = False
        while True:
            self.barge = False
            audio = self.listen(no_speech, kind, pre)
            pre = ()
            clip, self.wake_clip = self.wake_clip, None    # only the first listen after the wake judges it
            if clip and audio is None:
                trace.mark_wake(clip, "false")                # woke, then silence
            if audio is None:
                if kind == "command":                # woke, then nothing: say so
                    self.fail("heard", NOT_HEARD)
                else:
                    trace.t("idle", why="no follow-up")
                    hud.idle()
                return
            hud.thinking()
            text, raw = self.transcribe(audio, self.spec, barged)
            barged = False
            log(f'ORRIN: heard "{raw}"')
            if clip and not re.search(r"\w", raw):
                trace.mark_wake(clip, "false")                # woke, then nothing Whisper could put in words
            clip = None
            if not re.search(r"\w", text):
                if raw and re.search(r"\w", raw) and not lone_wake:
                    lone_wake = True                 # just "hey Jarvis": wait for the command
                    trace.t("listen.again", why="only the wake word")
                    hud.listening()
                    no_speech, kind = NO_SPEECH_TIMEOUT_S, "command"
                    continue
                if kind == "command":
                    self.fail("heard", NOT_HEARD)
                else:
                    trace.t("idle", why="empty follow-up")
                    hud.idle()
                return
            lone_wake = False
            hud.transcript(text)
            # The output opens now (Bluetooth wakes while Orrin thinks); Claude's sentences go
            # into it as they stream in, so the first one plays before the reply is finished.
            speak = self.cfg["orrinSpeak"]
            u = self.voice.utterance(live=True) if speak else None      # Claude streams: per sentence
            streamed = []

            def on_sentence(sentence):
                streamed.append(sentence)
                if u:
                    u.add(sentence)
            reply = self.j.handle(text, wait=lambda fut: self.wait(fut, u), on_sentence=on_sentence)
            hud.answering(persona.current(self.cfg))   # "switch to Friday" changed who's talking mid-exchange
            if reply is None:            # interrupted by the wake word: listen afresh
                if u:
                    u.stop()
                if self.barge:
                    persona.begin(self.woke_as)
                    hud.answering(persona.current(self.cfg))
                    self.voice.chime()
                    hud.listening()
                    no_speech, kind, pre = NO_SPEECH_TIMEOUT_S, "command", list(self.pre)
                    barged = True
                    continue
                hud.idle()
                return
            if self.j.error:
                hud.error(ERROR_LABELS.get(self.j.error, self.j.error.upper()), reply)
                trace.t("fail", why=self.j.error, line=reply)
            else:
                hud.reply(reply)
            if u:
                if reply and not streamed:
                    u.add(reply)
                elif self.j.error and reply not in streamed:
                    u.add(reply)             # e.g. it stopped mid-answer: say why
                u.finish()
                if self.play(u):
                    persona.begin(self.woke_as)
                    hud.answering(persona.current(self.cfg))
                    self.voice.chime()
                    hud.listening()
                    no_speech, kind, pre = NO_SPEECH_TIMEOUT_S, "command", list(self.pre)
                    barged = True
                    continue
            follow = float(self.cfg["orrinFollowup"] or 0)
            if follow <= 0 or reply in ("Very good, sir.", "You're welcome, sir."):
                hud.idle()
                return
            hud.followup()
            self.mic.flush()
            no_speech, kind = follow, "followup"

    def run(self):
        open_log()
        from core import session
        ok, holder = session.take_lock()
        if not ok:
            # the service (orrin.service) already runs one; see `orrinctl status`
            log(f"ORRIN: another voice loop is running (pid {holder or '?'}); stop it with: orrinctl stop")
            sys.exit(3)
        self.load()
        self.voice.ducker.restore_leftover()      # a previous run stopped mid-reply: music back up

        def stop(signum=None, frame=None):        # service stop (toggle off, dock change, log-out): music back up
            self.voice.ducker.restore()
            hud.offline()
            os._exit(0)
        import signal
        signal.signal(signal.SIGTERM, stop)
        db.prune_log()
        atexit.register(hud.offline)

        sock = session.hyprland_socket()

        def heartbeat():
            # also the session guard: once our Hyprland is gone (log-out), stop cleanly (exit 0, so
            # systemd doesn't restart it). The HUD answers the first beat after a qs restart with
            # "resync" and gets the toast state back (core/hud.py).
            while True:
                if session.session_gone(sock):
                    log("ORRIN: Hyprland session ended, stopping")
                    stop()
                hud.online()
                time.sleep(5)
        threading.Thread(target=heartbeat, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()
        self.check_combat()
        if not self.paused:
            self.mic.start()
        from core import wake as _wake
        log("ORRIN: online — say " + " / ".join(f'"{_wake.SAY.get(k, k.replace("_", " "))}"' for k in self.thresholds))
        last, last_prune = 0.0, time.time()
        persona.switched(self.cfg)                # remember who's active now (a later change gets announced)
        while True:
            self.check_persona()
            self.check_reminders()
            self.check_academic()
            self.check_background()
            self.check_combat()
            self.check_dj()
            if self.paused:
                time.sleep(1)
                continue
            if time.time() - last_prune > 86400:
                db.prune_log()
                last_prune = time.time()
            a = self.read(1.0)
            if a is None:
                continue
            score = self.woke(a)
            if not score:
                continue
            if time.time() - last < COOLDOWN_S:
                trace.t("wake.skip", score=round(score, 2), why="cooldown")
                continue
            trace.begin()
            trace.t("wake", score=round(score, 2), queued=self.mic.q.qsize(), persona=self.woke_as or "",
                    model=self.woke_model, raw=round(self.woke_raw, 2))
            import numpy as np
            self.wake_clip = trace.save_wake(self.woke_model, self.woke_raw, np.concatenate(list(self.pre)))
            log("ORRIN: wake word" + (f" ({self.woke_as})" if self.woke_as else ""))
            self.wake.reset()     # else its buffer still holds "hey Jarvis" and fires again mid-reply
            persona.begin(self.woke_as)            # "hey Friday" → FRIDAY answers this exchange
            hud.answering(persona.current(self.cfg))
            self.voice.chime()
            govee_pulse()
            hud.listening()
            self.voice.speaker.prepare()   # connect the Bluetooth speaker while Trevor talks
            if self.cfg["orrinDuck"]:     # turn the music down so it isn't heard as the command
                from core.voice import DUCK_LISTEN
                threading.Thread(target=self.voice.ducker.duck, args=(DUCK_LISTEN,), daemon=True).start()
            try:
                self.converse()
            except Exception as e:
                import traceback
                trace.t("error", where="converse", err=f"{type(e).__name__}: {e}")
                log(f"ORRIN: error: {traceback.format_exc()}")
                try:
                    self.fail("crash", "Something went wrong on my end, sir.")
                except Exception:
                    hud.idle()
            finally:
                self.voice.ducker.restore()
                persona.end()
                hud.answering("")
            trace.end()
            self.pre.clear()
            self.wake.reset()
            self.mic.flush()
            last = time.time()


# ── The ORRIN app (Quickshell console) ────────
class AppBridge:
    """Socket ops from the app (core/appserver.py) → Orrin, the conversations and the task runner."""

    def __init__(self, vl):
        from core.appserver import AppServer
        from core.tasks import TaskManager
        self.vl, self.j = vl, vl.j
        self.server = AppServer(self.j.loop, self.handlers(), log=log)
        self.tasks = TaskManager(vl.cfg, self.j.loop, self.notify, self.j.confirms,
                                 ask_aloud=lambda p: vl.bg.put(("ask", p)),
                                 announce=lambda title, line, thread: vl.owed.set(),
                                 paused=lambda: vl.paused, log=log)
        asyncio.run_coroutine_threadsafe(self.server.start(), self.j.loop).result(5)
        self.j.notify = self.notify
        asyncio.run_coroutine_threadsafe(self.tasks.run_forever(), self.j.loop)
        from core.watch import WatchManager
        self.watch = WatchManager(vl.cfg, self.notify, say=lambda title, line: vl.bg.put(("say", title, line)),
                                  paused=lambda: vl.paused, log=log, laptop=C.LAPTOP)
        asyncio.run_coroutine_threadsafe(self.watch.run_forever(), self.j.loop)
        log(f"ORRIN: app socket at {self.server.path}")
        try:
            self.vl.status.tasks([self.tasks.item(t) for t in db.list_tasks(limit=12)])
        except Exception as e:
            log(f"ORRIN: status: {e}")

    def notify(self, ev):
        self.server.broadcast(ev)
        try:
            k = ev.get("ev")
            if k in ("task", "task_line"):
                self.vl.status.tasks([self.tasks.item(t) for t in db.list_tasks(limit=12)])
            if k == "usage" or (k == "task" and ev["item"]["status"] != "running"):
                self.vl.status.usage(self.j.brain)
        except Exception as e:
            log(f"ORRIN: status: {e}")
        if ev.get("ev") == "busy" and not ev.get("on") or ev.get("ev") == "task" and ev["item"]["status"] != "running":
            self.server.broadcast(self.usage())

    def usage(self):
        return {"ev": "usage", **db.turns_today(), **self.j.brain.usage_brief()}

    def handlers(self):
        return {"hello": self.hello, "threads": self.threads, "thread": self.thread, "ask": self.ask, "new": self.new,
                "resume": self.resume, "tasks": self.task_list, "task_log": self.task_log, "task": self.task_start,
                "cancel": self.cancel, "task_resume": self.task_resume, "answer": self.answer, "usage": lambda m: self.usage(),
                "watchers": self.watchers, "watch_pause": self.watch_pause, "watch_stop": self.watch_stop,
                "control_stop": self.control_stop}

    def hello(self, m):
        return [{"ev": "state", "current": self.j.conv.current, "busy": self.j.busy},
                self.threads({}), self.task_list({}), self.watchers({}), self.usage(),
                *[{"ev": "confirm", "item": p} for p in self.j.confirms.pending()]]

    def threads(self, m):
        return {"ev": "threads", "q": m.get("q", ""), "quick": bool(m.get("quick")),
                "items": db.list_threads(str(m.get("q", ""))[:100], bool(m.get("quick")))}

    def thread(self, m):
        tid = int(m["id"])
        return {"ev": "messages", "thread": db.get_thread(tid), "items": db.thread_messages(tid)}

    def ask(self, m):
        text = " ".join(str(m.get("text", "")).split())[:2000]
        if text and STOP_CONTROL.match(text) and control.active():
            control.stop_all("console")                 # now, not after the running request lets go of the turn lock
            return {"ev": "control", "active": False}
        if text:
            threading.Thread(target=self._ask, args=(text,), daemon=True).start()

    def _ask(self, text):
        try:
            self.j.handle(text, source="typed", confirm=self._confirm_typed)
        except Exception as e:
            log(f"ORRIN: typed request failed: {type(e).__name__}: {e}")
            self.notify({"ev": "error", "op": "ask", "error": "Something went wrong on my end."})

    def _confirm_typed(self, prompt):
        p = self.j.confirms.open(prompt, "typed")
        ok = p.wait(120)
        if not p.answered:
            self.j.confirms.expire(p)
        return ok

    def _fresh_brain(self):
        asyncio.run_coroutine_threadsafe(self.j.brain.reset(), self.j.loop)

    def new(self, m):
        self.j.conv.new()
        self.j.brain.history = ""
        self._fresh_brain()
        return {"ev": "state", "current": None}

    def resume(self, m):
        tid = int(m["id"])
        self.j.brain.history = self.j.conv.resume(tid)
        self._fresh_brain()
        return [{"ev": "state", "current": tid}, self.thread({"id": tid})]

    def watchers(self, m):
        return {"ev": "watchers", "items": [self.watch.item(w) for w in db.list_watchers()]}

    def watch_pause(self, m):
        self.watch.pause(int(m["id"]), bool(m.get("on", True)))
        return self.watchers({})

    def watch_stop(self, m):
        self.watch.stop(int(m["id"]))
        return self.watchers({})

    def task_list(self, m):
        return {"ev": "tasks", "items": [self.tasks.item(t) for t in db.list_tasks(30)]}

    def task_log(self, m):
        return {"ev": "task_log", "id": int(m["id"]), "items": db.task_log(int(m["id"]))}

    def task_start(self, m):
        from core.conversations import title_from
        text = str(m.get("text", "")).strip()[:4000]
        if text:
            self.tasks.start(title_from(text, 48), text)
        return self.task_list({})

    def cancel(self, m):
        self.tasks.cancel(int(m["id"]))
        return self.task_list({})

    def task_resume(self, m):
        self.tasks.resume(int(m["id"]))
        return self.task_list({})

    def answer(self, m):
        self.j.confirms.answer(int(m["id"]), "task" if m.get("yes") == "task" else bool(m.get("yes")))

    def control_stop(self, m):
        control.stop_all("console")
        return {"ev": "control", "active": False}


# ── CLI ────────────────────────────────────────
def show_log(rows):
    for r in rows:
        ts = datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        log(f"{ts}  {r['tier']:<16} {r['ms'] or 0:>6} ms  {r['request'][:70]}")
        if r["tools"] != "[]":
            log(f"{'':>24}tools: {r['tools'][:120]}")


def main():
    ap = argparse.ArgumentParser(description="ORRIN, the desktop's voice assistant (ORRIN / SELENE in AlchemOS)")
    ap.add_argument("--text", action="append", help="handle a typed request (repeat for a conversation)")
    ap.add_argument("--dry-run", action="store_true", help="validate and print tool calls without running them")
    ap.add_argument("--confirm", choices=["ask", "yes", "no"], default="ask", help="answer confirmations (text mode)")
    ap.add_argument("--speak", action="store_true", help="also speak replies in text mode")
    ap.add_argument("--no-hud", action="store_true", help="don't show the HUD toast in text mode")
    ap.add_argument("--misses", action="store_true", help="recent requests the fast path didn't handle")
    ap.add_argument("--log", action="store_true", help="recent action log")
    ap.add_argument("--facts", action="store_true", help="remembered facts")
    ap.add_argument("--reminders", action="store_true", help="pending timers / reminders")
    ap.add_argument("--say", metavar="TEXT", help="speak TEXT with the configured voice (Settings → TEST VOICE)")
    ap.add_argument("--as", dest="persona", choices=list(persona.NAMES),
                    help="with --say: as this persona (voice and manner), not the active one")
    ap.add_argument("--voice", help="with --say: voice to use instead of the setting (bm_george, en_GB-alan-medium…)")
    ap.add_argument("--effect", help="with --say: effect preset instead of the setting (CLEAN, HOLOGRAM, SUIT)")
    ap.add_argument("--trace", action="store_true", help="follow the stage-by-stage trace live (~/.local/state/orrin/trace.log)")
    ap.add_argument("--record", nargs="?", type=float, const=60, metavar="MIN",
                    help="save each exchange as WAV in ~/.local/state/orrin/rec for MIN minutes (default 60; 0 = stop)")
    args = ap.parse_args()

    if args.trace:
        trace.TRACE_FILE.parent.mkdir(parents=True, exist_ok=True)
        trace.TRACE_FILE.touch()
        os.execvp("tail", ["tail", "-n", "40", "-F", str(trace.TRACE_FILE)])
    elif args.record is not None:
        trace.set_recording(args.record)
        log(f"recording exchanges to {trace.REC_DIR} for {args.record:g} min" if args.record > 0 else "recording off")
    elif args.say:
        from core.voice import Voice
        v = Voice(C.Config(), log=log)
        v.overrides = {k: val for k, val in (("voice", args.voice), ("preset", args.effect)) if val}
        persona.begin(args.persona)
        v.speak(args.say)
    elif args.misses:
        show_log([r for r in db.recent_log(200) if not r["tier"].startswith("fast")][:40])
    elif args.log:
        show_log(db.recent_log(40))
    elif args.facts:
        for f in db.all_facts():
            log(f"{f['id']:>4}  {f['fact']}")
    elif args.reminders:
        for r in A.list_reminders()["items"]:
            log(f"{r['id']:>4}  {r['kind']:<8} {r['due']}  ({r['minutes_left']} min)  {r['text']}")
    elif args.text:
        text_mode(args)
    else:
        VoiceLoop().run()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, BrokenPipeError):
        pass
