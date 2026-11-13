#!/usr/bin/env python3
"""Personas (core/persona.py): JARVIS text untouched, FRIDAY's lines and "boss", switching through
settings.json (temp copy), outside-change detection, voice params, the fast-path switch, "hey Friday"
stripped without eating Friday the weekday, the [FRIDAY] tag, HUD text styling, DJ templates, chimes,
and the per-message persona in the conversation DB (temp DB). No audio, no Claude.
Run: python tests/test_persona.py"""
import json
import os
import re
import sys
import tempfile
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import config as C  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


tmp = Path(tempfile.mkdtemp())
settings = tmp / "settings.json"
# The checks below are the legacy skin's (JARVIS / FRIDAY, its skin.json keyed jarvis / friday); ALCHEMOS's names are at the end
settings.write_text(json.dumps({"orrinVoice": "bm_lewis", "orrinSpeed": 1.4, "orrinPitch": 0.5, "other": 1,
                                "skin": "legacy"}, indent=4))
# skins, as the HUD has them: alchemos (the real skin.json) and a stand-in for the private legacy overlay
import shutil  # noqa: E402
(tmp / "skins/alchemos").mkdir(parents=True)
shutil.copy(Path(ROOT).resolve().parent / "quickshell/skins/alchemos/skin.json", tmp / "skins/alchemos/skin.json")
(tmp / "skins/legacy").mkdir()
(tmp / "skins/legacy/skin.json").write_text(json.dumps({"osName": "STARK OS", "personas": {
    "jarvis": {"name": "JARVIS", "call": "Jarvis"}, "friday": {"name": "FRIDAY", "call": "FRIDAY"}}}))   # keyed as the real one is
C.HUD_SETTINGS = settings

from core import persona as P  # noqa: E402
P.SKINS_DIR = tmp / "skins"      # the real skins folder is never read

cfg = C.Config()

# ── defaults ──
check("default active", P.active(cfg), "orrin")
check("default current", P.current(cfg), "orrin")
check("jarvis voice", P.voice_params(cfg), ("bm_lewis", 1.4, 0.5))
check("friday voice", P.voice_params(cfg, "selene"), ("bf_emma", 1.15, 0.0))

# ── JARVIS is untouched ──
for line in ["Very well, sir.", "Shall I lock the screen, sir?", "Sorry sir, I didn't catch that.", ""]:
    check(f"jarvis style {line!r}", P.style(line, "orrin"), line)

# ── FRIDAY's manner ──
check("friday stock", P.style("Very well, sir.", "selene"), "Very well.")
check("friday error", P.style("Something went wrong on my end, sir.", "selene"), "Something went wrong on my side.")
check("friday shall", P.style("Shall I lock the screen, sir?", "selene"), "Shall I lock the screen?")
check("friday sir anywhere", P.style("Done. Your CPU is at sixty degrees, sir.", "selene"), "Done. Your CPU is at sixty degrees.")
check("friday sorry", P.style("Sorry sir, Spotify isn't open.", "selene"), "Sorry, Spotify isn't open.")
check("friday greeting", P.style("Good evening, sir. Systems online.", "selene"), "Good evening. Systems online.")
check("friday no sir left", "sir" in P.style("Close Firefox, sir?", "selene").lower(), False)
check("friday keeps 'desire'", P.style("As you desire.", "selene"), "As you desire.")
# every stock line has a version without "sir"
check("friday table sir-free", [k for k, v in P.SELENE_LINES.items() if "sir" in v.lower()], [])
check("friday table title-free", [v for v in P.SELENE_LINES.values() if re.search(r"\b(sir|boss)\b", v, re.I)], [])
check("friday no boss from rules", P.style("Very good, sir. Shall I, sir?", "selene"), "Very good. Shall I?")
check("friday keeps 'Sirius'", P.style("Sirius is bright tonight, sir.", "selene"), "Sirius is bright tonight.")

# ── exchange override ──
P.begin("selene")
check("override current", P.current(cfg), "selene")
check("override active unchanged", P.active(cfg), "orrin")
check("style uses current", P.style("Done, sir."), "Done.")
P.end()
check("after end", P.current(cfg), "orrin")
P.begin(None)
check("begin None = active", P.current(cfg), "orrin")
P.end()

# ── switching: settings.json, other keys kept, outside change detected once ──
check("switched first call records", P.switched(cfg), None)
check("set friday changed", P.set_active("selene"), True)
check("settings persona", json.loads(settings.read_text())["orrinPersona"], "selene")
check("settings other kept", json.loads(settings.read_text())["other"], 1)
cfg = C.Config()
check("active friday", P.active(cfg), "selene")
check("own switch not re-announced", P.switched(cfg), None)
check("set friday again unchanged", P.set_active("selene"), False)
check("switch reply unchanged", P.switch_reply("selene", False), "I'm already here.")
# an outside change (Settings / IPC writes the file)
d = json.loads(settings.read_text()); d["orrinPersona"] = "orrin"; settings.write_text(json.dumps(d))
os.utime(settings, (os.path.getmtime(settings) + 2,) * 2)
cfg = C.Config()
check("outside change announced", P.switched(cfg), "orrin")
check("announced once", P.switched(cfg), None)
try:
    P.set_active("ultron")
    check("bad persona raises", False, True)
except ValueError:
    pass
# mid-exchange switch: the rest of the exchange is the new persona
P.begin("orrin")
P.set_active("selene")
check("exchange follows switch", P.current(), "selene")
P.end()
P.set_active("orrin")

# ── brain tag + prompt ──
check("legacy keys read as orrin / selene", (P.label("orrin"), P.label("selene")), ("JARVIS", "FRIDAY"))
check("tag selene (legacy)", P.tag("hi", "selene"), "[STARK OS · JARVIS · FRIDAY] [SELENE] hi")
check("tag orrin (legacy)", P.tag("hi", "orrin"), "[STARK OS · JARVIS · FRIDAY] hi")
from core import brain  # noqa: E402
sp = brain.system_prompt()
check("prompt keeps ORRIN text", sp.startswith(brain.SYSTEM_PROMPT), True)
check("prompt has SELENE", "[SELENE]" in sp and "moon goddess" in sp, True)

# ── fast path ──
from core import fastpath as F  # noqa: E402
for text, who in [("switch to Friday.", "selene"), ("switch to jarvis", "orrin"), ("let me talk to Friday please", "selene"),
                  ("put Jarvis back on", "orrin"), ("switch back to Jarvis", "orrin"), ("give me friday", "selene")]:
    r = F.match(text)
    check(f"fastpath {text!r}", [(s["tool"], s["args"]) for s in r] if r else None, [("orrin_persona", {"name": who})])
for text in ["set a reminder for friday", "what's due friday", "switch to workspace 2"]:
    r = F.match(text)
    check(f"fastpath not persona {text!r}", any(s["tool"] == "orrin_persona" for s in (r or [])), False)

# ── orrin_persona action (against the temp settings) ──
import alchemos_actions as A  # noqa: E402
r = A.TOOLS["orrin_persona"](name="selene")
check("action ok", (r["ok"], r["persona"], r["changed"]), (True, "selene", True))
check("action say", r["say"], P.announce_line("selene"))
check("action label", A.tool_label("orrin_persona", {"name": "selene"}), "PERSONA → FRIDAY")
A.TOOLS["orrin_persona"](name="orrin")

# ── hearing: "hey Friday" stripped, Friday the day kept ──
from core.hearing import strip_wake  # noqa: E402
for raw, want in [("Hey Friday, dim the lights.", "dim the lights."), ("Friday, switch to Jarvis.", "switch to Jarvis."),
                  ("Hey Friday.", ""), ("Hey Jarvis, switch to Friday.", "switch to Friday."),
                  ("What is due on a Friday?", "What is due on a Friday?"), ("Oh Friday is busy.", "Oh Friday is busy."),
                  ("Friday night plans?", "Friday night plans?"), ("Hey Joe, visit volume up.", "volume up."),
                  ("Hey Orrin, dim the lights.", "dim the lights."), ("Hey Oren. What time is it?", "What time is it?"),
                  ("Hey Selene, play music.", "play music."), ("Hey Celine, pause.", "pause."), ("Selene, stop.", "stop."),
                  ("Erin said hi.", "Erin said hi."), ("Orange juice on the list.", "Orange juice on the list.")]:
    check(f"strip {raw!r}", strip_wake(raw), want)

# ── HUD text is styled, the IPC function names aren't ──
from core import hud  # noqa: E402
sent = []
hud.ENABLED = True
hud._q.put = lambda item: sent.append(item)
P.begin("selene")
hud.reply("Very well, sir.")
hud.error("NO NETWORK", "I'm having trouble reaching the network, sir.")
hud.toast("TIMER", "Your timer is done, sir.")
hud.tool("THEME → MARK III")
P.end()
hud.reply("Very well, sir.")
check("hud friday reply", sent[0], ("reply", ("Very well.",)))
check("hud friday error", sent[1], ("error", ("NO NETWORK", "I can't reach the network.")))
check("hud friday toast", sent[2], ("toast", ("TIMER", "Your timer is done.")))
check("hud tool untouched", sent[3], ("tool", ("THEME → MARK III",)))
check("hud jarvis reply", sent[4], ("reply", ("Very well, sir.",)))
hud.answering("selene")
check("hud answering snapshot", hud.snapshot()["answering"], "selene")

# ── voice: params per persona, chime notes differ ──
from core import voice as V  # noqa: E402
v = V.Voice(C.Config())
check("voice params jarvis", v.params("orrin")[0], "bm_lewis")
check("voice params friday", v.params("selene")[0], "bf_emma")
v.overrides = {"voice": "af_heart"}
check("voice override wins", v.params("selene")[0], "af_heart")
cj, cf = V.chime_audio("listen", "orrin"), V.chime_audio("listen", "selene")
check("chimes differ", bool(len(cj) == len(cf) and abs(cj - cf).max() < 1e-6), False)
check("error chime shared", bool(abs(V.chime_audio("error", "orrin") - V.chime_audio("error", "selene")).max() < 1e-6), True)

# ── DJ: templates + set prompt per persona ──
from core import dj  # noqa: E402
check("dj friday templates sir-free", [t for t in P.DJ_TEMPLATES["selene"] if "sir" in t], [])
p = dj.PROMPT.format(name=P.call("selene"), voice=P.dj_voice("selene"), vibe="v", adjust="", carry="", lo=1, hi=2, library="")
check("dj prompt friday", ("You are FRIDAY" in p, 'never "sir" or "boss"' in p, "Jarvis's voice" in p), (True, True, False))
p = dj.PROMPT.format(name=P.call("orrin"), voice=P.dj_voice("orrin"), vibe="v", adjust="", carry="", lo=1, hi=2, library="")
check("dj prompt jarvis unchanged", 'Write DJ lines in Jarvis\'s voice (dry, British, calls him "sir", at most 18 words, no emojis, no hype clichés)' in p, True)

# ── conversation DB: who answered is stored (temp DB) ──
import orrin_db as db  # noqa: E402
db.DB_PATH = tmp / "orrin.db"
db._MIGRATED = False
tid = db.new_thread("t", "thread")
db.add_message(tid, "orrin", "voice", "hi", persona="selene")
check("db persona stored", db.thread_messages(tid)[-1]["persona"], "selene")
db.add_message(tid, "orrin", "voice", "hi", persona="orrin")
check("db jarvis = ''", db.thread_messages(tid)[-1]["persona"], "")
check("db temp only", str(db.DB_PATH).startswith(str(tmp)), True)

# ── ALCHEMOS skin: ORRIN / SELENE (same ids, voices, manner) ──
def set_skin(name):
    data = json.loads(settings.read_text())
    data["skin"] = name
    settings.write_text(json.dumps(data, indent=4))
    os.utime(settings, (os.path.getmtime(settings) + 5,) * 2)


set_skin("alchemos")
check("alchemos skin", P.skin(), "alchemos")
check("alchemos labels", (P.label("orrin"), P.label("selene"), P.call("orrin"), P.call("selene")), ("ORRIN", "SELENE", "Orrin", "Selene"))
check("alchemos announce", P.announce_line("selene"), "SELENE here. ORRIN is resting.")
check("alchemos announce jarvis", P.announce_line("orrin"), "ORRIN here, sir. SELENE's on standby.")
check("alchemos: no names tag", P.tag("hi", "orrin"), "hi")
check("alchemos tag selene", P.tag("hi", "selene"), "[SELENE] hi")
check("prompt explains the tag", "[STARK OS · JARVIS · FRIDAY]" in brain.system_prompt(), True)
check("os name alchemos", P.os_name(), "AlchemOS")
check("prompt: ORRIN on AlchemOS by default", brain.system_prompt().startswith("You are ORRIN") and "desktop, AlchemOS" in brain.system_prompt(), True)
check("prompt: a tagged desktop name wins", "the first name is what the desktop is called (say that, never alchemos)" in brain.system_prompt().lower(), True)
check("alchemos label tool", A.tool_label("orrin_persona", {"name": "selene"}), "PERSONA → SELENE")
check("dj voice orrin", P.dj_voice("orrin").startswith("in Orrin's voice"), True)
check("aliases", (P.norm("Orrin"), P.norm("SELENE"), P.norm("orrin"), P.norm("ultron")), ("orrin", "selene", "orrin", None))
for text, who in [("switch to Selene", "selene"), ("let me talk to Orrin", "orrin"), ("switch to selena", "selene"),
                  ("switch to friday", "selene")]:
    r = F.match(text)
    check(f"alchemos fastpath {text!r}", [(s["tool"], s["args"]) for s in r] if r else None, [("orrin_persona", {"name": who})])
r = A.TOOLS["orrin_persona"](name="selene")
check("action takes selene", (r["ok"], r["persona"]), (True, "selene"))
A.TOOLS["orrin_persona"](name="orrin")
# the legacy skin asked for but its overlay missing: ALCHEMOS names (the HUD shows ALCHEMOS too)
set_skin("legacy")
(tmp / "skins/legacy").rename(tmp / "skins/legacy-away")
check("legacy without overlay", (P.skin(), P.label("orrin")), ("alchemos", "ORRIN"))
(tmp / "skins/legacy-away").rename(tmp / "skins/legacy")
check("os name legacy", P.os_name(), "STARK OS")
check("legacy: names tag", P.tag("hi", "orrin"), "[STARK OS · JARVIS · FRIDAY] hi")
# any skin folder names them: a made-up one, and the template-like fallback for missing keys
(tmp / "skins/nebula").mkdir()
(tmp / "skins/nebula/skin.json").write_text(json.dumps({"osName": "NebulaOS", "personas": {"orrin": {"name": "VEGA", "call": "Vega"}}}))
set_skin("nebula")
check("new skin names", (P.os_name(), P.label("orrin"), P.call("orrin"), P.label("selene")), ("NebulaOS", "VEGA", "Vega", "FRIDAY"))
check("new skin tag", P.tag("hi", "orrin"), "[NebulaOS · VEGA · FRIDAY] hi")
set_skin("_template")
check("templates are never a skin", P.skin(), "alchemos")
set_skin("legacy")

print("FAILS:", len(FAILS)) if FAILS else print("ok: personas")
sys.exit(1 if FAILS else 0)
