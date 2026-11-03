#!/usr/bin/env python3
"""Screenshots: fast-path wording, router intents, the screenshot action against a faked HUD (qs ipc shot …),
and stark-shot's pure helpers (monitor overlap for the flash, file naming). Temp intents copy + temp dirs;
nothing is captured. Run: python tests/test_screenshot.py"""
import importlib.machinery
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import config as C  # noqa: E402
from core import fastpath as F  # noqa: E402
from core import router_local as R  # noqa: E402
import stark_actions as A  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def fast(text):
    s = F.match(text)
    return [(x["tool"], x["args"].get("mode")) for x in s] if s else None


# ── fast path ──
for text, mode in [("take a screenshot", "region"), ("Jarvis, take a screenshot please", "region"), ("screenshot", "region"),
                   ("print screen", "region"), ("grab a screen shot", "region"),
                   ("screenshot this monitor", "screen"), ("screenshot the monitor i'm on", "screen"),
                   ("take a screenshot of the whole screen", "screen"), ("capture this screen", "screen"),
                   ("screenshot this window", "window"), ("take a screenshot of the current window", "window"),
                   ("snap the window", "window"),
                   ("take a screenshot and annotate it", "annotate"), ("annotate a screenshot", "annotate"),
                   ("screenshot and mark it up", "annotate")]:
    check(f"fast {text!r}", fast(text), [("screenshot", mode)])
check("region says select", F.match("take a screenshot")[0]["say"], "Select the area, sir.")
check("window says window", F.match("screenshot this window")[0]["say"], "Window captured, sir.")
check("compound", fast("take a screenshot and then lock the screen"), [("screenshot", "region"), ("lock_screen", None)])
# Not screenshots: screen roles, lock, reading the screen
check("role still a role", F.match("put music on the tv")[0]["tool"], "set_screen_role")
check("lock still lock", fast("lock the screen"), [("lock_screen", None)])
check("reading the screen isn't a shot", fast("what's on my screen"), None)
check("screenshots folder isn't a shot", fast("open the screenshots folder"), None)

# ── action: labels, policy, validation ──
check("label", A.tool_label("screenshot", {"mode": "screen"}), "SCREENSHOT → SCREEN")
check("label default", A.tool_label("screenshot", {}), "SCREENSHOT → REGION")
check("no confirmation", A.confirmation_prompt("screenshot", {"mode": "window"}), None)
check("registered", A.TOOLS.get("screenshot") is A.screenshot, True)
check("bad mode refused", A.screenshot("everything")["ok"], False)
A.set_dry_run(True)
check("dry run", A.screenshot("window").get("would"), "screenshot window")
check("dry run default", A.screenshot().get("would"), "screenshot region")
A.set_dry_run(False)


# ── action against a faked HUD ──
class FakeHud:
    def __init__(self, take="ok", result=None, up=True, busy_polls=2):
        self.calls, self.take, self.result, self.up, self.busy_polls = [], take, result, up, busy_polls
        self.last = {"ok": True, "path": "/old.png"}
        self.started = False

    def run(self, cmd, timeout=6):
        self.calls.append(cmd)
        if cmd[:3] == ["qs", "ipc", "call"]:
            if not self.up:
                return 1, "", "No running instances"
            if cmd[4] == "status":
                busy = self.started and self.busy_polls > 0
                if busy:
                    self.busy_polls -= 1
                elif self.started and self.result is not None:
                    self.last = self.result
                return 0, json.dumps({"busy": busy, "last": self.last}), ""
            self.started = self.take == "ok"
            return 0, self.take, ""
        return 0, "ok", ""                         # hyprctl dispatch (fallback)


real_run, real_sleep = A._run, A.time.sleep
A.time.sleep = lambda s: None
try:
    hud = FakeHud(result={"ok": True, "path": "/new.png", "name": "stark-x.png", "width": 1920, "height": 1080, "copied": True})
    A._run = hud.run
    r = A.screenshot("screen")
    check("screen waits for the file", (r.get("ok"), r.get("file"), r.get("size"), r.get("copied")), (True, "stark-x.png", "1920x1080", True))
    check("screen went through the HUD", ["qs", "ipc", "call", "shot", "screen"] in hud.calls, True)

    hud = FakeHud(result={"ok": False, "error": "no focused window"})
    A._run = hud.run
    check("window failure reported", A.screenshot("window"), {"ok": False, "error": "no focused window"})

    hud = FakeHud()
    A._run = hud.run
    r = A.screenshot("region")
    check("region returns at once", (r["ok"], "selector" in r.get("result", ""), sum(c[4] == "status" for c in hud.calls if c[0] == "qs")), (True, True, 1))

    hud = FakeHud(take="busy")
    A._run = hud.run
    check("busy", A.screenshot("screen"), {"ok": False, "error": "a screenshot is already being taken"})

    hud = FakeHud(result=None, busy_polls=10**6)
    A._run = hud.run
    check("never finishes", A.screenshot("screen"), {"ok": False, "error": "the capture didn't finish"})

    hud = FakeHud(up=False)
    A._run = hud.run
    r = A.screenshot("window")
    check("HUD down → stark-shot through Hyprland", (r["ok"], hud.calls[-1]), (True, ["hyprctl", "dispatch", 'hl.dsp.exec_cmd("stark-shot window")']))
finally:
    A._run, A.time.sleep = real_run, real_sleep

# ── router intents (temp copy) ──
tmp = Path(tempfile.mkdtemp())
shutil.copy(R.INTENTS_FILE, tmp / "intents.json")
R.INTENTS_FILE = tmp / "intents.json"
C.DATA_DIR = tmp / "data"
r = R.LocalRouter(C.Config(), record=False, log=lambda *a: None)


def local(text):
    d = r.decide(text, 0.70)
    return (d.intent, d.steps[0]["args"]) if d.path == "local" else d.path


check("router region", local("could you grab me a screenshot"), ("screenshot.region", {"mode": "region"}))
check("router screen", local("capture my display"), ("screenshot.screen", {"mode": "screen"}))
check("router window", local("snap a pic of this window"), ("screenshot.window", {"mode": "window"}))
check("router annotate", local("i want to annotate a screenshot"), ("screenshot.annotate", {"mode": "annotate"}))
check("router: close window isn't a shot", local("close this window"), ("close_window", {}))
check("router: a note isn't a shot", str(local("take a note")).startswith("claude:"), True)
check("router: reading the screen stays Claude", str(local("read this window")).startswith("claude:"), True)
shutil.rmtree(tmp, ignore_errors=True)

# ── stark-shot helpers ──
script = Path.home() / ".local" / "bin" / "stark-shot"
loader = importlib.machinery.SourceFileLoader("stark_shot", str(script))
spec = importlib.util.spec_from_loader("stark_shot", loader)
S = importlib.util.module_from_spec(spec)
loader.exec_module(S)
mons = [{"name": "DP-1", "x": 0, "y": 0, "w": 2560, "h": 1440}, {"name": "eDP-1", "x": 2560, "y": 240, "w": 1920, "h": 1200},
        {"name": "HDMI-A-1", "x": -1920, "y": 0, "w": 1920, "h": 1080}]
check("overlap one monitor", S.overlap((100, 100, 400, 300), mons), [{"name": "DP-1", "x": 100, "y": 100, "w": 400, "h": 300, "area": 120000}])
both = S.overlap((2400, 300, 400, 200), mons)
check("overlap spans two, local coords", [(m["name"], m["x"], m["y"], m["w"], m["h"]) for m in both],
      [("eDP-1", 0, 60, 240, 200), ("DP-1", 2400, 300, 160, 200)])
check("overlap left-of-origin monitor", S.overlap((-1920, 0, 1920, 1080), mons)[0]["name"], "HDMI-A-1")
check("overlap nothing", S.overlap((9000, 9000, 10, 10), mons), [])
check("slurp colours", S.rgba("#ff5a4d", 0x22), "#ff5a4d22")
d = Path(tempfile.mkdtemp())
S.OUT_DIR = d / "Screenshots"


class Frozen(S.datetime):
    @classmethod
    def now(cls, tz=None):
        return S.datetime(2026, 11, 3, 11, 30, 14)


S.datetime = Frozen
p1 = S.target_path()
p1.write_bytes(b"x")
p2 = S.target_path()
p2.write_bytes(b"x")
check("file name (folder made)", p1.name, "stark-20261103-113014.png")
check("same second → -2, -3", (p2.name, S.target_path().name), ("stark-20261103-113014-2.png", "stark-20261103-113014-3.png"))
shutil.rmtree(d, ignore_errors=True)

print("FAIL" if FAILS else "ok", f"{len(FAILS)} failing" if FAILS else "screenshot")
sys.exit(1 if FAILS else 0)
