#!/usr/bin/env python3
"""Jarvis as its own service (stark-jarvis.service): the HUD snapshot a restarted Quickshell gets back
(core/hud.py), the single-instance lock and the session guard (core/session.py).
Nothing is sent to the real HUD; the lock lives in a temp dir. Run: python tests/test_service.py"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import hud, session  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


# ── HUD snapshot: tracks what the toast shows, queues a restore on "resync" ──
sent = []
hud._q.put = lambda item: sent.append(item)          # no worker, no qs
answers = []
hud.call = lambda fn, *a: answers.pop(0) if answers else ""

hud.listening()
hud.transcript("dim the lights")
hud.tool("LIGHTS → 40 %")
s = hud.snapshot()
check("listening → thinking on transcript", s["phase"], "thinking")
check("transcript kept", s["transcript"], "dim the lights")
check("tool kept", s["tools"], ["LIGHTS → 40 %"])
hud.paused(True)
check("paused tracked", hud.snapshot()["paused"], True)
hud.paused(False)
hud.confirm("Close all windows?")
check("confirm phase + text", (hud.snapshot()["phase"], hud.snapshot()["reply"]), ("confirm", "Close all windows?"))
hud.reply("Done, sir.")
hud.idle()
check("idle after reply", hud.snapshot()["phase"], "idle")
hud.listening()
check("listening clears", (hud.snapshot()["transcript"], hud.snapshot()["tools"]), ("", []))
for i in range(7):
    hud.note(f"n{i}")
check("tools capped at 5", len(hud.snapshot()["tools"]), 5)
check("note keeps phase", hud.snapshot()["phase"], "listening")

sent.clear()
answers[:] = [""]
hud.online()
check("synced HUD: no restore", [f for f, _ in sent], [])
answers[:] = ["resync"]
hud.online()
check("resync → one restore queued", [f for f, _ in sent], ["restore"])
check("restore carries the snapshot", json.loads(sent[0][1][0])["phase"], "listening")

# ── single-instance lock (a second process can't take it) ──
with tempfile.TemporaryDirectory() as d:
    session.LOCK = Path(d) / "voice.lock"
    ok, _ = session.take_lock()
    check("first takes the lock", ok, True)
    code = ("import sys; sys.path[:0]=[%r, %r]; from core import session; from pathlib import Path;"
            "session.LOCK=Path(%r); ok, h = session.take_lock(); print(ok, h)"
            % (os.path.join(ROOT, "mcp"), ROOT, str(session.LOCK)))
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=30).stdout.split()
    check("second process refused, told the holder", out, ["False", str(os.getpid())])

# ── session guard ──
old = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE")
os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = "no-such-instance-xyz"
sock = session.hyprland_socket()
check("gone instance → stop", session.session_gone(sock), True)
os.environ.pop("HYPRLAND_INSTANCE_SIGNATURE")
check("outside Hyprland → never stops", session.session_gone(session.hyprland_socket()), False)
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / ".socket.sock"
    p.touch()
    check("live instance → keep going", session.session_gone(p), False)
if old is not None:
    os.environ["HYPRLAND_INSTANCE_SIGNATURE"] = old

print("FAILED: " + ", ".join(FAILS) if FAILS else "ok: service")
sys.exit(1 if FAILS else 0)
