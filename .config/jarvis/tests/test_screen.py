#!/usr/bin/env python3
"""Window reading + watchers without touching real windows or Claude: naming a target, the never-read
rules, the in-memory PNG, the local change detector (clock flicker ignored, real changes caught), the
watcher manager with fake captures and a fake judge (match / no match / back-off / combat / expiry /
closed window / blocklisted title / max 3 / usage), the judge's reply parsing, the screen tools' results
(fenced as untrusted, image attached), and the gate (a screen read makes later actions ask).
Run: .venv/bin/python tests/test_screen.py"""
import asyncio
import json
import os
import sys
import tempfile
import time
import zlib
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp())
os.environ["JARVIS_DB"] = str(TMP / "jarvis.db")
import numpy as np  # noqa: E402

import jarvis_db as db  # noqa: E402
from core import screen as S  # noqa: E402
from core import watch as W  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


# ── fake desktop ──
WINS = [
    {"address": "0xa1", "class": "kitty", "title": "cargo build", "pid": 11, "workspace": {"id": 1, "name": "1"}, "monitor": 0, "at": [0, 0], "size": [800, 600]},
    {"address": "0xa2", "class": "discord", "title": "#general - Discord", "pid": 12, "workspace": {"id": 2, "name": "2"}, "monitor": 1, "at": [1920, 0], "size": [800, 600]},
    {"address": "0xa3", "class": "zen", "title": "RBC Royal Bank — Zen Browser", "pid": 13, "workspace": {"id": 1, "name": "1"}, "monitor": 0, "at": [800, 0], "size": [800, 600]},
    {"address": "0xa4", "class": "org.kde.polkit-kde-authentication-agent-1", "title": "Authentication Required", "pid": 14, "workspace": {"id": 1, "name": "1"}, "monitor": 0, "at": [10, 10], "size": [300, 200]},
    {"address": "0xa5", "class": "zen", "title": "LEARN - Grades — Zen Browser", "pid": 13, "workspace": {"id": 3, "name": "3"}, "monitor": 0, "at": [0, 0], "size": [800, 600]},
    {"address": "0xa6", "class": "kitty", "title": "htop", "pid": 15, "workspace": {"id": 1, "name": "1"}, "monitor": 0, "at": [0, 600], "size": [800, 600]},
]
MONS = [{"id": 0, "name": "DP-6", "x": 0, "y": 0, "width": 1920, "height": 1080, "scale": 1, "focused": True, "activeWorkspace": {"id": 1}},
        {"id": 1, "name": "DP-5", "x": 1920, "y": 0, "width": 1920, "height": 1080, "scale": 1, "focused": False, "activeWorkspace": {"id": 2}},
        {"id": 2, "name": "eDP-1", "x": 3840, "y": 0, "width": 1920, "height": 1200, "scale": 1, "focused": False, "activeWorkspace": {"id": 4}}]
state = {"active": "0xa1", "locked": False}
S.clients = lambda: [dict(w) for w in WINS]
S.monitors = lambda: [dict(m) for m in MONS]
S.active_window = lambda: next((dict(w) for w in WINS if w["address"] == state["active"]), None)
S.locked = lambda: state["locked"]
cfg = {"jarvisCaptureBlocklist": S.DEFAULT_BLOCKLIST, "jarvisWatchInterval": 10}


def res(t):
    try:
        k, o = S.resolve(t, cfg)
        return k, o.get("address") or o.get("name")
    except S.ScreenError as e:
        return "error", str(e)


check("this window = focused", res("this window"), ("window", "0xa1"))
check("empty = focused", res(""), ("window", "0xa1"))
check("by app", res("the Discord window"), ("window", "0xa2"))
check("by title", res("LEARN"), ("window", "0xa5"))
check("monitor 2 = second from the left", res("what's on monitor 2"), ("monitor", "DP-5"))
check("laptop screen", res("the laptop screen"), ("monitor", "eDP-1"))
check("this screen = focused monitor", res("this screen"), ("monitor", "DP-6"))
check("no such monitor", res("monitor 7")[0], "error")
check("blocklisted title refused", res("the bank window"), ("error", "I won't read that one, sir: its title is on your never-read list"))
check("polkit refused even when named", res("authentication")[0], "error")
check("two kitties, the focused one wins", res("kitty"), ("window", "0xa1"))
state["active"] = "0xa2"
check("two kitties, none focused → ask which", "Which one" in res("kitty")[1], True)
state["active"] = "0xa3"
check("focused window blocklisted → refused", res("this window")[0], "error")
state["active"] = "0xa1"
state["locked"] = True
check("locked → nothing", res("this window"), ("error", "the screen is locked, sir; I don't read anything while it is"))
state["locked"] = False
check("custom blocklist from settings", S.excluded(WINS[1], {"jarvisCaptureBlocklist": ["discord"]}) != "", True)
check("blocklist as a comma string", S.excluded(WINS[1], {"jarvisCaptureBlocklist": "foo, discord"}) != "", True)
check("whole words: 'bmo' doesn't hit 'submodule'", S.excluded({"class": "kitty", "title": "git submodule"}, cfg), "")
check("password managers hard-excluded", S.excluded({"class": "Bitwarden", "title": "Vault"}, {"jarvisCaptureBlocklist": []}) != "", True)
check("hyprlock hard-excluded", S.excluded({"class": "hyprlock", "title": ""}, {"jarvisCaptureBlocklist": []}) != "", True)

# hotplug guard: no capture while the HUD's settle flag is fresh, or of a window on no monitor
# (Hyprland 0.56.2 segfaults on that toplevel export); each skip goes to the journal
logged = []
real_export, real_log, real_flag = S.wlcap.capture_window, S.hud_log, S.SETTLE_FLAG
S.wlcap.capture_window = lambda a: np.zeros((4, 4, 3), np.uint8)
S.hud_log = logged.append
S.SETTLE_FLAG = str(TMP / "stark-hotplug-settling")


def cap_err(addr):
    try:
        S.capture_window({"address": addr}, cfg)
        return None
    except S.ScreenError as e:
        return str(e)


check("guard: plain capture works", cap_err("0xa1"), None)
Path(S.SETTLE_FLAG).touch()
check("guard: settling → no window capture", "still changing" in (cap_err("0xa1") or ""), True)
try:
    S.capture_monitor(MONS[0], cfg)
    mon_err = None
except S.ScreenError as e:
    mon_err = str(e)
check("guard: settling → no monitor capture", "still changing" in (mon_err or ""), True)
os.utime(S.SETTLE_FLAG, (time.time() - 30, time.time() - 30))
check("guard: a stale flag (crashed HUD) holds nothing up", cap_err("0xa1"), None)
os.unlink(S.SETTLE_FLAG)
WINS.append({"address": "0xa9", "class": "mpv", "title": "film", "pid": 19, "workspace": {"id": 7, "name": "7"}, "monitor": -1, "at": [0, 0], "size": [800, 600]})
check("guard: window on no monitor → refused", "between screens" in (cap_err("0xa9") or ""), True)
WINS.pop()
check("guard: skips logged with the window's class", [("mpv" in m or "settling" in m) for m in logged], [True, True, True])
S.wlcap.capture_window, S.hud_log, S.SETTLE_FLAG = real_export, real_log, real_flag

# monitor capture: never-read windows on it are blacked out
S._grim = lambda args: np.full((1080, 1920, 3), 200, np.uint8)
img, _ = S.capture_monitor(MONS[0], cfg)
check("bank window blacked out", int(img[300, 1200].max()), 0)
check("polkit dialog blacked out", int(img[100, 100].max()), 0)
check("the rest kept", int(img[900, 1800].max()), 200)

# ── PNG in memory ──
rgb = (np.arange(24 * 10 * 3) % 251).astype(np.uint8).reshape(10, 24, 3)
p = S.png(rgb)
check("png signature", p[:8], b"\x89PNG\r\n\x1a\n")
idat = p[p.index(b"IDAT") + 4:p.index(b"IEND") - 8]
raw = zlib.decompress(idat)
check("png pixels round-trip", np.frombuffer(raw, np.uint8).reshape(10, 24 * 3 + 1)[:, 1:].reshape(10, 24, 3).tolist(), rgb.tolist())
check("shrink keeps it under the limit", max(S.shrink(np.zeros((3000, 5000, 3), np.uint8)).shape[:2]) <= 1568, True)

# ── local change detection ──
def frame(clock=0, build_done=False, cursor=None):
    f = np.full((600, 960, 3), 30, np.uint8)
    f[40:80, 40:500] = 160                                      # a log line
    f[8:24, 880:940] = 60 + (clock % 2) * 150                   # a clock in the corner, ticking
    if build_done:
        f[300:360, 40:700] = 230                                # "BUILD SUCCEEDED"
    return f


g = S.Grid()
g.compare(S.thumb(frame(0)))
flick = [g.passes(g.compare(S.thumb(frame(i)))) for i in range(1, 9)]
check("ticking clock: learned as noise within a few looks", any(flick[3:]), False)
r = g.compare(S.thumb(frame(9, build_done=True)))
check("a real change passes", g.passes(r), True)
check("region found", r["region"] is not None, True)
check("hash moved", r["hamming"] >= 0, True)
r2 = g.compare(S.thumb(frame(10, build_done=True)))
check("…and settles on the next look", r2["settled"], True)

# ── watcher manager ──
frames = {}
judged = []


async def judge(w, before, now):
    judged.append((w["id"], before.get("text"), now.get("text")))
    return verdict["match"], verdict["say"], 1

verdict = {"match": True, "say": "The build succeeded."}
said, pushed = [], []
paused = {"on": False}
clock = {"t": time.time()}
gone = set()
blocked = set()


def capture(w):
    if w["id"] in gone:
        raise W.WindowGone()
    if w["id"] in blocked:
        raise S.ScreenError("I won't read that one, sir: its title is on your never-read list")
    return frames[w["id"]](), {"address": w["target"]}


wm = W.WatchManager(cfg, pushed.append, lambda title, line: said.append((title, line)), lambda: paused["on"], judge=judge,
                    capture=capture, read_text=lambda w, obj: None, log=lambda *a: None, clock=lambda: clock["t"])
db.time = type("T", (), {"time": staticmethod(lambda: clock["t"])})   # the db stamps rows with the fake clock too


def run(n=1, step=10):
    for _ in range(n):
        clock["t"] += step
        asyncio.run(wm.tick())


# laptop mode (switched on undocked): watchers wait for the dock; nothing is captured
looked = []
wl = W.WatchManager(cfg, pushed.append, lambda t, l: None, lambda: False, judge=judge,
                    capture=lambda w: looked.append(w["id"]) or (_ for _ in ()).throw(W.WindowGone()),
                    read_text=lambda w, obj: None, log=lambda *a: None, clock=lambda: clock["t"], laptop=True)
lw = db.add_watcher("window", "0xa1", "kitty: x", "it changes", 10, 2)
for _ in range(3):
    clock["t"] += 10
    asyncio.run(wl.tick())
check("laptop mode: no captures", looked, [])
check("laptop mode: still active, marked laptop", (db.get_watcher(lw)["status"], wl.item(db.get_watcher(lw))["laptop"]), ("active", True))
db.update_watcher(lw, status="stopped")

a = db.add_watcher("window", "0xa1", "kitty: cargo build", "the build finishes", 10, 2)
tick = {"n": 0}


def kitty():
    tick["n"] += 1
    return frame(tick["n"], build_done=tick.get("done", False))


frames[a] = kitty
run(6)
check("clock ticking: Claude never asked", judged, [])
check("checks counted", db.get_watcher(a)["checks"], 6)
tick["done"] = True
run(3)
check("build done: Claude asked once", len(judged), 1)
check("match → done", db.get_watcher(a)["status"], "done")
check("match → spoken", said[-1], ("WATCH", "Sir, the build succeeded."))
check("judge calls counted", db.get_watcher(a)["calls"], 1)
check("watch turns in today's usage", db.turns_today()["watch"], 1)
check("app told", any(e.get("ev") == "watch" for e in pushed), True)
check("usage pushed to the app", any(e.get("ev") == "usage" and e.get("watch") == 1 for e in pushed), True)

# no match: new baseline, back-off, still watching
judged.clear()
verdict.update(match=False, say="")
b = db.add_watcher("window", "0xa5", "zen: LEARN - Grades", "a new grade appears", 10, 2)
page = {"v": 0}


def learn():
    f = np.full((600, 960, 3), 250, np.uint8)
    f[100 + page["v"] * 60:150 + page["v"] * 60, 50:900] = 20
    return f


frames[b] = learn
run(2)
page["v"] = 1
run(3)
check("unrelated change: asked once", len(judged), 1)
check("…still watching", db.get_watcher(b)["status"], "active")
run(3)
check("same picture again: not asked again", len(judged), 1)
check("no match doubles the gap", wm.state[b].gap, W.JUDGE_GAP_S * 2)
wm.state[b].next_judge = clock["t"] + 1000
page["v"] = 2
run(3)
check("a change inside the back-off waits", len(judged), 1)
wm.state[b].next_judge = 0
run(1)
check("after the back-off: asked", len(judged), 2)
check("gap keeps growing, capped", wm.state[b].gap <= W.JUDGE_GAP_MAX_S and wm.state[b].gap == W.JUDGE_GAP_S * 4, True)

# a minute clock: asked about once, then its cells are learned as noise
judged.clear()
mclock = {"m": 0}


def minute_clock():
    f = np.full((600, 960, 3), 30, np.uint8)
    f[8:24, 780:900] = 200 if mclock["m"] % 2 else 90           # its digits change in place
    return f


m1 = db.add_watcher("window", "0xa6", "kitty: htop", "a new message arrives", 10, 2)
frames[m1] = minute_clock
run(2)
mclock["m"] = 1
run(3)
check("minute clock: asked once", len(judged), 1)
for k in (2, 3, 4, 5):
    mclock["m"] = k
    wm.state[m1].next_judge = 0
    run(3)
check("…a second time (a status line may change twice), then never again", len(judged), 2)
wm.stop(m1)
judged.clear()
wm.state.get(b) and setattr(wm.state[b], "next_judge", 0)

# combat mode: no captures at all
paused["on"] = True
before = db.get_watcher(b)["checks"]
run(5)
check("combat mode: no captures", db.get_watcher(b)["checks"], before)
check("combat flagged for the app", wm.item(db.get_watcher(b))["combat"], True)
paused["on"] = False

# paused by him, from the app
check("pause", wm.pause(b), True)
before = db.get_watcher(b)["checks"]
run(3)
check("paused: no captures", db.get_watcher(b)["checks"], before)
wm.pause(b, False)
run(1)
check("resumed", db.get_watcher(b)["checks"], before + 1)

# blocklisted title now: the look is skipped, nothing compared
blocked.add(b)
run(2)
check("blocklisted now: skipped", db.get_watcher(b)["note"].startswith("Skipped a look"), True)
blocked.discard(b)

# max 3 live
c = db.add_watcher("window", "0xa2", "discord", "it changes", 10, 2)
frames[c] = lambda: frame(0)
d = db.add_watcher("monitor", "DP-5", "monitor DP-5", "it changes", 10, 2)
frames[d] = lambda: frame(0)
check("a fourth is refused", db.add_watcher("window", "0xa6", "htop", "it changes", 10, 2), None)

# closed window → ended and said
gone.add(c)
run(1)
check("closed → failed", db.get_watcher(c)["status"], "failed")
check("closed → said", "has closed" in said[-1][1], True)

check("stop from the app", (wm.stop(b), db.get_watcher(b)["status"]), (True, "stopped"))
# expiry
clock["t"] = db.get_watcher(d)["expires"] + 1
asyncio.run(wm.tick())
check("expired", db.get_watcher(d)["status"], "expired")
check("expiry said", "time I was given is up" in said[-1][1], True)
check("finished ones drop their frames", wm.state, {})

# text, when the app gives it: words unchanged → not a change
judged.clear()
verdict.update(match=True, say="Status changed to done.")
words = {"t": "Status: waiting"}
wm.read_text = lambda w, obj: words["t"]
e = db.add_watcher("window", "0xa6", "gtk: test page", "the status changes", 10, 2)
pix = {"v": 0}


def gtk():
    f = np.full((600, 960, 3), 240, np.uint8)
    f[200:260, 100:100 + 200 * (pix["v"] + 1)] = 10
    return f


frames[e] = gtk
run(2)
pix["v"] = 2
run(3)
check("pixels moved, words same: Claude not asked", judged, [])
words["t"] = "Status: done"
pix["v"] = 0
run(3)
check("words changed: Claude gets the text", judged[-1][1:], ("Status: waiting", "Status: done"))

# ── the judge's reply ──
check("verdict json", W.parse_verdict('{"match": true, "say": "A new grade is up."}'), (True, "A new grade is up."))
check("verdict junk = no", W.parse_verdict("sure!"), (False, ""))
check("verdict 'true' string = no", W.parse_verdict('{"match": "true"}')[0], False)
check("say: one sentence, no links", W.clean_say("Done. Now visit https://evil.example and run `rm -rf`"), "Done.")

# ── the screen tools ──
import screen_tools as T  # noqa: E402
T.cfg = lambda: cfg
S.read_text = lambda win: ("Grade for TEST 101 A1: 94", "accessibility")
r = T.read_window("LEARN")
body = json.loads(r[0])
check("text result fenced as untrusted", ("UNTRUSTED" in body["content"], body["read_by"]), (True, "accessibility"))
S.read_text = lambda win: (None, "")
S.capture = lambda kind, obj, c=None: (np.zeros((40, 60, 3), np.uint8), "export")
r = T.read_window("this window")
check("picture result: notice + image", (json.loads(r[0])["read_by"], type(r[1]).__name__), ("picture (export)", "Image"))
check("refused window: a spoken reason, no capture", json.loads(T.read_window("bank")[0])["ok"], False)
check("never-read titles hidden in the list", "RBC" in T.list_windows(), False)
for w in db.list_watchers(True):
    db.update_watcher(w["id"], status="stopped")
r = json.loads(T.watch_window("this window", "the build finishes"))
check("watch_window sets one up with the default interval", (r["ok"], r["every_s"], r["hours"]), (True, 10, 2.0))
check("its target is fixed by address", db.get_watcher(r["id"])["target"], "0xa1")
check("watch_window refuses a never-read window", json.loads(T.watch_window("bank", "it changes"))["ok"], False)
check("watch_list", len(json.loads(T.watch_list())["watchers"]), 1)
check("watch_stop", json.loads(T.watch_stop(all=True))["stopped"], 1)

# ── kitty's own text: get-text-only password, user-only socket ──
import importlib.util  # noqa: E402
import socket as _socket  # noqa: E402
import stat as _stat  # noqa: E402
import subprocess as _sp  # noqa: E402

run_dir = TMP / "run"
run_dir.mkdir(mode=0o700)
os.environ["XDG_RUNTIME_DIR"] = str(run_dir)
check("no socket → nothing", S._kitty_socket(4242), None)
(run_dir / "kitty-rc-4242").write_text("")
check("a plain file isn't a socket", S._kitty_socket(4242), None)
(run_dir / "kitty-rc-4242").unlink()
srv = _socket.socket(_socket.AF_UNIX)
srv.bind(str(run_dir / "kitty-rc-4242"))
check("the user's socket file is used", S._kitty_socket(4242), f"unix:{run_dir}/kitty-rc-4242")
check("pid must be a number", S._kitty_socket("4242; rm"), None)
_lstat = os.lstat
os.lstat = lambda p: type("St", (), {"st_mode": _stat.S_IFSOCK | 0o777, "st_uid": os.getuid() + 1})()
check("someone else's socket is refused", S._kitty_socket(4242), None)
os.lstat = _lstat

calls = []
S._kitty_password = lambda: "s3cret-pw"
S._kitty_public_key = lambda pid: "1:PUBKEY"
os.environ["KITTY_WINDOW_ID"] = "7"                  # as if Jarvis itself ran inside a kitty


def fake_run(args, **kw):
    calls.append((args, kw.get("env", {})))
    return _sp.CompletedProcess(args, 0, "line one\nline two\n", "")


_run = S.subprocess.run
S.subprocess.run = fake_run
check("kitty text read", S.kitty_text({"pid": 4242, "title": "t"}), "line one\nline two")
args, env = calls[-1]
check("password never on the command line", any("s3cret" in a for a in args), False)
check("password + that kitty's key in the env", (env.get("KITTY_RC_PASSWORD"), env.get("KITTY_PUBLIC_KEY")), ("s3cret-pw", "1:PUBKEY"))
check("our own kitty env not passed on", "KITTY_WINDOW_ID" in env, False)
check("only get-text is asked for", [a for a in args if a in ("get-text", "send-text", "ls", "launch")], ["get-text"])
S._kitty_password = lambda: None
calls.clear()
check("no password in the keyring → no request", (S.kitty_text({"pid": 4242}), calls), (None, []))
S.subprocess.run = _run
srv.close()

spec = importlib.util.spec_from_file_location("rc_check", os.path.expanduser("~/.config/kitty/jarvis-rc-check.py"))
rc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rc)
check("checker: get-text over the socket", rc.is_cmd_allowed({"cmd": "get-text"}, None, True, {}), True)
check("checker: get-text over the TTY refused", rc.is_cmd_allowed({"cmd": "get-text"}, None, False, {}), False)
for cmd in ("send-text", "send-key", "launch", "ls", "close-window", "set-colors", "run", "action"):
    check(f"checker refuses {cmd}", rc.is_cmd_allowed({"cmd": cmd}, None, True, {}), False)

fake_bin = TMP / "bin"
fake_bin.mkdir()
inc = os.path.expanduser("~/.config/kitty/jarvis-rc-password.sh")
for pw, want in (("abcDEF_123-x", 'remote_control_password "abcDEF_123-x" jarvis-rc-check.py\n'),
                 ('bad" yes', ""), ("", "")):
    (fake_bin / "secret-tool").write_text(f"#!/bin/sh\nprintf '%s' '{pw}'\n")
    (fake_bin / "secret-tool").chmod(0o755)
    r = _sp.run([inc], capture_output=True, text=True, env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"})
    check(f"include for {pw!r}", (r.returncode, r.stdout), (0, want))

# ── the gate: a screen read makes what follows ask ──
from core import brain as B  # noqa: E402
from core import config as C  # noqa: E402


class Cfg(dict):
    def model_for(self, strong):
        return "haiku"


asked = []


async def confirm(prompt):
    asked.append(prompt)
    return True

C.load_servers = lambda dry_run=False: ({}, {
    "stark": {"policy": "stark", "auto_allow": set()},
    "screen": {"policy": "screen", "name": "screen", "read_only": True, "auto_allow": set(),
               "read_tools": {"read_window", "list_windows"}, "auto_write": {}},
})
C.integrations = lambda raw=None: {}
brain = B.Brain(Cfg(), confirm, lambda label: None, log=lambda *a: None)


def gate(tool, args=None, fresh=False):
    if fresh or brain._req is None:
        brain._req = {"text": "x", "count": 0, "tools": [], "calls": [], "error": "", "tainted": "", "deadline": 1e18}
    asked.clear()
    r = asyncio.run(brain._gate(tool, args or {}, None))
    return type(r).__name__.replace("PermissionResult", ""), len(asked)


check("read_window runs freely", gate("mcp__screen__read_window", {"target": "this window"}, fresh=True), ("Allow", 0))
check("after reading the screen, a desktop action asks", gate("mcp__stark__set_theme", {"preset": "matrix"}), ("Allow", 1))
check("…and says why", "reading your screen" in asked[0], True)
check("watch_window untainted: no question", gate("mcp__screen__watch_window", fresh=True), ("Allow", 0))
gate("mcp__screen__read_window", fresh=True)
check("watch_window after a read: asks", gate("mcp__screen__watch_window"), ("Allow", 1))
check("a second read stays free", gate("mcp__screen__read_window"), ("Allow", 0))

# Hyprland 0.57: special workspaces have no id (clients, monitors, workspaces): only address / type / name
SPECIAL = {"address": "special:music", "type": "special", "name": "special:music"}
NONE = {"address": "", "type": "", "name": ""}
check("ws_name of a 0.57 special workspace", S.ws_name(SPECIAL), "special:music")
check("ws_name falls back to the id", S.ws_name({"id": 3}), "3")
check("monitor with no special open", S.shown_on({"activeWorkspace": {"id": 1, "name": "1"}, "specialWorkspace": NONE}), {"1"})
check("monitor with a special open", S.shown_on({"activeWorkspace": {"id": 1, "name": "1"}, "specialWorkspace": SPECIAL}),
      {"1", "special:music"})
_mons = S.monitors
S.monitors = lambda: [{"id": 0, "name": "eDP-1", "activeWorkspace": {"id": 1, "name": "1"}, "specialWorkspace": NONE}]
check("window on a closed special workspace isn't visible", S._visible({"monitor": 0, "workspace": SPECIAL}), False)
S.monitors = lambda: [{"id": 0, "name": "eDP-1", "activeWorkspace": {"id": 1, "name": "1"}, "specialWorkspace": SPECIAL}]
check("…and is once it's open", S._visible({"monitor": 0, "workspace": SPECIAL}), True)
S.monitors = _mons
_clients, _grim = S.clients, S._grim
S.clients = lambda: [{"address": "0xs1", "class": "org.keepassxc.KeePassXC", "title": "Vault", "workspace": SPECIAL,
                      "at": [10, 10], "size": [20, 20]},
                     {"address": "0xs2", "class": "kitty", "title": "zsh", "workspace": {"id": 1, "name": "1"}, "at": [40, 0], "size": [20, 20]}]
S._grim = lambda args: np.full((100, 100, 3), 200, np.uint8)
img, _ = S.capture_monitor({"name": "eDP-1", "x": 0, "y": 0, "width": 100, "height": 100, "scale": 1,
                            "activeWorkspace": {"id": 1, "name": "1"}, "specialWorkspace": SPECIAL}, cfg)
check("monitor read with a 0.57 special workspace: never-read window blacked out", (int(img[15, 15, 0]), int(img[5, 45, 0])), (0, 200))
S.clients, S._grim = _clients, _grim

raw = json.loads(open(os.path.join(ROOT, "servers.json")).read())
check("screen server registered", (raw["screen"]["policy"], sorted(raw["screen"]["read_tools"])), ("screen", ["list_windows", "read_window"]))

# nothing in the capture path writes files
src = open(os.path.join(ROOT, "core", "screen.py")).read() + open(os.path.join(ROOT, "core", "wlcap.py")).read() \
    + open(os.path.join(ROOT, "core", "watch.py")).read() + open(os.path.join(ROOT, "mcp", "screen_tools.py")).read()
check("no file writes in the capture path", any(x in src for x in ("open(", ".write_bytes", ".write_text", "imwrite", "np.save")), False)

print("\n" + ("FAILED: " + ", ".join(FAILS) if FAILS else "all screen tests passed"))
sys.exit(1 if FAILS else 0)
