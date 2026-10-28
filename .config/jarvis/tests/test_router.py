#!/usr/bin/env python3
"""Local router: decisions, phase-2 pass-through, self-learning and `jarvis intents remove`.
Learning runs against a temp copy of intents.json. Nothing executes. Run: python tests/test_router.py"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import config as C  # noqa: E402
from core import router_local as R  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


tmp = Path(tempfile.mkdtemp())
shutil.copy(R.INTENTS_FILE, tmp / "intents.json")
R.INTENTS_FILE = tmp / "intents.json"
C.DATA_DIR = tmp
r = R.LocalRouter(C.Config(), record=False, log=lambda *a: None)


def path(text):
    return r.decide(text, 0.70).path


def local(text):
    d = r.decide(text, 0.70)
    return (d.intent, d.steps[0]["tool"], d.steps[0]["args"]) if d.path == "local" else d.path


check("vpn proton", local("hook me up to proton"), ("vpn.control", "vpn", {"action": "connect_proton"}))
check("brightness slot", local("dim the lights to 20%"), ("lights.brightness", "lights", {"action": "brightness", "value": 20}))
check("volume ignores 'to'", local("set the volume to 35")[2], {"action": "set_volume", "value": 35})
check("timer + label slots", R.fill_slots({"minutes": "minutes", "label": "timer_label?"}, "set an egg timer for six minutes"), ({"minutes": 6, "label": "egg"}, []))
check("workspace", local("jump over to workspace four")[2], {"n": 4})
check("missing slot", path("set the volume").startswith("claude:"), True)
check("anchor: open ≠ close", path("open it").startswith("claude:"), True)
check("negation", path("don't turn off the lights"), "claude:negation")
check("compound", path("dim the lights and play some jazz").startswith("claude:"), True)
check("chat", path("why do cats purr").startswith("claude:"), True)
for t in ["any new emails", "what's on my calendar today", "when is cs 137 a6 due", "did my midterm get graded",
          "find the lab report in my drive", "check my inbox please"]:
    check(f"phase 2 never local: {t}", path(t), "claude:claude-only")
intents = R.load_intents()["intents"]
for k in ("claude.email", "claude.calendar", "claude.docs", "claude.assignments", "claude.grades"):
    check(f"{k} is claude-only", intents[k]["kind"], "claude-only")
check("every tool intent names a real tool", all(it["tool"] in R.A.TOOLS for it in intents.values() if it.get("kind", "tool") == "tool"), True)

# ── self-learning ──
check("learn new phrasing", r.learn("make the lights a cozy 30 percent", "lights", {"action": "brightness", "value": 30}), "lights.brightness")
check("learned saved", "make the lights a cozy 30 percent" in R.load_intents()["intents"]["lights.brightness"]["learned"], True)
check("dedupe", r.learn("Make the lights a cozy 30 percent.", "lights", {"action": "brightness", "value": 30}), None)
check("args must match the transcript", r.learn("make it cozy in here", "lights", {"action": "brightness", "value": 30}), None)
check("never learn phase 2", r.learn("check my email and dim the lights to 30", "lights", {"action": "brightness", "value": 30}), None)
check("never learn compound", r.learn("dim the lights to 30 and play jazz", "lights", {"action": "brightness", "value": 30}), None)
check("now decided locally", local("make the lights a cozy 40 percent")[0], "lights.brightness")
for i in range(R.LEARN_CAP + 3):
    r.learn(f"workspace number {i % 9 + 1} now {'please ' * (i // 9)}go", "switch_workspace", {"n": i % 9 + 1})
check("cap per intent", len(R.load_intents()["intents"]["switch_workspace"]["learned"]) <= R.LEARN_CAP, True)

# ── jarvis intents remove ──
before = sum(len(it.get("learned", [])) for it in R.load_intents()["intents"].values())
R.cli(["remove", "1"])
after = sum(len(it.get("learned", [])) for it in R.load_intents()["intents"].values())
check("remove one", before - after, 1)
check("file stays valid json", isinstance(json.loads(R.INTENTS_FILE.read_text()), dict), True)

shutil.rmtree(tmp)
print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
