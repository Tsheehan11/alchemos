#!/usr/bin/env python3
"""Screen roles (set_screen_role, quickshell/Roles.qml) vs desktop widgets: fast-path wording rules,
the "Panel or widget?" question and its learned answer, the router intent and the action in dry-run.
Runs against a temp copy of intents.json and a temp data dir. Nothing executes.
Run: python tests/test_screen_roles.py"""
import shutil
import sys
import os
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

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


def kind(text):
    """'role:<screen>:<role>' | 'widget:<type>' | 'ask' | other tool | None"""
    s = F.match(text)
    if not s:
        return None
    if s[0].get("choice"):
        return "ask"
    t, a = s[0]["tool"], s[0]["args"]
    if t == "set_screen_role":
        return f"role:{a['screen']}:{a['role']}"
    if t == "widget_add":
        return f"widget:{a['type']}"
    return t


# ── wording: role ──
check("TV", kind("put music on the TV"), "role:tv:music")
check("TV, with 'the' (whisper drops / adds it)", kind("put the music on the tv"), "role:tv:music")
check("no verb", kind("clock on monitor 2"), "role:monitor 2:clock")
check("'screen'", kind("stats on screen 2"), "role:monitor 2:stats")
check("laptop screen", kind("show a clock on the laptop screen"), "role:laptop:clock")
check("set <screen> to", kind("set the laptop screen to stats"), "role:laptop:stats")
check("set form, no verb", kind("TV to clock"), "role:tv:clock")
check("set monitor", kind("switch monitor 1 to music"), "role:monitor 1:music")
check("nothing on", kind("nothing on monitor 2"), "role:monitor 2:none")
check("none on", kind("none on the second monitor"), "role:diag:none")
check("panel", kind("show the music panel on monitor 2"), "role:monitor 2:music")
check("hud", kind("put the clock hud on the main monitor"), "role:main:clock")
# ── wording: widget ──
check("'widget'", kind("put a music widget on monitor 2"), "widget:media")
check("timer", kind("set a timer for 5 minutes on monitor 2"), "set_timer")
check("clock for a city", kind("put a clock for new york on monitor 2"), "widget:clock")
check("analog clock", kind("put an analog clock on monitor 2"), "widget:clock")
# ── wording: ambiguous ──
check("ambiguous music", kind("put music on monitor 2"), "ask")
check("ambiguous, article doesn't matter", kind("put the music on monitor 2") == kind("put music on monitor 2"), True)
check("ambiguous stats", kind("show stats on the second monitor"), "ask")
check("ambiguous clock", kind("put a clock on monitor 2"), "ask")
ask = F.match("put music on monitor 2")[0]
check("question", ask["say"], "Panel or widget, sir?")
check("panel option", ask["choice"]["panel"][0]["args"], {"screen": "monitor 2", "role": "music"})
check("widget option", ask["choice"]["widget"][0]["args"]["type"], "media")
for a, want in [("panel", "panel"), ("the panel", "panel"), ("um the screen", "panel"), ("widget", "widget"),
                ("a widget please", "widget"), ("play some jazz", None), ("yes", None)]:
    check(f"answer {a!r}", F.choice_answer(a), want)

# ── action (dry-run) ──
A.set_dry_run(True)
check("dry tv", A.set_screen_role("the TV", "music").get("would"), "roles set tv music")
check("dry laptop none", A.set_screen_role("laptop screen", "nothing").get("would"), "roles set laptop none")
check("dry current", A.set_screen_role("", "stats").get("would"), "roles set current stats")
check("bad role", A.set_screen_role("tv", "jazz")["ok"], False)
check("bad screen", A.set_screen_role("the fridge", "music")["ok"], False)
check("in TOOLS", "set_screen_role" in A.TOOLS, True)
check("label", A.tool_label("set_screen_role", {"screen": "the TV", "role": "music"}), "SCREEN → TV ⇢ MUSIC")

# ── router: intent, slots, learning the answer ──
tmp = Path(tempfile.mkdtemp())
shutil.copy(R.INTENTS_FILE, tmp / "intents.json")
R.INTENTS_FILE = tmp / "intents.json"
C.DATA_DIR = tmp / "data"
r = R.LocalRouter(C.Config(), record=False, log=lambda *a: None)
check("slots", R.fill_slots({"screen": "role_screen?", "role": "screen_role"}, "put music on monitor 2"),
      ({"screen": "monitor 2", "role": "music"}, []))
d = r.decide("could you put the visualizer on the tv", 0.70)
check("router: novel role phrasing", (d.path, d.steps[0]["args"] if d.steps else None),
      ("local", {"screen": "tv", "role": "music"}))
check("router: widget stays widget", r.decide("add a music widget", 0.70).intent, "widget.media")


def jarvis_stub():
    """Just what Jarvis._panel_or_widget / _choice_answer use."""
    import jarvis as J
    j = SimpleNamespace(router=r, dry_run=False, learning=[], pending_choice=None)
    j._panel_or_widget = lambda text, steps: J.Jarvis._panel_or_widget(j, text, steps)
    j._choice_answer = lambda text: J.Jarvis._choice_answer(j, text)
    return j


def route(j, text):
    """Jarvis._handle's fast-path part → tool of the first step, or 'ask'."""
    steps = j._choice_answer(text)
    if steps is None:
        steps = F.match(text)
        if steps and steps[0].get("choice"):
            steps = j._panel_or_widget(text, steps)
    for th in j.learning:
        th.join(10)
    if not steps:
        return None
    return "ask" if steps[0].get("choice") else steps[0]["tool"]


j = jarvis_stub()
check("first time: asks", route(j, "put music on monitor 2"), "ask")
check("answer panel runs the role", route(j, "the panel"), "set_screen_role")
check("learned as screen.role", "put music on monitor 2" in R.load_learned().get("screen.role", []), True)
check("second time: no question", route(j, "put music on monitor 2"), "set_screen_role")
check("other ambiguous phrasing still asks", route(j, "put the clock on the second monitor"), "ask")
check("answer widget runs the widget (moves the clock)", route(j, "widget"), "widget_move")
check("no widget_move intent: kept as choice.widget", "put the clock on the second monitor" in R.load_learned().get("choice.widget", []), True)
check("remembered widget (choice)", route(j, "put the clock on the second monitor"), "widget_move")
check("already a widget.stats example", r.known_intent("show stats on the second monitor"), "widget.stats")
check("remembered widget", route(j, "show stats on the second monitor"), "widget_add")
check("unrelated reply drops the question", (route(j, "put a clock on monitor 2"), route(j, "what time is it"),
                                             j.pending_choice), ("ask", None, None))
j.pending_choice = (F.match("put a clock on monitor 2")[0]["choice"], time.monotonic() - 120)
check("stale answer ignored", route(j, "panel"), None)
check("router still loads with choice.* keys", (r._load(), len(r.vecs) == len(r.texts))[1], True)

shutil.rmtree(tmp)
print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
