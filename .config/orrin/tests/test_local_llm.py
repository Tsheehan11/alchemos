#!/usr/bin/env python3
"""The local model tier (core/local_llm.py) and open_app's workspace argument.

Unit checks: eligibility (account / sending, two-part, "check …", the router's paths), places, argument checks,
numbers that must come from his words, call → intent mapping, the fixed spoken lines, what Claude did, argument
comparison, trust bookkeeping (promotion / demotion), the power rules, the settings writer, the CLI.
End to end through Orrin.handle with a fake llama-server (HTTP, on a free port), a fake Claude and fake tools:
shadow agreement → earned → shadow off runs it locally → "undo" sends it back; a disagreement resets the streak;
a wrong number escalates; a failed live call demotes; ineligible requests never reach the model; dry runs record
nothing; a dead server means Claude only. Temp intents.json, data dir, settings and DB; nothing real runs and no
real model or Claude is used. Run: python tests/test_local_llm.py"""
import asyncio
import json
import os
import shutil
import socket
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp())
os.environ["ORRIN_DB"] = str(TMP / "orrin.db")
import orrin_db as db  # noqa: E402
from core import config as C  # noqa: E402
from core import router_learn as L  # noqa: E402
from core import router_local as R  # noqa: E402
from core import local_llm as LL  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


shutil.copy(R.INTENTS_FILE, TMP / "intents.json")
R.INTENTS_FILE = TMP / "intents.json"
C.DATA_DIR = TMP / "data"
C.DATA_DIR.mkdir()
C.HUD_SETTINGS = TMP / "settings.json"
C.HUD_SETTINGS.write_text(json.dumps({"skin": "alchemos", "orrinVoice": "bm_george"}))
LL.KEY_FILE = TMP / "api-key"
LL.KEY_FILE.write_text("test-key\n")
quiet = lambda *a: None   # noqa: E731


class Cfg(C.Config):
    over = {}

    def __getitem__(self, k):
        return self.over.get(k, C.Config.__getitem__(self, k))


cfg = Cfg()
Cfg.over = {"orrinRouterThreshold": 0.70, "orrinRouterAsk": False, "orrinDecisions": "local", "orrinBrain": "auto",
            "orrinBrainShadow": True, "orrinLocalPromote": 2}

# ── open_app's workspace argument (dry run: nothing starts) ──
import alchemos_actions as A  # noqa: E402
app = next(iter(A.ALIASES))
A.set_dry_run(True)
r = A.open_app(app, 3)
check("open_app on a workspace (dry run)", (r["ok"], "workspace 3" in r.get("would", "") or "is up" in str(r)), (True, True))
check("open_app workspace out of range", A.open_app(app, 11)["ok"], False)
check("open_app workspace 0 = current", "workspace" in A.open_app(app, 0).get("would", ""), False)
A.set_dry_run(False)
check("exec rule carries the workspace", A._hypr_exec("steam", 2)[-1], 'hl.dsp.exec_cmd("steam", { workspace = "2" })')
check("label shows the workspace", A.tool_label("open_app", {"name": "steam", "workspace": 1}), "OPEN → STEAM · WS 1")

# ── eligibility ──
router = R.LocalRouter(cfg, record=False, log=quiet)
tier = LL.LocalTier(cfg, router=router, log=quiet)
D = R.Decision
check("two-part", LL.two_part("restart the song and raise the volume"), True)
check("app on a workspace is one part", LL.two_part("open steam on workspace one"), False)
check("comma without a second verb", LL.two_part("dj, study house mix"), False)
check("ok, great. play music", LL.two_part("ok, great. play music"), False)
check("then", LL.two_part("pause the music then lock the screen"), True)
for text, want in [("check zen browser in workspace 2", "check"), ("Can you monitor workspace 4", "check"),
                   ("email my prof that I'm late", "account or sending"), ("send Sam a message", "account or sending"),
                   ("add this to my calendar", "account or sending"), ("restart song and raise volume", "two-part"),
                   ("open " + "very " * 20 + "slowly", "long")]:
    check(f"not eligible: {text[:30]}", tier.eligible(text, None), (False, want))
check("eligible: theme", tier.eligible("change theme to silver", None), (True, ""))
check("router path below-threshold", tier.eligible("change theme to silver", D("claude:below-threshold"))[0], True)
check("router path slots", tier.eligible("change theme to silver", D("claude:slots:preset"))[0], True)
check("router path claude-only", tier.eligible("change theme to silver", D("claude:claude-only"))[0], False)
check("router path other (chat)", tier.eligible("change theme to silver", D("claude:other"))[0], False)
check("router path negation", tier.eligible("change theme to silver", D("claude:negation"))[0], False)
Cfg.over["orrinBrain"] = "claude"
check("orrinBrain claude: off", tier.eligible("change theme to silver", None), (False, "off"))
Cfg.over["orrinBrain"] = "auto"

# ── places ──
for p, want in [("", ""), ("campus", ""), ("Waterloo, Ontario", ""), ("Toronto", "Toronto, Ontario"),
                ("in toronto", "Toronto, Ontario"), ("Austin", None), ("London", None), ("Kitchener, Ontario", "Kitchener, Ontario")]:
    check(f"place {p!r}", LL.canon_place(p), want)

# ── argument checks ──
check("theme ARGENT ok", LL.validate("set_theme", {"preset": "argent"})[0], True)
check("a colour isn't a preset (the model maps it)", LL.validate("set_theme", {"preset": "silver"})[0], False)
check("unknown theme", LL.validate("set_theme", {"preset": "jarvis"})[0], False)
check("unknown app", LL.validate("open_app", {"name": "wordpress 4"})[0], False)
check("workspace 0 dropped", LL.validate("open_app", {"name": app, "workspace": 0})[2], {"name": app})
check("timer 0", LL.validate("set_timer", {"minutes": 0})[0], False)
check("weather unknown place", LL.validate("weather", {"place": "Austin"})[0], False)
check("weather campus = home", LL.validate("weather", {"place": "campus"}), (True, "", {}))
check("voice set needs a percent", LL.validate("orrin_volume", {"action": "set"})[0], False)
check("music volume 140", LL.validate("media", {"action": "set_volume", "value": 140})[0], False)
check("empty spotify query", LL.validate("spotify_play", {"query": " "})[0], False)

# ── numbers must come from his words ──
check("timer 69 for 1 h 29", bool(LL.numbers_said("set_timer", {"minutes": 69}, "one hour 29 minute time.")), True)
check("timer 89 for 1 h 29", LL.numbers_said("set_timer", {"minutes": 89}, "one hour 29 minute time."), "")
check("timer without a duration", bool(LL.numbers_said("set_timer", {"minutes": 10}, "set a timer for the pasta")), True)
check("workspace said as a word", LL.numbers_said("open_app", {"name": "steam", "workspace": 1}, "Open STEAM workspace one."), "")
check("workspace not said", bool(LL.numbers_said("switch_workspace", {"n": 4}, "go to workspace two")), True)
check("percent said", LL.numbers_said("orrin_volume", {"action": "set", "percent": 60}, "set your volume to 60 percent"), "")
check("half = 50", LL.numbers_said("media", {"action": "set_volume", "value": 50}, "music at half"), "")
check("brightness never said", bool(LL.numbers_said("lights", {"action": "brightness", "value": 100}, "Bright.")), True)
check("light mode isn't a number", LL.numbers_said("lights", {"action": "mode", "value": "music"}, "lights to music mode"), "")

# ── call → intent, spoken line ──
I = router.data["intents"]
check("media next", LL.intent_of(I, "media", {"action": "next"}), "media.next")
check("media play_pause isn't mute", LL.intent_of(I, "media", {"action": "play_pause"}), "llm.media.play_pause")
check("status default", LL.intent_of(I, "system_status", {}), "status.overview")
check("status: the router's guess wins", LL.intent_of(I, "system_status", {}, D("claude:below-threshold", top3=[["status.temperature", 0.6]])),
      "status.temperature")
check("restart isn't shuffle", LL.intent_of(I, "spotify_player", {"action": "restart"}), "llm.spotify_player.restart")
check("note widget", LL.intent_of(I, "widget_add", {"type": "note", "text": "x"}), "llm.widget_add.note")
check("dj start with a mood", LL.intent_of(I, "dj_start", {"mood": "gym"}), "dj.start")
check("lights brightness", LL.intent_of(I, "lights", {"action": "brightness", "value": 40}), "lights.brightness")
check("lights on", LL.intent_of(I, "lights", {"action": "on"}), "lights.power")
s = LL.steps_for(I, "set_theme", "set_theme", {"preset": "ARGENT"})
check("theme line is the intent's", "ARGENT" in s["say"] and s["tool"] == "set_theme", True)
s = LL.steps_for(I, "llm.spotify_player.restart", "spotify_player", {"action": "restart"})
check("no intent: the result's own line", (s["say"]({"say": "Restarted, sir."}), s["say"]({})), ("Restarted, sir.", "Done, sir."))

# ── what Claude did ──
from core.brain import Reply  # noqa: E402
lk = Reply(calls=[("alchemos", "list_audio_devices", {}), ("alchemos", "set_audio_output", {"device": "WH-1000XM4"})],
           tools=["a", "b"])
check("lookup then action", LL.claude_action(lk), ("set_audio_output", {"device": "WH-1000XM4"}))
check("only talked", LL.claude_action(Reply(text="Which one?")), ("none", {}))
check("declined", LL.claude_action(Reply(calls=[("alchemos", "power", {"action": "suspend"})], tools=["power(action=suspend) [declined]"])), None)
check("two actions", LL.claude_action(Reply(calls=[("alchemos", "switch_workspace", {"n": 1}), ("alchemos", "open_app", {"name": "steam"})],
                                            tools=["a", "b"])), None)
check("an error", LL.claude_action(Reply(error="limit")), None)
check("google tool", LL.claude_action(Reply(calls=[("google", "calendar_today", {})], tools=["x"])), None)
check("only a lookup counts as the answer", LL.claude_action(Reply(calls=[("alchemos", "system_status", {})], tools=["x"])),
      ("system_status", {}))

# ── comparing arguments ──
check("legacy ARCTIC = ARGENT", LL.same_args("set_theme", {"preset": "ARGENT"}, {"preset": "ARCTIC"}), True)
check("silver ≠ IRON", LL.same_args("set_theme", {"preset": "ARGENT"}, {"preset": "IRON"}), False)
check("89 = 89.0", LL.same_args("set_timer", {"minutes": 89}, {"minutes": 89.0}), True)
check("mood loosely", LL.same_args("dj_start", {"mood": "Study House Mix"}, {"mood": "study house mix"}), True)
check("mood differs", LL.same_args("dj_start", {"mood": "Study House Mix"}, {"mood": "gym"}), False)
check("weather home either way", LL.same_args("weather", {}, {"place": "Waterloo"}), True)
check("a note is extra", LL.same_args("dj_adjust", {"direction": "more", "note": "house"}, {"direction": "more"}), True)
check("missing workspace", LL.same_args("open_app", {"name": app, "workspace": 1}, {"name": app}), False)

# ── trust ──
check("first agree", LL._bump("media.next", "agree", 2), "shadow")
check("second agree → live", LL._bump("media.next", "agree", 2), "live")
check("event", L.read()["events"][-1]["kind"], "llm-live")
check("disagree → shadow, streak 0", (LL._bump("media.next", "disagree", 2, "x"), LL.trust()["media.next"]["streak"]), ("shadow", 0))
check("demotion event", L.read()["events"][-1]["kind"], "llm-demoted")
LL._bump("media.next", "agree", 2)
LL._bump("media.next", "agree", 2)
LL._live_outcome("media.next", False, "undo")
check("live negative → shadow", (LL.trust()["media.next"]["state"], LL.trust()["media.next"]["live_neg"]), ("shadow", 1))
check("router examples untouched by llm trust", L.read()["examples"], {})
with L.edit() as st:
    st["llm"] = {}

# ── power rules ──
pw = LL.Power(tier, laptop=False, log=quiet)
check("docked: wanted", pw.wanted(False)[0], True)
check("combat: not", pw.wanted(True), (False, "combat mode"))
Cfg.over["orrinBrain"] = "claude"
check("off in Settings: not", pw.wanted(False)[0], False)
Cfg.over["orrinBrain"] = "auto"
lp = LL.Power(LL.LocalTier(cfg, router=router, log=quiet), laptop=True, log=quiet)
check("laptop idle: not", lp.wanted(False), (False, "idle (laptop mode)"))
lp.demand()
check("laptop asked for: wanted", lp.wanted(False)[0], True)
lp.last_use = time.monotonic() - LL.LAPTOP_IDLE_S - 1
check("laptop idle again: not", lp.wanted(False)[0], False)
lp.demand()
check("laptop in combat: not", lp.wanted(True)[0], False)

# ── settings ──
check("shadow off written", LL.write_setting("orrinBrainShadow", False), True)
data = json.loads(C.HUD_SETTINGS.read_text())
check("other settings kept", (data["orrinBrainShadow"], data["skin"], data["orrinVoice"]), (False, "alchemos", "bm_george"))
check("same value: no write", LL.write_setting("orrinBrainShadow", False), False)


# ── end to end: a fake llama-server ──
ANSWERS = {}            # user text (lower) → (tool, args) | None (talks) ; "warm up" → talks
SEEN = []
SLOW = {}               # user text (lower) → seconds the fake model takes
SLOTS = {"restored": False}
LL.SLOT_DIR = TMP / "slots"
LL.SLOT_DIR.mkdir()


class Fake(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body):
        b = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._send(401, {"error": "key"})
        self._send(200, {"status": "ok"} if self.path == "/health" else {"data": [{"id": "fake.gguf"}]})

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if self.headers.get("Authorization") != "Bearer test-key":
            return self._send(401, {"error": "key"})
        if self.path.startswith("/slots/0?action=save"):
            (LL.SLOT_DIR / body["filename"]).write_text("kv")
            return self._send(200, {"n_saved": 4200})
        if self.path.startswith("/slots/0?action=restore"):
            if not (LL.SLOT_DIR / body["filename"]).exists():
                return self._send(404, {"error": "no file"})
            SLOTS["restored"] = True
            return self._send(200, {"n_restored": 4200})
        text = body["messages"][-1]["content"]
        time.sleep(SLOW.get(text.lower(), 0))
        SEEN.append((text, body["chat_template_kwargs"]["enable_thinking"], len(body["tools"])))
        a = ANSWERS.get(text.lower())
        msg = {"role": "assistant", "content": "Could you say that again?"}
        if a:
            msg = {"role": "assistant", "content": None,
                   "tool_calls": [{"id": "c0", "type": "function", "function": {"name": a[0], "arguments": json.dumps(a[1])}}]}
        computed = 5 if SLOTS["restored"] else 4200
        SLOTS["restored"] = False
        self._send(200, {"choices": [{"message": msg}], "timings": {"prompt_n": computed if text == "warm up" else 20}})


srv = ThreadingHTTPServer(("127.0.0.1", 0), Fake)
threading.Thread(target=srv.serve_forever, daemon=True).start()
LL.URL = f"http://127.0.0.1:{srv.server_address[1]}"

import orrin as JV  # noqa: E402
from core import control as K  # noqa: E402
JV.hud.ENABLED = False
K.STOP_FLAG = TMP / "control-stop"
ran = []
results = {}
A.TOOLS = {k: (lambda k=k: (lambda **a: ran.append((k, a)) or results.get(k, {"ok": True, "say": "ok"})))() for k in A.TOOLS}


class FakeBrain:
    calls = {}
    history = ""
    asked = []

    async def ask(self, text, on_sentence=None, source="voice"):
        self.asked.append(text)
        c = self.calls.get(text)
        return Reply(text="Done, sir." if c else "Pardon?", tools=[A.tool_label(c[0], c[1])] if c else [],
                     tier="claude:haiku", calls=[("alchemos", c[0], c[1])] if c else [])

    async def reset(self):
        pass

    async def disconnect(self):
        pass


j = JV.Orrin(cfg, dry_run=False, confirm_sync=lambda p: False)
j.router = router
j.llm.router = router
j.brain = FakeBrain()
j._learn = lambda *a: None             # keep the router from learning these words (so they stay the router's misses)
check("tier constructed", j.llm is not None, True)
check("not warm until asked", j._local_model("change theme to silver", D("claude:slots:preset")), (None, None))
check("warm-up through the fake server", j.llm.warm_up(), True)
check("first start computes and saves the prompt cache", (j.llm.warm_from, [f.name for f in LL.SLOT_DIR.iterdir()]),
      ("computed and saved", [j.llm.prefix_file()]))
(LL.SLOT_DIR / "orrin-prefix-0000000000000000.bin").write_text("old")
t2 = LL.LocalTier(cfg, router=router, log=quiet)
check("next start restores it", (t2.warm_up(), t2.warm_from), (True, "restored from disk"))
check("a restored start saves nothing new", sorted(f.name for f in LL.SLOT_DIR.iterdir()),
      sorted([j.llm.prefix_file(), "orrin-prefix-0000000000000000.bin"]))
(LL.SLOT_DIR / j.llm.prefix_file()).unlink()
t3 = LL.LocalTier(cfg, router=router, log=quiet)
t3.warm_up()
check("a new prompt replaces the old saved one", [f.name for f in LL.SLOT_DIR.iterdir()], [t3.prefix_file()])


def say(text):
    out = j.handle(text, source="cli", confirm=lambda p: False)
    for th in list(j.learning):
        th.join(15)
    j.llm.pool.submit(lambda: None).result(30)     # shadow comparisons (done callbacks) have run
    return out


def last_llm():
    rows = db.llm_log(1)
    return rows[-1] if rows else {}


SILVER = "Change theme to silver."
check("silver goes past the router", router.decide(SILVER).path.startswith(LL.ELIGIBLE), True)
ANSWERS[SILVER.lower()] = ("set_theme", {"preset": "ARGENT"})
FakeBrain.calls[SILVER] = ("set_theme", {"preset": "ARGENT"})

say(SILVER)
check("shadow: Claude acted", (j._last_tier, ran), ("claude:haiku", []))
check("shadow: agree logged", (last_llm().get("verdict"), last_llm().get("intent"), last_llm().get("mode")), ("agree", "set_theme", "shadow"))
check("voice-less cli = no thinking", SEEN[-1][1], False)
check("allowlisted tools + escalate", SEEN[-1][2], len(j.llm.tools()))
say(SILVER)
check("two agreements → earned", LL.trust()["set_theme"]["state"], "live")
say(SILVER)
check("shadow on: still Claude", (j._last_tier, ran), ("claude:haiku", []))

Cfg.over["orrinBrainShadow"] = False
n_claude = len(FakeBrain.asked)
reply = say(SILVER)
check("shadow off: ran locally", (j._last_tier, ran[-1:]), ("llm:set_theme", [("set_theme", {"preset": "ARGENT"})]))
check("… without Claude", len(FakeBrain.asked), n_claude)
check("… with the intent's fixed line", "ARGENT" in reply, True)
check("live logged", last_llm().get("verdict"), "live")
check("action log tier", db.recent_log(1)[0]["tier"], "llm:set_theme")
reply = say("undo")
check("undo after a local-model action", reply.startswith("My mistake"), True)
time.sleep(0.2)
check("undo → back to shadow", (LL.trust()["set_theme"]["state"], LL.trust()["set_theme"]["live_neg"]), ("shadow", 1))
check("demotion event", L.read()["events"][-1]["kind"], "llm-demoted")
say(SILVER)
check("demoted: Claude again", j._last_tier, "claude:haiku")

# shadow mode never makes him wait: a 3 s proposal, Claude answers at once
Cfg.over["orrinBrainShadow"] = True
SLOW[SILVER.lower()] = 3.0
rows = len(db.llm_log(1))
t0 = time.monotonic()
j.handle(SILVER, source="cli", confirm=lambda p: False)
took = time.monotonic() - t0
check("shadow: the reply didn't wait for the slow proposal", took < 1.5, True)
check("… and the comparison wasn't logged yet", len(db.llm_log(1)), rows)
j.llm.pool.submit(lambda: None).result(30)
check("… it was logged once the proposal came in", (len(db.llm_log(1)), last_llm().get("verdict")), (rows + 1, "agree"))
SLOW.clear()

# a wrong number never runs: 69 for "one hour 29"
TIMER = "one hour 29 minute time."
check("timer goes past the router", router.decide(TIMER).path.startswith(LL.ELIGIBLE), True)
ANSWERS[TIMER.lower()] = ("set_timer", {"minutes": 69})
FakeBrain.calls[TIMER] = ("set_timer", {"minutes": 89})
say(TIMER)
check("wrong number → escalated", (last_llm().get("verdict"), last_llm().get("why", "").startswith("numbers")), ("escalated", True))
check("Claude's intent counted as escalated", LL.trust().get("set_timer", {}).get("escalated"), 1)

# a disagreement resets the streak
DJ = "DJ, Study House Mix."
check("dj goes past the router", router.decide(DJ).path.startswith(LL.ELIGIBLE), True)
ANSWERS[DJ.lower()] = ("dj_start", {"mood": "Study House Mix"})
FakeBrain.calls[DJ] = ("dj_start", {"mood": "study house mix"})
Cfg.over["orrinBrainShadow"] = True
say(DJ)
check("dj agree", (last_llm().get("verdict"), LL.trust()["dj.start"]["streak"]), ("agree", 1))
FakeBrain.calls[DJ] = ("dj_start", {"mood": "gym"})
say(DJ)
check("dj disagree → streak 0", (last_llm().get("verdict"), LL.trust()["dj.start"]["streak"]), ("disagree", 0))

# the model talks instead of calling a tool → escalated, Claude answers
HOLD = "Hold on, I can't."
if router.decide(HOLD).path.startswith(LL.ELIGIBLE):
    say(HOLD)
    check("talking = escalated", (last_llm().get("verdict"), last_llm().get("why")), ("escalated", "no call"))

# ineligible never reaches the model
n = len(SEEN)
say("restart the song and raise the volume")
say("check zen browser in workspace 2")
check("two-part / check: model not asked", len(SEEN), n)

# a failed live call demotes
FakeBrain.calls[SILVER] = ("set_theme", {"preset": "ARGENT"})
say(SILVER)
say(SILVER)
check("earned again", LL.trust()["set_theme"]["state"], "live")
Cfg.over["orrinBrainShadow"] = False
results["set_theme"] = {"ok": False, "error": "theme engine down"}
say(SILVER)
check("failed live call", (j._last_tier, last_llm().get("verdict")), ("llm:set_theme", "live-failed"))
check("failed → shadow", LL.trust()["set_theme"]["state"], "shadow")
results.clear()

# typed requests think
j.surface = "typed"
f = j.llm.submit(SILVER, None, "typed")
f.result(10)
check("typed = thinking", SEEN[-1][1], True)
j.surface = "voice"

# dry run records nothing
rows = len(db.llm_log(1))
jd = JV.Orrin(cfg, dry_run=True, confirm_sync=lambda p: False)
jd.router, jd.llm.router, jd.brain, jd._learn = router, router, FakeBrain(), (lambda *a: None)
jd.llm.warm_up()
Cfg.over["orrinBrainShadow"] = True
jd.handle(SILVER, source="cli", confirm=lambda p: False)
jd.llm.pool.submit(lambda: None).result(30)
check("dry run: nothing logged", len(db.llm_log(1)), rows)

# "Did you mean …?" answered no: on to Claude (this crashed in the route trace before 2026-11-15)
real_route = j.route_local
j.route_local = lambda text: R.Decision("ask", intent="weather.tomorrow", ask="Did you mean check tomorrow's weather, sir?",
                                       steps=[{"tool": "weather", "args": {}, "say": "x"}], text=R.clean(text))
n_claude = len(FakeBrain.asked)
check("declined ask → Claude, no crash", (say("do I need an umbrella for my walk"), j._last_tier, len(FakeBrain.asked)),
      ("Pardon?", "claude:haiku", n_claude + 1))
j.route_local = real_route

# a dead server: Claude only, no error
LL.URL = "http://127.0.0.1:9"
check("dead server: not ready", j.llm.ready(), False)
n_claude = len(FakeBrain.asked)
say(SILVER)
check("dead server: Claude answered", (j._last_tier, len(FakeBrain.asked)), ("claude:haiku", n_claude + 1))

# CLI
import contextlib  # noqa: E402
import io  # noqa: E402
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    rc = LL.cli(["shadow", "report"])
check("report runs", (rc, "set_theme" in buf.getvalue(), "agree" in buf.getvalue()), (0, True, True))
with contextlib.redirect_stdout(io.StringIO()):
    check("shadow on", LL.cli(["shadow", "on"]), 0)
check("shadow on written", json.loads(C.HUD_SETTINGS.read_text())["orrinBrainShadow"], True)
with contextlib.redirect_stdout(io.StringIO()):
    check("bad command", LL.cli(["shadow", "maybe"]), 2)

srv.shutdown()
asyncio.run_coroutine_threadsafe(asyncio.sleep(0), j.loop).result(5)
shutil.rmtree(TMP, ignore_errors=True)
print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
