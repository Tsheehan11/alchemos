"""Talk to the Quickshell HUD (JarvisState via `qs ipc call jarvis …`). Silent if it isn't running."""
import queue
import subprocess
import threading

ENABLED = True
_q = queue.Queue()


def call(fn, *args):
    if not ENABLED:
        return
    try:
        subprocess.run(["qs", "ipc", "call", "jarvis", fn, *[str(a)[:600] for a in args]],
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
