"""
The voice loop runs as a systemd user service (orrin.service), not as a HUD child, so it
looks after its own lifetime:

  * one at a time: an flock on $XDG_RUNTIME_DIR/orrin/voice.lock (a hand-run `orrin` next to
    the service says so and exits instead of fighting it for the mic)
  * the session: it belongs to the Hyprland instance it was started in. Once that instance's
    socket is gone (log-out, Hyprland crashed) it exits cleanly, so nothing lingers when systemd's
    user manager outlives the session (an SSH login, a second seat).
"""
import fcntl
import os
from pathlib import Path

from . import config as C

LOCK = C.RUNTIME / "orrin" / "voice.lock"
_held = None


def take_lock():
    """True if this process is now the only voice loop. Held until exit."""
    global _held
    LOCK.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    f = open(LOCK, "a+")
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        f.seek(0)
        holder = f.read().strip()
        f.close()
        return False, holder
    f.seek(0)
    f.truncate()
    f.write(str(os.getpid()))
    f.flush()
    _held = f
    return True, ""


def hyprland_socket():
    """The Hyprland instance this process was started in (None outside Hyprland)."""
    sig = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
    return C.RUNTIME / "hypr" / sig / ".socket.sock" if sig else None


def session_gone(sock: Path | None):
    return sock is not None and not sock.exists()
