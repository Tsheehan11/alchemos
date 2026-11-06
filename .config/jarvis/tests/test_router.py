#!/usr/bin/env python3
"""Local router: decisions, phase-2 pass-through, self-learning (into the untracked learned file),
migration out of intents.json, the vector cache and `jarvis intents remove`. Runs against a temp copy
of intents.json and a temp data dir. Nothing executes. (The learning rules themselves: test_router_learning.py.) Run: python tests/test_router.py"""
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
os.environ["JARVIS_DB"] = os.path.join(tempfile.mkdtemp(), "jarvis.db")   # the gate reads outcomes: never his
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
C.DATA_DIR = tmp / "data"

# ── migration: "learned" lists left in intents.json move to the learned file ──
old = json.loads(R.INTENTS_FILE.read_text())
old["intents"]["media.pause"]["learned"] = ["put the tunes on hold"]
old["intents"]["media.next"]["learned"] = []
R.INTENTS_FILE.write_text(json.dumps(old, indent=2))
check("migrated count", R.migrate_learned(), 1)
check("learned store has it, as a candidate to re-check", [(x["intent"], x["text"], x["state"]) for x in R.L.read()["examples"].values()],
      [("media.pause", "put the tunes on hold", "candidate")])
check("intents.json has no learned keys", any("learned" in it for it in R.load_intents()["intents"].values()), False)
check("second migration is a no-op", R.migrate_learned(), 0)
pristine = R.INTENTS_FILE.read_text()

r = R.LocalRouter(C.Config(), record=False, log=lambda *a: None, settle=True)
check("migrated example re-checked at settle", R.L.read()["examples"]["1"]["state"] in ("active", "rejected"), True)
check("active examples merged at load", "put the tunes on hold" in r.texts, R.L.read()["examples"]["1"]["state"] == "active")
check("one vector per example", len(r.vecs), len(r.texts))


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
check("speak quieter = Jarvis's voice", local("jarvis speak quieter")[1:], ("jarvis_volume", {"action": "down"}))
check("set your volume to 40", local("set your volume to 40 percent")[2], {"action": "set", "percent": 40})
check("music volume stays media", local("set the volume to 40")[1], "media")
check("'your voice' alone isn't volume", path("make your voice deeper").startswith("claude:"), True)
for t in ["any new emails", "what's on my calendar today", "when is cs 137 a6 due", "did my midterm get graded",
          "find the lab report in my drive", "check my inbox please"]:
    check(f"phase 2 never local: {t}", path(t), "claude:claude-only")
# regressions (2026-11-06), from the built-in examples alone (this store is empty): "rest" isn't play,
# a "voice" request is never the music volume, "keep the music going" isn't pause
for text, want in [("give the music a rest", "media.pause"), ("give it a rest", "media.pause"), ("let the music rest", "media.pause"),
                   ("rest the music", "media.pause"), ("keep the music going", "media.play"),
                   ("louder voice please", "voice.volume_up"), ("a louder voice", "voice.volume_up"), ("voice louder", "voice.volume_up"),
                   ("speak up", "voice.volume_up"), ("talk louder", "voice.volume_up"), ("quieter voice please", "voice.volume_down"),
                   ("softer voice", "voice.volume_down"), ("louder music", "media.volume_up")]:
    check(f"regression: {text}", local(text)[0], want)
for text in ["use a quieter voice", "louder voice please", "voice up", "softer voice"]:
    d = r.decide(text, 0.70)
    check(f"voice never moves the music: {text}", d.path == "local" and d.intent.startswith("media."), False)
from core import fastpath as F  # noqa: E402
fp = lambda t: [(s["tool"], s["args"].get("action") or s["args"].get("type")) for s in (F.match(t) or [])]  # noqa: E731
check("fast: start the music = play", fp("start the music"), [("media", "play")])
check("fast: kill the music isn't the widget", fp("kill the music"), [])
check("fast: the music widget still works", fp("start the music widget"), [("widget_add", "media")])
check("fast: kill the music widget still works", fp("kill the music widget")[0][0], "widget_remove")
check("fast: music on a screen still the widget", fp("start the music on monitor 2"), [("widget_add", "media")])
intents = R.load_intents()["intents"]
for k in ("claude.email", "claude.calendar", "claude.docs", "claude.assignments", "claude.grades"):
    check(f"{k} is claude-only", intents[k]["kind"], "claude-only")
check("every tool intent names a real tool", all(it["tool"] in R.A.TOOLS for it in intents.values() if it.get("kind", "tool") == "tool"), True)

# ── self-learning ──
check("learn new phrasing", r.learn("make the lights a cozy 30 percent", "lights", {"action": "brightness", "value": 30}), "lights.brightness")
check("learned saved to the learned file", "make the lights a cozy 30 percent" in R.load_learned()["lights.brightness"], True)
check("intents.json untouched by learning", R.INTENTS_FILE.read_text(), pristine)
n = len(R.L.read()["examples"])
r.learn("Make the lights a cozy 30 percent.", "lights", {"action": "brightness", "value": 30})
check("dedupe", len(R.L.read()["examples"]), n)
check("args must match the transcript", r.learn("make it cozy in here", "lights", {"action": "brightness", "value": 30}), None)
check("never learn phase 2", r.learn("check my email and dim the lights to 30", "lights", {"action": "brightness", "value": 30}), None)
check("never learn compound", r.learn("dim the lights to 30 and play jazz", "lights", {"action": "brightness", "value": 30}), None)
check("now decided locally", local("make the lights a cozy 40 percent")[0], "lights.brightness")
for i in range(R.LEARN_CAP + 3):
    r.learn(f"workspace number {i % 9 + 1} now {'please ' * (i // 9)}go", "switch_workspace", {"n": i % 9 + 1})
check("cap per intent", len(R.load_learned()["switch_workspace"]) <= R.LEARN_CAP, True)

# ── the vector cache: a fresh router loads the rebuilt cache instead of re-embedding ──
calls = []
r2 = R.LocalRouter.__new__(R.LocalRouter)
r2.cfg, r2.log, r2.record, r2.lock, r2.emb = r.cfg, (lambda *a: None), False, r.lock, r.emb
real = r.emb
r2.emb = type("Spy", (), {"name": real.name, "__call__": lambda self, ts: calls.append(len(ts)) or real(ts)})()
r2._load()
check("cache hit after learning", calls, [])
check("cache matches merged examples", (len(r2.vecs), r2.texts), (len(r.vecs), r.texts))

# ── jarvis intents remove (→ jarvis router forget) ──
before = sum(map(len, R.load_learned().values()))
R.cli(["remove", next(x["id"] for x in R.L.read()["examples"].values() if x["state"] == "active")])
after = sum(map(len, R.load_learned().values()))
check("remove one", before - after, 1)
check("remove leaves intents.json alone", R.INTENTS_FILE.read_text(), pristine)
check("learned file stays valid json", isinstance(json.loads(R.learned_file().read_text()), dict), True)

shutil.rmtree(tmp)
print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
