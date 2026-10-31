#!/usr/bin/env python3
"""
JARVIS: Claude-powered voice assistant for STARK OS.

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

Started by the HUD (quickshell/JarvisState.qml) only while docked.

Text mode / testing:
  jarvis --text "set the theme to matrix and dim the lights"
  jarvis --text "..." --dry-run      validate + print tool calls, change nothing
  jarvis --text "suspend" --confirm no     answer the confirmation question
  jarvis --misses | --log | --facts | --reminders | --say "text"
  jarvis --trace          follow each exchange stage by stage (wake score, VAD, STT, route, TTS)
  jarvis --record [MIN]   also keep WAVs of each exchange for tuning (~/.local/state/jarvis/rec)

Phase-2 integrations (servers.json, core/integrations.py, docs/phase2-*.md):
  jarvis integrations [--json]       CONNECTED / NOT CONNECTED for each
  jarvis connect google | microsoft | learn-ical [URL]
  jarvis disconnect google | microsoft | learn-ical

JARVIS app (Super + J, quickshell/JarvisApp.qml; core/appserver.py, conversations.py, tasks.py):
  jarvis app-data threads [QUERY] [--quick] | thread ID | tasks | task ID | usage   history as JSON

SE tracker sheet (mcp/tracker.py, docs/jarvis-app.md):
  jarvis tracker find [ID] | show | pending [DAYS] | diff | log [N] | undo
Calendar writes (mcp/google_api.CalendarWriter):
  jarvis calendar log [N] | undo

Local router (intents.json, tools/eval_router.py):
  jarvis intents [list | log [N] | review | remove N…]   learned examples, recent decisions
"""
import argparse
import asyncio
import atexit
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

JARVIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(JARVIS_DIR / "mcp"))
sys.path.insert(0, str(JARVIS_DIR))
os.environ.pop("ANTHROPIC_API_KEY", None)   # Pro login only, never an API key

if __name__ == "__main__" and sys.argv[1:2] in (["connect"], ["disconnect"], ["integrations"]):
    from core import integrations          # before the heavy imports: Settings polls `integrations --json`
    sys.exit(integrations.main(sys.argv[1:]))
if __name__ == "__main__" and sys.argv[1:2] == ["app-data"]:
    from core import conversations         # the app reads history this way while Jarvis is off (undocked)
    sys.exit(conversations.app_data(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["tracker"]:
    sys.path.insert(0, str(JARVIS_DIR / "mcp"))
    import tracker                         # find / show / pending / diff / log / undo: no models needed
    sys.exit(tracker.cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["calendar"]:
    sys.path.insert(0, str(JARVIS_DIR / "mcp"))
    import google_api                      # log / undo of Jarvis's calendar writes
    sys.exit(google_api.calendar_cli(sys.argv[2:]))
if __name__ == "__main__" and sys.argv[1:2] == ["intents"]:
    sys.path.insert(0, str(JARVIS_DIR / "mcp"))
    from core import router_local          # list / review / remove need no model
    sys.exit(router_local.cli(sys.argv[2:]))

import jarvis_db as db  # noqa: E402
import stark_actions as A  # noqa: E402
from core import fastpath, hearing, hud, secrets, trace  # noqa: E402
from core import config as C  # noqa: E402

# ── Wake word / speech-to-text ──────────────────
WAKEWORD = "hey_jarvis"
NEAR_MISS = 0.15           # wake scores above this (but under THRESHOLD) are traced as near misses
THRESHOLD = 0.4            # real "hey Jarvis" at the desk peaks at 0.83-1.0; nothing else got past 0.25
BARGE_THRESHOLD = 0.3      # over its own voice (which never scored above 0.21) "hey Jarvis" is harder to hear
COOLDOWN_S = 0.5           # after a conversation ends (the model is reset, so it can't refire on itself)
# base.en + vocabulary prompt: 0.3 s per command on this CPU. small.en was barely more accurate
# on Trevor's recordings (1-2 words in 28 commands) for 0.95 s; distil-small.en was worse.
WHISPER_MODEL = "base.en"
NO_SPEECH_TIMEOUT_S = 4.0  # nothing said after the wake word → "Sorry sir, I didn't catch that."
CONFIRM_TIMEOUT_S = 6.0
RATE = hearing.RATE
CHUNK = hearing.CHUNK      # 80 ms
NOT_HEARD = "Sorry sir, I didn't catch that."
SYNC_S = 15 * 60           # Outlook calendar link + LEARN feed + grade notices, while docked

YES = re.compile(r"\b(yes|yeah|yep|yup|confirm(ed)?|do it|go ahead|affirmative|proceed|sure|please do|correct)\b")
NO = re.compile(r"\b(no|nope|don't|do not|cancel|stop|negative|never ?mind|wait)\b")

LOG_FILE = None   # voice mode: ~/.local/share/jarvis/jarvis.log (the HUD discards stdout)


def log(*a):
    print(*a, flush=True)
    if LOG_FILE:
        LOG_FILE.write(datetime.now().strftime("%m-%d %H:%M:%S ") + " ".join(map(str, a)) + "\n")
        LOG_FILE.flush()


def open_log():
    global LOG_FILE
    path = C.DATA_DIR / "jarvis.log"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1_000_000:
        path.replace(path.with_suffix(".log.old"))
    LOG_FILE = open(path, "a", encoding="utf-8")


def govee_pulse():
    """A small light swell on the strip with the chime (stark-govee skips it if the strip is off or busy).
    Straight to the daemon's Unix socket, fire and forget: no process, never delays listening."""
    import socket
    path = os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "stark-govee.sock")

    def send():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(path)
                s.sendall(b"anim listen\n")
        except OSError:
            pass                                   # no strip / daemon: nothing to do
    threading.Thread(target=send, daemon=True).start()


def is_yes(text):
    t = text.lower()
    return bool(YES.search(t)) and not NO.search(t)


# Why a request failed, as the toast shows it (Brain.ERRORS has the spoken lines)
ERROR_LABELS = {"limit": "USAGE LIMIT", "offline": "NO NETWORK", "timeout": "TIMED OUT", "auth": "LOGIN EXPIRED",
                "failed": "CLAUDE ERROR", "tools": "TOO MANY STEPS", "noreply": "CLAUDE NOT RESPONDING",
                "tool": "ACTION FAILED", "heard": "DIDN'T CATCH THAT", "crash": "INTERNAL ERROR"}


# ── The assistant, shared by voice and text mode ─
class Jarvis:
    def __init__(self, cfg, dry_run=False, confirm_sync=None, speak=None):
        self.cfg = cfg
        self.dry_run = dry_run
        A.set_dry_run(dry_run)
        self.confirm_sync = confirm_sync      # (prompt) -> bool, runs on the main thread
        self.speak = speak                    # unused here; voice mode speaks replies itself
        self.last_query = ""
        self.confirm_q = queue.Queue()
        self.loop = asyncio.new_event_loop()
        threading.Thread(target=self.loop.run_forever, daemon=True).start()
        from core.brain import Brain, is_usage_question
        self.is_usage_question = is_usage_question
        self.brain = Brain(cfg, self._confirm_async, self._on_tool, dry_run=dry_run, log=log)
        self.router = None
        self.learning = []                     # learn() threads; text mode waits for them before exiting
        # The JARVIS app (core/appserver.py, voice mode only): voice and typed requests take turns on
        # one brain, every exchange is recorded in a thread, and tool labels / confirmations reach the app.
        from core.conversations import Confirmations, Conversations
        self.notify = lambda ev: None          # set by AppBridge once the socket is up
        self.turn_lock = threading.RLock()
        self.surface = "voice"                 # who's asking right now: voice (HUD toast) | typed (app only)
        self.busy = False
        self.conv = Conversations(lambda ev: self.notify(ev))
        self.confirms = Confirmations(lambda ev: self.notify(ev))
        try:                                   # load once, keep warm (≈0.2 s with cached vectors)
            from core.router_local import LocalRouter
            self.router = LocalRouter(cfg, log=log)
            self.router.warm()
        except Exception as e:                 # no model files and offline, bad intents.json…: Claude only
            log(f"JARVIS: local router unavailable ({type(e).__name__}: {e}); using Claude only")

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
                said.append(f"I couldn't: {r.get('error', 'unknown error')}.")
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
                    log(f"JARVIS: thread record failed: {e}")
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
        steps = fastpath.match(text, self.last_query)
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
        elif (d := self.route_local(text)) and d.path == "local":
            trace.t("route", to="local", intent=d.intent, score=d.top3[0][1], ms=d.ms)
            steps = d.steps
            reply, tools = self.run_steps(steps, confirm)
            tier = f"local:{d.intent}"
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
            if d and not r.error:
                self._learn(text, d, r)
        if steps is not None and any(t.endswith("[failed]") for t in tools):
            self.error = "tool"
        ms = int((time.monotonic() - t0) * 1000)
        self._last_tools, self._last_tier = tools, tier
        self._log_action(text, tier, tools, reply, ms)
        log(f"  [{tier} · {ms} ms]")
        trace.t("reply", tier=tier, ms=ms, tools=len(tools), text=reply)
        return reply

    def route_local(self, text):
        """The local router's decision, or None when it's off (Settings → JARVIS → DECISIONS) or not loaded."""
        if not self.router or self.cfg["jarvisDecisions"] != "local":
            return None
        try:
            return self.router.decide(text)
        except Exception as e:
            log(f"JARVIS: local router failed: {type(e).__name__}: {e}")
            return None

    def _learn(self, text, d, r):
        """Claude answered with exactly one stark tool call: teach the router that phrasing."""
        if self.dry_run or d.path in ("claude:claude-only", "claude:empty") or len(r.calls) != 1:
            return
        server, tool, args = r.calls[0]
        if server != "stark":
            return
        th = threading.Thread(target=lambda: self.router.learn(text, tool, args), daemon=True)
        th.start()
        self.learning.append(th)

    def _log_action(self, *row):
        """SQLite write off the critical path (it was ~50 ms before the reply could play)."""
        def write():
            try:
                db.log_action(*row)
            except Exception as e:
                log(f"JARVIS: log failed: {e}")
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

    j = Jarvis(cfg, dry_run=args.dry_run, confirm_sync=confirm)
    voice = None
    if args.speak:
        from core.voice import Voice
        voice = Voice(cfg)
    for request in args.text:
        log(f'> {request}')
        hud.transcript(request)
        reply = j.handle(request, source="cli")
        if reply:
            log(f"JARVIS: {reply}")
            hud.reply(reply)
            if voice:
                voice.speak(reply)
    for th in j.learning:                     # onnxruntime aborts if the interpreter exits mid-inference
        th.join(10)
    asyncio.run_coroutine_threadsafe(j.brain.disconnect(), j.loop).result(10)


# ── Voice mode ─────────────────────────────────
class Mic:
    """pw-record → 80 ms chunks on a queue (a reader thread keeps the pipe drained)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.q = queue.Queue(maxsize=400)

    def start(self):
        if self.proc:
            return
        # --raw: without it pw-record ≥ 1.6.10 writes an AU stream to stdout (header + big-endian)
        cmd = ["pw-record", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "s16",
               "-P", "media.name=Jarvis wake word"]
        if self.cfg["jarvisMic"]:
            cmd += ["--target", self.cfg["jarvisMic"]]
        self.proc = subprocess.Popen(cmd + ["-"], stdout=subprocess.PIPE)
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True).start()

    def stop(self):
        p, self.proc = self.proc, None
        if p:
            p.terminate()
            p.wait()
        self.flush()

    def flush(self):
        while not self.q.empty():
            self.q.get_nowait()

    def _reader(self, proc):
        import numpy as np
        n = CHUNK * 2
        while True:
            data = proc.stdout.read(n)
            if not data or len(data) < n:
                if self.proc is proc:     # not a deliberate stop
                    log("JARVIS: microphone stream ended")
                    os._exit(1)
                return
            try:
                self.q.put(np.frombuffer(data, dtype=np.int16), timeout=1)
            except queue.Full:
                pass

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
        self.bg = queue.Queue()                           # ("say", title, line) | ("ask", Pending): tasks, while idle
        self.near = 0.0                                   # peak of a wake score that didn't reach THRESHOLD
        self.spec = None                                  # listen()'s early transcription, if still valid

    def load(self):
        import openwakeword
        from openwakeword.model import Model
        from openwakeword.vad import VAD
        from core.voice import Voice
        log("JARVIS: loading models…")
        openwakeword.utils.download_models([WAKEWORD])
        self.wake = Model(wakeword_models=[WAKEWORD], inference_framework="onnx")
        self.vad = VAD()
        self.stt = hearing.STT(WHISPER_MODEL)
        self.voice = Voice(self.cfg, log=log, prewarm=True)
        self.voice.progress = lambda start, end, total, ms: (hud.speech_done() if start is None
                                                             else hud.speak(start, end, total, ms))
        self.voice.warm()
        A.apps()
        self.j = Jarvis(self.cfg, confirm_sync=self.confirm)
        self.j.warm()
        try:
            self.app = AppBridge(self)
        except Exception as e:                 # the console is optional: voice keeps working without it
            log(f"JARVIS: app socket unavailable: {type(e).__name__}: {e}")

    # ── hearing ──
    def read(self, timeout):
        """Next mic chunk; the last 2 s are kept so a command said in the same breath as
        "hey Jarvis" (waking it or interrupting it) keeps its first words."""
        a = self.mic.read(timeout)
        if a is not None:
            self.pre.append(a)
        return a

    def woke(self, a, where="idle"):
        score = max(self.wake.predict(a).values())
        if score >= (THRESHOLD if where in ("idle", "listening") else BARGE_THRESHOLD):
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
                log("JARVIS: interrupted while speaking")
                interrupted = True
                u.stop()
        self.wake.reset()
        if u.fell_back:
            hud.note("SPEAKER UNREACHABLE → LAPTOP")
        return interrupted

    def say(self, text):
        """Speak while watching for "hey Jarvis". True if it interrupted."""
        hud.reply(text)
        if not self.cfg["jarvisSpeak"]:
            return False
        u = self.voice.utterance()
        u.add(text)
        u.finish()
        return self.play(u)

    def fail(self, why, line):
        """Something went wrong after the chime: say so, and show why."""
        trace.t("fail", why=why, line=line)
        log(f"JARVIS: {ERROR_LABELS.get(why, why)} — {line}")
        hud.error(ERROR_LABELS.get(why, why.upper()), line)
        if self.cfg["jarvisSpeak"]:
            u = self.voice.utterance()
            u.add(line)
            u.finish()
            self.play(u)

    def confirm(self, prompt):
        log(f"  ? {prompt}")
        hud.confirm(prompt)
        if self.cfg["jarvisSpeak"]:
            u = self.voice.utterance()
            u.add(prompt)
            u.finish()
            self.play(u)
        self.mic.flush()
        audio = self.listen(CONFIRM_TIMEOUT_S, kind="confirm")
        answer = self.transcribe(audio)[0] if audio is not None else ""
        log(f'  > "{answer}"')
        ok = is_yes(answer)
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
                log("JARVIS: interrupted while thinking")
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

    def check_combat(self):
        want = self.cfg["gameJarvis"] and A.combat_mode()
        if want != self.paused:
            self.paused = want
            if want:
                log("JARVIS: combat mode, wake word paused")
                self.mic.stop()
            else:
                log("JARVIS: combat mode over, listening again")
                self.mic.start()
                self.wake.reset()
            hud.paused(want)

    def check_reminders(self):
        now = time.time()
        if now - self.last_reminder_check < 1.0:
            return
        self.last_reminder_check = now
        try:
            due = db.due_reminders(now)
        except Exception as e:
            log(f"JARVIS: reminders: {e}")
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
            log(f"JARVIS: {msg}")
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
            log(f"JARVIS: academic: {e}")
            return
        for line in lines:
            log(f"JARVIS: {line}")
            hud.toast("LEARN" if "tracker" not in line else "TRACKER", line.upper())
            if not self.paused:
                self.say(line)
        try:
            offer = academic_sync.pop_tracker_offer()
        except Exception as e:
            log(f"JARVIS: tracker offer: {e}")
            return
        if offer:
            self.offer_tracker(offer)

    def check_background(self):
        """Task announcements, and a task's question asked out loud (the app can answer it too)."""
        if self.paused:
            return
        while True:
            try:
                item = self.bg.get_nowait()
            except queue.Empty:
                return
            if item[0] == "say":
                _, title, line = item
                log(f"JARVIS: {line}")
                hud.toast(title, line.upper()[:300])
                self.say(line)
            elif item[0] == "ask" and not item[1].answered:
                self.ask_pending(item[1])

    def ask_pending(self, p):
        """Ask a background task's question out loud. A clear yes / no answers it; silence leaves it
        waiting in the app."""
        self.voice.chime()
        prompt = f"For the {p.title.lower()} task: {p.prompt}" if p.title else p.prompt
        log(f"  ? {prompt}")
        hud.confirm(prompt)
        if self.cfg["jarvisSpeak"]:
            u = self.voice.utterance()
            u.add(prompt)
            u.finish()
            self.play(u)
        if p.answered:
            hud.idle()
            return
        self.mic.flush()
        audio = self.listen(CONFIRM_TIMEOUT_S, kind="confirm", stop=lambda: p.answered)
        answer = self.transcribe(audio)[0] if audio is not None else ""
        log(f'  > "{answer}"')
        if answer and not p.answered and (is_yes(answer) or NO.search(answer.lower())):
            self.j.confirms.answer(p.id, is_yes(answer))
            self.say("Very good, sir." if is_yes(answer) else "Very well, sir.")
        else:
            hud.idle()

    def offer_tracker(self, offer):
        import tracker
        self.voice.chime()
        ok = self.confirm(offer["prompt"])
        if not ok:
            log("JARVIS: tracker offer declined")
            hud.idle()
            return
        if offer.get("calendar"):                # a sheet change AUTO-UPDATE made: its event, now he said yes
            try:
                import sheet_calendar
                cal, did = sheet_calendar.SheetCalendar(), []
                for before, after in offer["calendar"]:
                    did += cal.follow(tracker.row_from_json(before), tracker.row_from_json(after))["did"]
            except Exception as e:
                log(f"JARVIS: calendar follow failed: {type(e).__name__}: {e}")
                self.fail("tool", getattr(e, "say", None) or "I couldn't reach your calendar, sir.")
                return
            self.say(f"Done, sir: I {' and '.join(did)}." if did else "Its calendar event was already right, sir.")
            return
        try:
            t = tracker.Tracker()
            res = t.apply(offer["changes"], offer["source"], calendar=True)
        except Exception as e:
            log(f"JARVIS: tracker write failed: {type(e).__name__}: {e}")
            self.fail("tool", "I couldn't reach your tracker, sir.")
            return
        bad = [r for r in res if not r["ok"]]
        for r in bad:
            log(f"JARVIS: tracker: {r['error']}")
        for n in t.calendar_report["notes"]:
            log(f"JARVIS: tracker calendar: {n}")
        did = t.calendar_report["did"]
        self.say(bad[0]["say"] if bad else "Done, sir. It's in your tracker" + (f", and I {' and '.join(did)}." if did else "."))

    def _sync_loop(self):
        """Every SYNC_S while docked (this process only runs docked): the Outlook calendar link, the LEARN
        feed, grade notices in Gmail, and with AUTO-ADD the "STARK – Assignments" calendar
        (mcp/academic_sync.py). Off the main thread, so the wake word never waits on the network."""
        time.sleep(30)
        while True:
            try:
                import academic_sync
                import outlook_ical
                if outlook_ical.url():
                    m = outlook_ical.fetch()
                    if not m.get("ok"):
                        log(f"JARVIS: Outlook calendar link: {m.get('error')}")
                if secrets.has("learn", "ical_url"):
                    r = academic_sync.sync(self.cfg, log=log)
                    busy = {k: v for k, v in r.items() if v and k != "learn"
                            and not (isinstance(v, dict) and set(v) == {"skipped"})} | (
                        {"learn": r["learn"]} if r.get("learn", {}).get("new") or r.get("learn", {}).get("changed") else {})
                    if busy:
                        log(f"JARVIS: academic sync {busy}")
            except Exception as e:
                log(f"JARVIS: sync failed: {type(e).__name__}: {e}")
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
            log(f'JARVIS: heard "{raw}"')
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
            # The output opens now (Bluetooth wakes while Jarvis thinks); Claude's sentences go
            # into it as they stream in, so the first one plays before the reply is finished.
            speak = self.cfg["jarvisSpeak"]
            u = self.voice.utterance() if speak else None
            streamed = []

            def on_sentence(sentence):
                streamed.append(sentence)
                if u:
                    u.add(sentence)
            reply = self.j.handle(text, wait=lambda fut: self.wait(fut, u), on_sentence=on_sentence)
            if reply is None:            # interrupted by the wake word: listen afresh
                if u:
                    u.stop()
                if self.barge:
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
                    self.voice.chime()
                    hud.listening()
                    no_speech, kind, pre = NO_SPEECH_TIMEOUT_S, "command", list(self.pre)
                    barged = True
                    continue
            follow = float(self.cfg["jarvisFollowup"] or 0)
            if follow <= 0 or reply in ("Very good, sir.", "You're welcome, sir."):
                hud.idle()
                return
            hud.followup()
            self.mic.flush()
            no_speech, kind = follow, "followup"

    def run(self):
        open_log()
        self.load()
        self.voice.ducker.restore_leftover()      # a previous run stopped mid-reply: music back up

        def stop(signum, frame):                  # HUD reload / dock change: don't leave the music down
            self.voice.ducker.restore()
            hud.offline()
            os._exit(0)
        import signal
        signal.signal(signal.SIGTERM, stop)
        db.prune_log()
        atexit.register(hud.offline)

        def heartbeat():
            while True:
                hud.online()
                time.sleep(5)
        threading.Thread(target=heartbeat, daemon=True).start()
        threading.Thread(target=self._sync_loop, daemon=True).start()
        self.check_combat()
        if not self.paused:
            self.mic.start()
        log('JARVIS: online — say "Hey Jarvis"')
        last, last_prune = 0.0, time.time()
        while True:
            self.check_reminders()
            self.check_academic()
            self.check_background()
            self.check_combat()
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
            trace.t("wake", score=round(score, 2), queued=self.mic.q.qsize())
            log("JARVIS: wake word")
            self.wake.reset()     # else its buffer still holds "hey Jarvis" and fires again mid-reply
            self.voice.chime()
            govee_pulse()
            hud.listening()
            self.voice.speaker.prepare()   # connect the Bluetooth speaker while Trevor talks
            if self.cfg["jarvisDuck"]:     # turn the music down so it isn't heard as the command
                from core.voice import DUCK_LISTEN
                threading.Thread(target=self.voice.ducker.duck, args=(DUCK_LISTEN,), daemon=True).start()
            try:
                self.converse()
            except Exception as e:
                import traceback
                trace.t("error", where="converse", err=f"{type(e).__name__}: {e}")
                log(f"JARVIS: error: {traceback.format_exc()}")
                try:
                    self.fail("crash", "Something went wrong on my end, sir.")
                except Exception:
                    hud.idle()
            finally:
                self.voice.ducker.restore()
            trace.end()
            self.pre.clear()
            self.wake.reset()
            self.mic.flush()
            last = time.time()


# ── The JARVIS app (Quickshell console) ────────
class AppBridge:
    """Socket ops from the app (core/appserver.py) → Jarvis, the conversations and the task runner."""

    def __init__(self, vl):
        from core.appserver import AppServer
        from core.tasks import TaskManager
        self.vl, self.j = vl, vl.j
        self.server = AppServer(self.j.loop, self.handlers(), log=log)
        self.tasks = TaskManager(vl.cfg, self.j.loop, self.notify, self.j.confirms,
                                 ask_aloud=lambda p: vl.bg.put(("ask", p)),
                                 announce=lambda title, line, thread: vl.bg.put(("say", title, line)),
                                 paused=lambda: vl.paused, log=log)
        asyncio.run_coroutine_threadsafe(self.server.start(), self.j.loop).result(5)
        self.j.notify = self.notify
        asyncio.run_coroutine_threadsafe(self.tasks.run_forever(), self.j.loop)
        log(f"JARVIS: app socket at {self.server.path}")

    def notify(self, ev):
        self.server.broadcast(ev)
        if ev.get("ev") == "busy" and not ev.get("on") or ev.get("ev") == "task" and ev["item"]["status"] != "running":
            self.server.broadcast(self.usage())

    def usage(self):
        return {"ev": "usage", **db.turns_today(), **self.j.brain.usage_brief()}

    def handlers(self):
        return {"hello": self.hello, "threads": self.threads, "thread": self.thread, "ask": self.ask, "new": self.new,
                "resume": self.resume, "tasks": self.task_list, "task_log": self.task_log, "task": self.task_start,
                "cancel": self.cancel, "task_resume": self.task_resume, "answer": self.answer, "usage": lambda m: self.usage()}

    def hello(self, m):
        return [{"ev": "state", "current": self.j.conv.current, "busy": self.j.busy},
                self.threads({}), self.task_list({}), self.usage(),
                *[{"ev": "confirm", "item": p} for p in self.j.confirms.pending()]]

    def threads(self, m):
        return {"ev": "threads", "q": m.get("q", ""), "quick": bool(m.get("quick")),
                "items": db.list_threads(str(m.get("q", ""))[:100], bool(m.get("quick")))}

    def thread(self, m):
        tid = int(m["id"])
        return {"ev": "messages", "thread": db.get_thread(tid), "items": db.thread_messages(tid)}

    def ask(self, m):
        text = " ".join(str(m.get("text", "")).split())[:2000]
        if text:
            threading.Thread(target=self._ask, args=(text,), daemon=True).start()

    def _ask(self, text):
        try:
            self.j.handle(text, source="typed", confirm=self._confirm_typed)
        except Exception as e:
            log(f"JARVIS: typed request failed: {type(e).__name__}: {e}")
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
        self.j.confirms.answer(int(m["id"]), bool(m.get("yes")))


# ── CLI ────────────────────────────────────────
def show_log(rows):
    for r in rows:
        ts = datetime.fromtimestamp(r["ts"]).strftime("%m-%d %H:%M")
        log(f"{ts}  {r['tier']:<16} {r['ms'] or 0:>6} ms  {r['request'][:70]}")
        if r["tools"] != "[]":
            log(f"{'':>24}tools: {r['tools'][:120]}")


def main():
    ap = argparse.ArgumentParser(description="JARVIS for STARK OS")
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
    ap.add_argument("--voice", help="with --say: voice to use instead of the setting (bm_george, en_GB-alan-medium…)")
    ap.add_argument("--effect", help="with --say: effect preset instead of the setting (CLEAN, HOLOGRAM, SUIT)")
    ap.add_argument("--trace", action="store_true", help="follow the stage-by-stage trace live (~/.local/state/jarvis/trace.log)")
    ap.add_argument("--record", nargs="?", type=float, const=60, metavar="MIN",
                    help="save each exchange as WAV in ~/.local/state/jarvis/rec for MIN minutes (default 60; 0 = stop)")
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
