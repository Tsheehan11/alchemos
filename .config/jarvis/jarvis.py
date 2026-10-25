#!/usr/bin/env python3
"""
JARVIS: Claude-powered voice assistant for STARK OS.

  "Hey Jarvis" → chime, LISTENING on the HUD → faster-whisper transcribes →
    fast path (local rules, no AI: media, lock, workspaces, lights, VPN, apps,
    themes, timers) or Claude (Agent SDK on the Pro login, tools from MCP
    servers in servers.json) → spoken reply (piper) + HUD toast.
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

import jarvis_db as db  # noqa: E402
import stark_actions as A  # noqa: E402
from core import fastpath, hud, trace  # noqa: E402
from core import config as C  # noqa: E402

# ── Wake word / speech-to-text ──────────────────
WAKEWORD = "hey_jarvis"
NEAR_MISS = 0.15         # wake scores above this (but under THRESHOLD) are traced as near misses
THRESHOLD = 0.5            # raise to ~0.7 if it triggers by accident, lower if it misses you
COOLDOWN_S = 1.5
WHISPER_MODEL = "base.en"  # "small.en" = more accurate but slower; "tiny.en" = fastest
MAX_COMMAND_S = 10.0       # longest command it will listen for
SILENCE_END_S = 1.0        # stop listening after this much silence
NO_SPEECH_TIMEOUT_S = 4.0  # nothing said after the wake word → give up quietly
VAD_THRESHOLD = 0.5        # Silero speech probability per 80 ms chunk
CONFIRM_TIMEOUT_S = 6.0
RATE = 16000
CHUNK = 1280               # 80 ms

YES = re.compile(r"\b(yes|yeah|yep|yup|confirm(ed)?|do it|go ahead|affirmative|proceed|sure|please do|correct)\b")
NO = re.compile(r"\b(no|nope|don't|do not|cancel|stop|negative|never ?mind|wait)\b")

CHIMES = ["/usr/share/sounds/ocean/stereo/message-new-instant.oga",
          "/usr/share/sounds/freedesktop/stereo/message.oga"]


def chime():
    for path in CHIMES:
        if os.path.exists(path):
            subprocess.Popen(["pw-play", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return


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


def is_yes(text):
    t = text.lower()
    return bool(YES.search(t)) and not NO.search(t)


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

    # Brain (asyncio thread) asks; the main thread answers (it owns the mic / terminal)
    async def _confirm_async(self, prompt):
        fut = self.loop.create_future()
        self.confirm_q.put((prompt, lambda ok: self.loop.call_soon_threadsafe(fut.set_result, ok)))
        return await fut

    def _on_tool(self, label):
        log(f"  ◆ {label}")
        trace.t("tool", label=label)
        hud.tool(label)

    def warm(self):
        """Start the Claude client now so the first question is fast."""
        return asyncio.run_coroutine_threadsafe(self.brain.connect(), self.loop)

    def run_steps(self, steps):
        """Fast-path steps → (spoken text, tool log). Confirmations first, one at a
        time; then the approved steps run side by side ("theme X and dim the lights"
        costs the slower of the two, not the sum)."""
        said, tools, approved = [], [], []
        for s in steps:
            if s["tool"] is None:
                continue
            self._on_tool(A.tool_label(s["tool"], s["args"]))
            prompt = A.confirmation_prompt(s["tool"], s["args"])
            if prompt and not self.confirm_sync(prompt):
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

    def handle(self, text, wait=None):
        """One request → reply text. wait(future) blocks until the Claude future is done
        (voice mode watches the mic for barge-in meanwhile); returns None if interrupted."""
        t0 = time.monotonic()
        steps = fastpath.match(text, self.last_query)
        if steps is not None:
            trace.t("route", to="fast", steps=",".join(s["tool"] or "say" for s in steps))
            reply, tools = self.run_steps(steps)
            tier = "fast"
        elif self.is_usage_question(text):
            trace.t("route", to="usage")
            hud.thinking()
            self._on_tool("CLAUDE USAGE")
            reply, tools = asyncio.run_coroutine_threadsafe(self.brain.usage_report(), self.loop).result(), ["usage"]
            tier = "usage"
        else:
            trace.t("route", to="claude")
            hud.thinking()
            self.last_query = text
            fut = asyncio.run_coroutine_threadsafe(self.brain.ask(text), self.loop)
            r = (wait or self.wait_text)(fut)
            if r is None or r.interrupted:
                db.log_action(text, "claude:interrupted", r.tools if r else [], "", int((time.monotonic() - t0) * 1000))
                return None
            reply, tools = r.text, r.tools
            tier = r.tier if not r.error else f"error:{r.error}"
        ms = int((time.monotonic() - t0) * 1000)
        try:
            db.log_action(text, tier, tools, reply, ms)
        except Exception as e:
            log(f"JARVIS: log failed: {e}")
        log(f"  [{tier} · {ms} ms]")
        trace.t("reply", tier=tier, ms=ms, tools=len(tools), text=reply)
        return reply

    def wait_text(self, fut):
        while True:
            try:
                prompt, answer = self.confirm_q.get(timeout=0.05)
                answer(self.confirm_sync(prompt))
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
        reply = j.handle(request)
        if reply:
            log(f"JARVIS: {reply}")
            hud.reply(reply)
            if voice:
                voice.speak(reply)
    asyncio.run_coroutine_threadsafe(j.brain.disconnect(), j.loop).result(10)


# ── Voice mode ─────────────────────────────────
class Mic:
    """pw-record → 80 ms chunks on a queue (a reader thread keeps the pipe drained)."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.proc = None
        self.q = queue.Queue(maxsize=400)
        self.vad = None

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

    def speech_prob(self, a):
        """Silero VAD (bundled with openWakeWord). A loudness threshold missed speech
        on the laptop mic, whose fan hum is ~700 RMS against speech peaks of ~3000."""
        if self.vad is None:
            from openwakeword.vad import VAD
            self.vad = VAD()
        return float(self.vad.predict(a))

    def record(self, no_speech_s=NO_SPEECH_TIMEOUT_S, kind="command", pre=()):
        """Until the speaker stops → float32 audio, or None if nothing was said.
        pre: chunks from just before (the wake word), only for the saved recording."""
        import numpy as np
        frames, probs, speech, silent, elapsed = [], [], False, 0.0, 0.0
        step = CHUNK / RATE
        first = last = None
        trace.t("listen", kind=kind, wait=no_speech_s)
        while True:
            a = self.read(2.0)
            if a is None:
                reason = "mic-stalled"
                break
            frames.append(a)
            elapsed += step
            p = self.speech_prob(a)
            probs.append(p)
            if p > VAD_THRESHOLD:
                if not speech:
                    first = len(frames) - 1
                    trace.t("vad.start", at=round(elapsed, 2), p=round(p, 2))
                speech, silent, last = True, 0.0, len(frames)
                trace.mark("speech_end")
            else:
                silent += step
            if speech and silent >= SILENCE_END_S:
                reason = "silence"
                break
            if not speech and elapsed >= no_speech_s:
                reason = "no-speech"
                break
            if elapsed >= MAX_COMMAND_S + (no_speech_s if not speech else 0):
                reason = "max-length"
                break
        audio = np.concatenate(frames) if frames else np.zeros(0, np.int16)
        db = lambda x: round(20 * np.log10(max(1.0, float(np.sqrt(np.mean(np.square(x.astype(np.float64))))))) - 90.3, 1) if len(x) else -99
        voiced = np.concatenate(frames[first:last]) if speech else audio
        trace.t("vad.end", reason=reason, len=round(elapsed, 2),
                speech=round(((last or 0) - (first or 0)) * step, 2) if speech else 0,
                p_max=round(max(probs, default=0), 2), p_mean=round(float(np.mean(probs)) if probs else 0, 2),
                level_db=db(audio), voice_db=db(voiced),
                peak_db=round(20 * np.log10(max(1, int(np.abs(audio).max(initial=0)))) - 90.3, 1))
        saved = trace.save(kind, np.concatenate(list(pre) + [audio]) if pre else audio)
        if saved:
            trace.t("saved", file=saved.name)
        if not speech:
            return None
        return audio.astype(np.float32) / 32768.0


class VoiceLoop:
    def __init__(self):
        self.cfg = C.Config()
        self.mic = Mic(self.cfg)
        self.paused = False
        self.barge = False
        self.last_reminder_check = 0.0
        from collections import deque
        self.pre = deque(maxlen=int(2.0 * RATE / CHUNK))   # the last 2 s before the wake word (recordings only)
        self.near = 0.0                                   # peak of a wake score that didn't reach THRESHOLD

    def load(self):
        import openwakeword
        from openwakeword.model import Model
        from faster_whisper import WhisperModel
        from core.voice import Voice
        log("JARVIS: loading models…")
        openwakeword.utils.download_models([WAKEWORD])
        self.wake = Model(wakeword_models=[WAKEWORD], inference_framework="onnx")
        self.stt = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
        self.voice = Voice(self.cfg, log=log, prewarm=True)
        self.voice.warm()
        A.apps()
        self.j = Jarvis(self.cfg, confirm_sync=self.confirm)
        self.j.warm()

    # ── helpers ──
    def woke(self, a, where="idle"):
        score = max(self.wake.predict(a).values())
        if score >= THRESHOLD:
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

    def transcribe(self, audio):
        t0 = time.monotonic()
        segments, info = self.stt.transcribe(audio, language="en", beam_size=1)
        segments = list(segments)
        text = " ".join(s.text for s in segments).strip()
        trace.t("stt", ms=int((time.monotonic() - t0) * 1000), model=WHISPER_MODEL, audio_s=round(len(audio) / RATE, 2),
                logprob=round(min((s.avg_logprob for s in segments), default=0), 2),
                no_speech=round(max((s.no_speech_prob for s in segments), default=0), 2), text=text)
        return text

    def say(self, text):
        """Speak while watching for "hey Jarvis". True if it interrupted."""
        hud.reply(text)
        if not self.cfg["jarvisSpeak"]:
            return False
        self.wake.reset()
        t = threading.Thread(target=self.voice.speak, args=(text,), daemon=True)
        t.start()
        interrupted = False
        while t.is_alive():
            a = self.mic.read(0.2)
            if a is not None and not interrupted and self.woke(a, "speaking"):
                log("JARVIS: interrupted while speaking")
                interrupted = True
                self.voice.stop()
        t.join()
        self.wake.reset()
        return interrupted

    def confirm(self, prompt):
        log(f"  ? {prompt}")
        hud.confirm(prompt)
        self.say(prompt)
        self.mic.flush()
        audio = self.mic.record(no_speech_s=CONFIRM_TIMEOUT_S, kind="confirm")
        answer = self.transcribe(audio) if audio is not None else ""
        log(f'  > "{answer}"')
        ok = is_yes(answer)
        if ok:
            hud.thinking()
        return ok

    def wait(self, fut):
        """Wait for Claude, answering confirmations; "hey Jarvis" interrupts."""
        self.wake.reset()
        while True:
            try:
                prompt, answer = self.j.confirm_q.get_nowait()
                answer(self.confirm(prompt))
                self.wake.reset()
            except queue.Empty:
                pass
            if fut.done():
                return fut.result()
            a = self.mic.read(0.1)
            if a is not None and self.woke(a, "thinking"):
                log("JARVIS: interrupted while thinking")
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

    # ── one exchange ──
    def converse(self):
        """Listen → answer → follow-ups. Returns when the conversation goes idle."""
        no_speech, kind, pre = NO_SPEECH_TIMEOUT_S, "command", list(self.pre)
        while True:
            self.barge = False
            audio = self.mic.record(no_speech_s=no_speech, kind=kind, pre=pre)
            pre = ()
            if audio is None:
                trace.t("idle", why="nothing heard" if kind != "followup" else "no follow-up")
                hud.idle()
                return
            hud.thinking()
            text = self.transcribe(audio)
            log(f'JARVIS: heard "{text}"')
            if not text or not re.search(r"\w", text):
                trace.t("idle", why="empty transcript")
                hud.idle()
                return
            hud.transcript(text)
            reply = self.j.handle(text, wait=self.wait)
            if reply is None:            # interrupted by the wake word: listen afresh
                if self.barge:
                    chime()
                    hud.listening()
                    no_speech, kind = NO_SPEECH_TIMEOUT_S, "command"
                    continue
                hud.idle()
                return
            if reply:
                if self.say(reply):
                    chime()
                    hud.listening()
                    no_speech, kind = NO_SPEECH_TIMEOUT_S, "command"
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
        db.prune_log()
        atexit.register(hud.offline)

        def heartbeat():
            while True:
                hud.online()
                time.sleep(5)
        threading.Thread(target=heartbeat, daemon=True).start()
        self.check_combat()
        if not self.paused:
            self.mic.start()
        log('JARVIS: online — say "Hey Jarvis"')
        last, last_prune = 0.0, time.time()
        while True:
            self.check_reminders()
            self.check_combat()
            if self.paused:
                time.sleep(1)
                continue
            if time.time() - last_prune > 86400:
                db.prune_log()
                last_prune = time.time()
            a = self.mic.read(1.0)
            if a is None:
                continue
            self.pre.append(a)
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
            self.voice.speaker.prepare()   # connect the Bluetooth speaker while Trevor talks
            chime()
            hud.listening()
            try:
                self.converse()
            except Exception as e:
                import traceback
                trace.t("error", where="converse", err=f"{type(e).__name__}: {e}")
                log(f"JARVIS: error: {traceback.format_exc()}")
                hud.idle()
            trace.end()
            self.pre.clear()
            self.wake.reset()
            self.mic.flush()
            last = time.time()


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
