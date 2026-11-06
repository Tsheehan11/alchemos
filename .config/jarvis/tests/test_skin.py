#!/usr/bin/env python3
"""HUD skins (quickshell/Skin.qml): the fast path's skin phrases (and what it must leave alone), "switch
back" only while the legacy skin is on, the set_skin action / tool / HUD label, never learned. No HUD
needed: the qs call is stubbed. Run: python tests/test_skin.py"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
import stark_actions as A  # noqa: E402
from core import fastpath, router_learn  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


SKIN_NOW = {"v": "alchemos"}
A.skin_current = lambda: SKIN_NOW["v"]


def skin_of(text):
    r = fastpath.match(text)
    return [s["args"].get("name") for s in r if s["tool"] == "set_skin"] if r else None


for text, want in [
    ("switch to the legacy skin", "legacy"), ("Switch to legacy skin.", "legacy"),
    ("switch to legacy skin please", "legacy"), ("go back to the alchemos skin", "alchemos"),
    ("switch to the AlchemOS skin", "alchemos"), ("switch to the alchemy OS skin", "alchemos"),
    ("change to the old skin", "legacy"), ("switch skins", "toggle"), ("toggle the skin", "toggle"),
    ("switch skins to legacy", "legacy"), ("hey jarvis switch to the default skin", "alchemos"),
    ("put the stark skin on", "legacy"),
]:
    check(f"skin {text!r}", skin_of(text), [want])

# bare and misheard skin names (Whisper: "AlkeneOS"), no verb or no "skin"
for text, want in [("Legacy skin.", "legacy"), ("the legacy skin", "legacy"), ("alchemos skin please", "alchemos"),
                   ("Hey Jarvis, switch back to AlkeneOS.", "alchemos"), ("switch back to legacy", "legacy"),
                   ("go back to alchemos", "alchemos"), ("switch to alchemy os", "alchemos")]:
    check(f"skin {text!r}", skin_of(text), [want])

# not a skin: the persona and theme switches keep their own tools, and "switch back" needs the legacy skin
for text in ["switch to friday", "switch to the stark theme", "set the theme to iron", "switch back",
             "go back", "switch to workspace 2", "switch back to jarvis", "switch to stark", "switch to the old theme"]:
    check(f"not skin {text!r}", bool(skin_of(text)), False)
SKIN_NOW["v"] = "legacy"
check("switch back while legacy", skin_of("switch back"), ["alchemos"])
check("go back while legacy", skin_of("go back please"), ["alchemos"])
SKIN_NOW["v"] = ""
check("switch back, HUD down", bool(skin_of("switch back")), False)

# action
check("tool registered", "set_skin" in A.TOOLS, True)
check("label", A.tool_label("set_skin", {"name": "legacy"}), "SKIN → LEGACY")
check("never learned", "set_skin" in router_learn.BLOCKED_TOOLS, True)
calls = []
A._run = lambda cmd, timeout=6: (calls.append(cmd) or (0, "skin legacy", ""))
A.DRY_RUN = False
r = A.set_skin("legacy")
check("action ok", (r.get("ok"), r.get("skin")), (True, "legacy"))
check("action call", calls[-1], ["qs", "ipc", "call", "skin", "set", "legacy"])
A._run = lambda cmd, timeout=6: (calls.append(cmd) or (0, "skin alchemos", ""))
check("toggle call", (A.set_skin("toggle").get("skin"), calls[-1][-1]), ("alchemos", "toggle"))
A._run = lambda cmd, timeout=6: (0, "legacy skin not installed", "")
check("not installed", A.set_skin("legacy"), {"ok": False, "error": "legacy skin not installed"})
check("bad name", A.set_skin("chrome").get("ok"), False)

# theme presets: each skin's names work in the other (STARK OS preset ⇄ the metal that replaced it)
METALS = ["AURUM", "ARGENT", "IRON", "VERDIGRIS", "MERCURY", "LEAD", "PINKY"]
OLD = ["STARK", "MARK III", "VIBRANIUM", "MATRIX", "ARCTIC", "SOLAR", "PINKY"]
for spoken, presets, want in [("mark three", METALS, "IRON"), ("Mark 3", METALS, "IRON"), ("matrix", METALS, "VERDIGRIS"),
                              ("solar", METALS, "AURUM"), ("iron", METALS, "IRON"), ("verdigris", METALS, "VERDIGRIS"),
                              ("argent", METALS, "ARGENT"), ("pinky", METALS, "PINKY"),
                              ("iron", OLD, "MARK III"), ("aurum", OLD, "SOLAR"), ("lead", OLD, "VIBRANIUM"),
                              ("stark", OLD, "STARK"), ("chrome", METALS, None)]:
    check(f"preset {spoken!r} in {presets[0]}…", A.match_preset(spoken, presets), want)
check("choices", sorted(A.preset_choices(["IRON", "PINKY"])), ["IRON", "MARK III", "PINKY"])

# the desktop's name, spoken
from core import speech  # noqa: E402
check("speak AlchemOS", speech.normalize("Welcome to AlchemOS. ALCHEMOS skin."), "Welcome to Alkem O S. Alkem O S skin.")
check("speak STARK OS", speech.normalize("STARK OS online."), "Stark O S online.")
# the clock's role words for the new clock
check("role circle", A.norm_role("the alchemical circle"), "clock")

print(f"\n{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
