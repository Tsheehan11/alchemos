"""Talk to the Quickshell HUD (OrrinState via `qs ipc call jarvis …`). Silent if it isn't running."""
import json
import queue
import subprocess
import threading

ENABLED = True
MAX_ARG = 20000
_q = queue.Queue()


def call(fn, *args):
    """One IPC call; returns what the HUD answered ("" if it isn't running)."""
    if not ENABLED:
        return ""
    try:
        # the whole text, every time: the pop-up scrolls long answers (the cap only guards against a runaway)
        r = subprocess.run(["qs", "ipc", "call", "jarvis", fn, *[str(a)[:MAX_ARG] for a in args]],
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=3, text=True)
        return r.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


# ── what the toast shows right now, so a restarted HUD can pick it up ──
# Jarvis runs as its own service (stark-jarvis.service); Quickshell can restart under it. A fresh
# OrrinState answers the heartbeat with "resync" and gets this snapshot back (OrrinState.restore).
# Only the live phases come back on screen; a finished reply isn't shown again.
_lock = threading.Lock()
_snap = {"phase": "idle", "transcript": "", "reply": "", "tools": [], "paused": False, "answering": ""}


def _track(fn, args):
    with _lock:
        s = _snap
        if fn == "listening":
            s.update(phase="listening", transcript="", reply="", tools=[])
        elif fn == "followup":
            s["phase"] = "followup"
        elif fn == "transcript":
            s["transcript"] = str(args[0])
            if s["phase"] == "idle":
                s["phase"] = "thinking"
        elif fn == "thinking":
            s["phase"] = "thinking"
        elif fn in ("tool", "note"):
            s["tools"] = (s["tools"] + [str(args[0])])[-5:]
            if fn == "tool":
                s["phase"] = "thinking"
        elif fn == "reply":
            s.update(phase="reply", reply=str(args[0]))
        elif fn == "confirm":
            s.update(phase="confirm", reply=str(args[0]))
        elif fn in ("idle", "error"):
            s["phase"] = "idle"
        elif fn == "paused":
            s["paused"] = args[0] == "true"
        elif fn == "answering":
            s["answering"] = str(args[0])


def snapshot():
    with _lock:
        return json.loads(json.dumps(_snap))


def _worker():
    while True:
        fn, args = _q.get()
        call(fn, *args)


# One worker, so a fast burst (thinking → tool → reply) reaches the HUD in order
# without the voice loop waiting on qs.
threading.Thread(target=_worker, daemon=True).start()


# text the HUD shows, in the current persona's manner (core/persona.style; JARVIS unchanged): arg index per fn
_STYLED = {"reply": 0, "confirm": 0, "toast": 1, "error": 1, "alert": 1}


def send(fn, *args):
    if ENABLED:
        i = _STYLED.get(fn)
        if i is not None and len(args) > i:
            from . import persona
            args = args[:i] + (persona.style(str(args[i])),) + args[i + 1:]
        _track(fn, args)
        _q.put((fn, args))


def online():
    """Heartbeat. A HUD that (re)started since the last beat answers "resync": queue the state."""
    if call("online") == "resync":
        _q.put(("restore", (json.dumps(snapshot()),)))


def offline():     call("offline")
def listening():   send("listening")
def followup():    send("followup")
def transcript(t): send("transcript", t)
def thinking():    send("thinking")
def tool(label):   send("tool", label)
def reply(t):      send("reply", t)
def confirm(t):    send("confirm", t)
def idle():        send("idle")
def paused(on):    send("paused", "true" if on else "false")
def toast(title, text): send("toast", title, text)
def error(reason, line): send("error", reason, line)     # spoken failure line + why, e.g. NO NETWORK
def note(label):   send("note", label)                   # an extra line on the toast, phase unchanged
def answering(who): send("answering", who or "")         # persona of this exchange (core/persona.py); "" = the default


def speak(start, end, total, ms):
    """A sentence of the reply starts playing: characters start..end of total (spoken text), ms long.
    The pop-up highlights and scrolls along with it."""
    send("speak", int(start), int(end), int(total), int(ms))


def speech_done():
    send("speechDone")
