#!/usr/bin/env python3
"""Router learning (core/router_learn.py + core/router_local.py + the signals in jarvis.py): v1 migration,
promotion through the gate, rejection by the eval / his history / the word check, blocked intents, demotion
and deletion on negatives, per-intent calibration, the "Did you mean …?" band, dedupe / cap / decay, the
`jarvis router` CLI, persona independence, and the live signals (correction, "no I meant", undo, reworded
repeat, inverse, kill switch, declined, weak positive, ask yes / no) through Jarvis.handle with a fake
Claude and fake tools. Temp intents.json, data dir and DB; nothing real runs. Run: python tests/test_router_learning.py"""
import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp())
os.environ["JARVIS_DB"] = str(TMP / "jarvis.db")
import jarvis_db as db  # noqa: E402
from core import config as C  # noqa: E402
from core import router_learn as L  # noqa: E402
from core import router_local as R  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


shutil.copy(R.INTENTS_FILE, TMP / "intents.json")
R.INTENTS_FILE = TMP / "intents.json"
C.DATA_DIR = TMP / "data"
C.DATA_DIR.mkdir()
pristine = R.INTENTS_FILE.read_text()
quiet = lambda *a: None   # noqa: E731


class Cfg(C.Config):
    """The real defaults, but Settings values these tests set."""
    over = {}

    def __getitem__(self, k):
        return self.over.get(k, C.Config.__getitem__(self, k))


cfg = Cfg()
Cfg.over = {"jarvisRouterThreshold": 0.70, "jarvisRouterAsk": True, "jarvisDecisions": "local"}


def state(text, intent=None):
    for r in L.read()["examples"].values():
        if r["text"] == text and (intent is None or r["intent"] == intent):
            return r["state"]
    return None


# ── v1 file (the 2026-10-28 format, with the garbage it really had) → candidates, re-checked at settle ──
L.path().write_text(json.dumps({"_doc": "old", "learned": {
    "media.next": ["get it", "and skimp"], "move_window": ["move it to windows 4"], "set_theme": ["mark iii"],
    "what_is_playing": ["how's music"], "choice.panel": ["put the music on monitor two"]}}))
up = L.read()
check("v1 → candidates", sorted(r["state"] for r in up["examples"].values()), ["candidate"] * 5)
check("v1 choices kept apart", up["choices"], {"panel": ["put the music on monitor two"]})
r = R.LocalRouter(cfg, record=False, log=quiet, settle=True)
check("migrated: 'get it' rejected (no supporting words)", state("get it"), "rejected")
check("migrated: 'and skimp' rejected", state("and skimp"), "rejected")
check("migrated: blocked intent rejected", state("move it to windows 4"), "rejected")
check("migrated: 'mark iii' promoted", state("mark iii"), "active")
check("migrated: 'how's music' promoted", state("how's music"), "active")
check("rejections say why", all(x["why"] for x in L.read()["examples"].values() if x["state"] == "rejected"), True)
check("events logged", {e["kind"] for e in L.read()["events"]} >= {"migrated", "promoted", "rejected"}, True)
check("intents.json untouched", R.INTENTS_FILE.read_text(), pristine)
check("choice still known", r.known_intent("put the music on monitor two"), "choice.panel")

# ── learn from Claude: one confirm promotes through the gate ──
check("claude call → promoted", r.learn("make the lights a cozy 30 percent", "lights", {"action": "brightness", "value": 30}),
      "lights.brightness")
check("active in the store", state("make the lights a cozy 30 percent"), "active")
check("now local", r.decide("make the lights a cozy 40 percent", 0.70).path, "local")
check("args must come from the words", r.learn("make it cozy in here", "lights", {"action": "brightness", "value": 30}), None)
check("compound never", r.learn("dim the lights to 30 and play jazz", "lights", {"action": "brightness", "value": 30}), None)
check("integration words never", r.learn("check my email and dim the lights to 30", "lights", {"action": "brightness", "value": 30}), None)
n = len(L.read()["examples"])
check("near-identical = same example", r.learn("Make the lights a cozy 30 percent, please.", "lights", {"action": "brightness", "value": 30}),
      "lights.brightness")
check("no duplicate record", len(L.read()["examples"]), n)
check("built-in phrasing adds nothing", (r.learn("resume my music", "media", {"action": "play"}), len(L.read()["examples"])),
      ("media.play", n))

# ── blocked intents: never a candidate, never asked about ──
for text, tool, args in [("put the machine to bed", "power", {"action": "suspend"}),
                         ("lock it all up", "lock_screen", {}),
                         ("get rid of this window", "close_focused_window", {}),
                         ("chuck this over to workspace 3", "move_window_to_workspace", {"n": 3}),
                         ("wipe the widgets", "widget_remove", {"target": "all"}),
                         ("get me off the vpn", "vpn", {"action": "disconnect"})]:
    check(f"blocked: {tool}", r.learn(text, tool, args), None)
    check(f"blocked: no record for {tool}", any(x["text"] == R.clean(text) for x in L.read()["examples"].values()), False)
for name in ("claude.email", "claude.calendar", "claude.docs", "claude.assignments", "claude.grades", "power",
             "close_window", "move_window", "widget.clear", "vpn.control", "lock_screen"):
    check(f"blocked: {name}", L.blocked(name, R.load_intents()["intents"][name]), True)
check("add_evidence refuses blocked", r.add_evidence("power", "nap time", "ask", confirm=True), None)

# ── the gate: the eval and his own history ──
with L.edit() as st:
    bad = L.add_record(st, "media.next", "why do cats purr", "claude", confirms=1)
ok, why = r.approve(bad["id"])
check("gate: eval would act on a question → refused", (ok, "eval" in why), (False, True))
check("refused stays out of the router", "why do cats purr" in r.texts, False)
db.log_outcome("crank up the tunes", "media.volume_up", 0.72, "", "neg", "correction")
with L.edit() as st:
    hist = L.add_record(st, "media.volume_up", "crank up the tunes", "claude", confirms=1)
ok, why = r.approve(hist["id"])
check("gate: history — a corrected request may not act again", (ok, "corrected" in why), (False, True))

# ── negatives: demote, then delete; the words stop acting; threshold goes up; built-ins untouched ──
rid = next(x["id"] for x in L.read()["examples"].values() if x["text"] == "make the lights a cozy 30 percent")
d = r.decide("make the lights a cozy 30 percent", 0.70)
check("matched the learned example", (d.path, d.example), ("local", rid))
r.outcome(d.info(), "neg", "correction")
check("first negative demotes", state("make the lights a cozy 30 percent"), "candidate")
check("the exact words no longer act", r.decide("make the lights a cozy 30 percent", 0.70).path, "claude:unlearned")
check("demoted never re-promotes on its own", L.ready(L.read()["examples"][rid]), False)
r.outcome(dict(d.info(), example=rid), "neg", "undo")
check("second negative deletes", rid in L.read()["examples"], False)
check("threshold raised for that intent", r.threshold_for("lights.brightness", 0.70) > 0.70, True)
check("other intents unchanged", r.threshold_for("media.pause", 0.70), 0.70)
check("built-ins untouched", R.INTENTS_FILE.read_text(), pristine)

# ── calibration ──
check("no outcomes → no offset", L.calibrate([], 0.70), 0.0)
check("a negative at 0.74 → just above it", L.calibrate([(0.74, False)], 0.70), 0.05)
check("raise is capped", L.calibrate([(0.99, False)], 0.70), L.MAX_RAISE)
check("rare negatives among many positives tolerated", L.calibrate([(0.8, True)] * 12 + [(0.8, False)], 0.70), 0.0)
check("lower only with 3 yes in the band", L.calibrate([(0.67, True), (0.68, True)], 0.70), 0.0)
check("3 yes in the band → lower", L.calibrate([(0.67, True), (0.68, True), (0.675, True)], 0.70), -0.03)
check("a no in the band blocks lowering", L.calibrate([(0.67, True), (0.68, True), (0.675, True), (0.69, False)], 0.70), 0.0)
check("blocked intents never lowered", L.calibrate([(0.67, True)] * 5, 0.70, may_lower=False), 0.0)
for s in (0.676, 0.68, 0.685):
    db.log_outcome(f"egg timer {s}", "set_timer", s, "", "ask_yes", "asked")
r._recalibrate("set_timer")
r._reload_if_changed()
check("yes answers lower set_timer (gated)", r.threshold_for("set_timer", 0.70) < 0.70, True)
check("lowering logged", any(e["kind"] in ("threshold", "kept") and e["intent"] == "set_timer" for e in L.read()["events"]), True)

# ── ask band ──
with L.edit() as st:
    st["offsets"].pop("set_timer", None)
r._reload_if_changed()
d = r.decide("set an egg timer for six minutes", 0.70)
check("near miss → ask", (d.path, d.intent), ("ask", "set_timer"))
check("ask wording", d.ask, "Did you mean set a 6 minute timer, sir?")
check("ask carries the steps", d.steps[0]["tool"], "set_timer")
Cfg.over["jarvisRouterAsk"] = False
check("ask off → Claude", r.decide("set an egg timer for six minutes", 0.70).path, "claude:below-threshold")
Cfg.over["jarvisRouterAsk"] = True
check("never ask on a destructive verb", r.decide("delete my last screenshot", 0.70).path != "ask", True)
check("never ask when two intents tie", r.decide("set the volume", 0.70).path != "ask", True)
check("blocked intent is never asked", r._may_ask("power", "put it to sleep"), False)
ev = R._eval_module().run(r, 0.70)
check("eval: 0 wrong actions with the learned store", ev["wrong"], 0)
check("eval: every question is about the right intent", ev["asks"], ev["asks_right"])

# ── tidy: cap, decay ──
with L.edit() as st:
    for i in range(L.LEARN_CAP + 4):
        x = L.add_record(st, "switch_workspace", f"workspace hop {i}", "claude", confirms=1)
        x.update(state="active", promoted=time.time(), pos=i)
    old = L.add_record(st, "open_app", "spin up spotify", "claude", confirms=1)
    old.update(state="active", promoted=time.time() - 90 * 86400, updated=time.time() - 90 * 86400)
    stale = L.add_record(st, "open_app", "spin up steam", "claude")
    stale["updated"] = time.time() - 60 * 86400
    L.tidy(st)
    act = L.active(st)
check("cap per intent", len(act["switch_workspace"]), L.LEARN_CAP)
check("cap keeps the most useful", "workspace hop 0" not in [t for _, t in act["switch_workspace"]], True)
check("unused learned example decays", state("spin up spotify"), None)
check("stale candidate dropped", state("spin up steam"), None)

# ── CLI ──
rid = next(x["id"] for x in L.read()["examples"].values() if x["text"] == "mark iii")
check("forget", L.cli(["forget", rid]), 0)
r._reload_if_changed()
check("forgotten is gone", "mark iii" in r.texts, False)
check("forgotten isn't relearned", r.learn("mark iii", "set_theme", {"preset": "MARK III"}), None)
check("stats json", set(L.stats()) >= {"local_pct", "claude_pct", "events", "review", "router_hit_pct"}, True)
check("intents alias", R.cli(["review"]), 0)
check("reset-learned", (L.reset_learned() > 0, L.read()["examples"], L.read()["offsets"]), (True, {}, {}))
check("reset keeps a backup", L.path().with_suffix(".json.bak").exists(), True)
r._reload_if_changed()

# ── persona independent: one store, the same words with either name ──
check("friday lead-in stripped", R.clean("Friday, pause the music"), R.clean("Jarvis, pause the music"))
check("friday as a weekday kept", R.clean("what's the weather on friday"), "what's the weather on friday")
from core import persona as P  # noqa: E402
_active = P.active
P.active = lambda cfg=None: "friday"
check("same decision as FRIDAY", r.decide("make it louder", 0.70).intent, "media.volume_up")
P.active = _active
check("store path has no persona", "friday" not in str(L.path()).lower(), True)

# ── live signals through Jarvis.handle (fake Claude, fake tools) ──
import jarvis as JV  # noqa: E402
import stark_actions as A  # noqa: E402
from core import control as K  # noqa: E402
from core.brain import Reply  # noqa: E402

JV.hud.ENABLED = False
K.STOP_FLAG = TMP / "control-stop"
ran = []
A.TOOLS = {k: (lambda k=k: (lambda **a: ran.append((k, a)) or {"ok": True, "say": "ok", "percent": 50, "was": 40}))() for k in A.TOOLS}


class FakeBrain:
    """Claude: maps a request to at most one stark call (what the real one would have done)."""
    calls = {}
    history = ""

    async def ask(self, text, on_sentence=None, source="voice"):
        c = self.calls.get(text)
        return Reply(text="Done, sir.", tools=[A.tool_label(c[0], c[1])] if c else [], tier="claude:haiku",
                     calls=[("stark", c[0], c[1])] if c else [])

    async def reset(self):
        pass

    async def disconnect(self):
        pass


answers = []
j = JV.Jarvis(cfg, dry_run=False, confirm_sync=lambda p: answers.pop(0) if answers else False)
j.router = r
j.brain = FakeBrain()
JV.L_OUTCOME_S = 30


def say(text, ans=None):
    if ans is not None:
        answers.append(ans)
    out = j.handle(text, source="cli", confirm=lambda p: answers.pop(0) if answers else False)
    for th in list(j.learning):
        th.join(15)
    return out


def outcomes(intent=None):
    return [(o["intent"], o["outcome"], o["why"]) for o in db.router_outcomes(1, intent)]


# a bad learned example ("chill the tunes out" → play) makes a wrong local action; "no, I meant pause it"
# → negative (the learned example is demoted), does the pause, and teaches the words as pause
with L.edit() as st:
    bad_ex = L.add_record(st, "media.play", "chill the tunes out", "claude", confirms=1)
    bad_ex.update(state="active", promoted=time.time())
r._reload_if_changed()
check("setup: a wrong local action", (r.decide("chill the tunes out", 0.70).intent, r.decide("chill the tunes out", 0.70).example),
      ("media.play", bad_ex["id"]))
say("chill the tunes out")
check("it acted locally", j._last_tier, "local:media.play")
say("no, I meant pause the music")
check("'no, I meant' = negative", outcomes("media.play")[-1][1:], ("neg", "correction"))
check("… the bad learned example is demoted", state("chill the tunes out", "media.play"), "candidate")
check("… and did what he meant", ran[-1], ("media", {"action": "pause"}))
check("… and taught the right intent", state("chill the tunes out", "media.pause") in ("active", "rejected"), True)
d = r.decide("chill the tunes out", 0.70)
check("the wrong reading never acts again", d.path == "local" and d.intent == "media.play", False)

# undo / that's wrong
say("bit louder")
check("undo: acted", j._last_tier, "local:media.volume_up")
check("undo reply", say("undo that"), "My mistake, sir. I won't take those words that way again.")
check("undo = negative", outcomes("media.volume_up")[-1][1:], ("neg", "undo"))
say("turn it down a little")
say("that's wrong")
check("that's wrong = negative", outcomes("media.volume_down")[-1][1:], ("neg", "correction"))

# inverse within 10 s
say("go back one song")
say("go to the next one")
check("inverse = negative", outcomes("media.previous")[-1][1:], ("neg", "inverse"))

# reworded repeat that came to another intent (via Claude) → negative + taught
with L.edit() as st:                            # a bad learned example: these words meant his voice
    bad_ex = L.add_record(st, "media.volume_up", "boost the sound for me", "claude", confirms=1)
    bad_ex.update(state="active", promoted=time.time())
r._reload_if_changed()
FakeBrain.calls["boost the sound of your voice for me"] = ("jarvis_volume", {"action": "up"})
say("boost the sound for me")
check("reworded: acted", j._last_tier, "local:media.volume_up")
say("boost the sound of your voice for me")
check("reworded (different intent, similar words) = negative", outcomes("media.volume_up")[-1][1:], ("neg", "reworded"))

# unrelated next request → the action stood (weak positive)
say("who's this by")
say("arctic theme please")
check("unrelated next request = weak positive", outcomes("what_is_playing")[-1][1:], ("pos", "weak-positive"))

# no next request: weak positive after the window
JV.L_OUTCOME_S = 0.3
say("make it louder")
time.sleep(0.6)
for th in list(j.learning):
    th.join(15)
check("silence for the window = weak positive", outcomes("media.volume_up")[-1][1:], ("pos", "weak-positive"))

# kill switch after a local action
say("make it louder")
K.STOP_FLAG.write_text("x")
time.sleep(0.6)
for th in list(j.learning):
    th.join(15)
check("kill switch = negative", outcomes("media.volume_up")[-1][1:], ("neg", "kill-switch"))
JV.L_OUTCOME_S = 30

# declined confirmation on a local action
d = R.Decision("local", intent="close_window", score=0.9, text="shut this thing", steps=[])
j._after_local("shut this thing", d, ["close_focused_window() [declined]"])
for th in list(j.learning):
    th.join(15)
check("declined = negative", outcomes("close_window")[-1][1:], ("neg", "declined"))

# ask band: yes runs it and teaches; no goes to Claude and teaches nothing
FakeBrain.calls["start a quick egg timer for 7 minutes"] = None
d = r.decide("set an egg timer for six minutes", 0.70)
check("ask setup", d.path, "ask")
ran.clear()
say("set an egg timer for six minutes", ans=True)
check("ask yes: ran", ran[-1][0], "set_timer")
check("ask yes: tier", j._last_tier, "ask:set_timer")
check("ask yes: logged", outcomes("set_timer")[-1][1:], ("ask_yes", "asked"))
check("ask yes: taught", state("set an egg timer for six minutes", "set_timer") in ("active", "rejected"), True)
r._reload_if_changed()
ran.clear()
q = "start a timer for the eggs, six minutes"
dq = r.decide(q, 0.70)
if dq.path == "ask":
    say(q, ans=False)
    check("ask no: nothing ran locally", ran, [])
    check("ask no: went to Claude", j._last_tier, "claude:haiku")
    check("ask no: logged, not taught", (outcomes("set_timer")[-1][1], state(R.clean(q))), ("ask_no", None))

# Claude single call → candidate → promoted; a declined / two-call answer teaches nothing
FakeBrain.calls["have the strip glow at 35 percent"] = ("lights", {"action": "brightness", "value": 35})
check("setup: goes to Claude", r.decide("have the strip glow at 35 percent", 0.70).path, "claude:below-threshold")
say("have the strip glow at 35 percent")
check("claude single call learned", state("have the strip glow at 35 percent", "lights.brightness"), "active")
check("… and acts locally next time", r.decide("have the strip glow at 35 percent", 0.70).path, "local")


class TwoCalls(FakeBrain):
    async def ask(self, text, on_sentence=None, source="voice"):
        return Reply(text="ok", tools=["A", "B"], tier="claude:haiku",
                     calls=[("stark", "lights", {"action": "brightness", "value": 20})])


j.brain = TwoCalls()
say("lights at twenty and tell me a joke")
check("multi-tool answer not learned", state("lights at twenty and tell me a joke"), None)

check("intents.json untouched at the end", R.INTENTS_FILE.read_text(), pristine)
asyncio.run_coroutine_threadsafe(asyncio.sleep(0), j.loop).result(5)
shutil.rmtree(TMP, ignore_errors=True)
print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
