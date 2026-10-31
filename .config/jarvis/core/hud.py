"""Talk to the Quickshell HUD (JarvisState via `qs ipc call jarvis …`). Silent if it isn't running."""
import queue
import subprocess
import threading

ENABLED = True
MAX_ARG = 20000
_q = queue.Queue()


def call(fn, *args):
    if not ENABLED:
        return
    try:
        # the whole text, every time: the pop-up scrolls long answers (the cap only guards against a runaway)
        subprocess.run(["qs", "ipc", "call", "jarvis", fn, *[str(a)[:MAX_ARG] for a in args]],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=3)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _worker():
    while True:
        fn, args = _q.get()
        call(fn, *args)


# One worker, so a fast burst (thinking → tool → reply) reaches the HUD in order
# without the voice loop waiting on qs.
threading.Thread(target=_worker, daemon=True).start()


def send(fn, *args):
    if ENABLED:
        _q.put((fn, args))


def online():      call("online")
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


def speak(start, end, total, ms):
    """A sentence of the reply starts playing: characters start..end of total (spoken text), ms long.
    The pop-up highlights and scrolls along with it."""
    send("speak", int(start), int(end), int(total), int(ms))


def speech_done():
    send("speechDone")
