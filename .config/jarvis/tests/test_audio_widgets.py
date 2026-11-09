#!/usr/bin/env python3
"""Audio routing (mcp/audio_devices.py names → devices, never guessing; the explicit-choice marker),
Jarvis's own mic pick (jarvis.py Mic.pick), the fast-path rules for audio and the new widget types,
the agenda feed's tracker / calendar linking (core/feed.link_due) and token accounting
(jarvis_db.add_usage / usage_since). Fake device lists and a temp DB / runtime dir: nothing is
switched and no audio is touched. Run: python tests/test_audio_widgets.py"""
import importlib.util
import os
import sys
import tempfile
import time
import types
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp(prefix="jarvis-audio-test-"))
os.environ["XDG_RUNTIME_DIR"] = str(TMP)
os.environ["JARVIS_DB"] = str(TMP / "test.db")          # never the real jarvis.db

import audio_devices as AD  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def dev(name, label, kind, available=True, default=False):
    return {"name": name, "label": label, "kind": kind, "available": available, "default": default,
            "bluetooth": name.startswith("bluez_")}


OUTS = [dev("alsa_output.HDMI1", "HDMI 1", "tv", available=False), dev("alsa_output.Speaker__sink", "Laptop Speaker", "laptop"),
        dev("bluez_output.80_99.1", "WH-1000XM4", "headphones", default=True)]
INS = [dev("alsa_input.Headset__source", "Headset Mono Microphone", "headphones", available=False),
       dev("alsa_input.Mic1__source", "Digital Microphone", "laptop", default=True), dev("bluez_input.80:99", "WH-1000XM4", "headphones")]

# ── spoken names ──
def res(word, direction="out", devs=None):
    state, hit = AD.resolve(word, direction, devs if devs is not None else (OUTS if direction == "out" else INS))
    return state, (hit["name"] if isinstance(hit, dict) else [d["name"] for d in hit] if isinstance(hit, list) else hit)


check("headphones", res("my headphones"), ("ok", "bluez_output.80_99.1"))
check("laptop speakers", res("the laptop speakers"), ("ok", "alsa_output.Speaker__sink"))
check("by label", res("wh-1000xm4"), ("ok", "bluez_output.80_99.1"))
check("tv unplugged", res("tv")[0], "none")
check("headset mic", res("headset mic", "in"), ("ok", "bluez_input.80:99"))
check("laptop mic", res("laptop", "in"), ("ok", "alsa_input.Mic1__source"))
check("speaker has no mic", res("speaker", "in")[0], "none")
check("garbage", res("toaster")[0], "none")
two = OUTS + [dev("bluez_output.AA_BB.1", "AirPods", "headphones")]
check("two headphones ask", res("headphones", devs=two), ("ask", ["bluez_output.80_99.1", "bluez_output.AA_BB.1"]))
AD.room_speaker_mac = lambda: "20:DF:B9:08:87:74"
check("room speaker not connected → connect", res("speakers"), ("connect", "20:DF:B9:08:87:74"))
AD.room_speaker_mac = lambda: ""
check("no room speaker → laptop", res("speakers"), ("ok", "alsa_output.Speaker__sink"))

# classify from PipeWire properties
check("classify bt headset", AD.classify({"name": "bluez_output.80_99_E7.1", "properties": {"device.form_factor": "headset"}}, "out"), "headphones")
check("classify room speaker", AD.classify({"name": "bluez_output.20_DF_B9_08_87_74.1", "properties": {"api.bluez5.address": "20:DF:B9:08:87:74"}},
                                           "out", "20:DF:B9:08:87:74"), "speaker")
check("classify hdmi", AD.classify({"name": "alsa_output.pci.HiFi__HDMI1__sink", "properties": {"device.icon_name": "video-display", "device.bus": "pci"}}, "out"), "tv")
check("classify usb mic", AD.classify({"name": "alsa_input.usb-JMTek", "properties": {"device.bus": "usb"}}, "in"), "usb")

# ── explicit choice: holds while the device set is the same, ends on any change ──
sig = ["a", "b"]
AD.signature = lambda: list(sig)
AD.mark_choice("out", "alsa_output.Speaker__sink")
check("choice holds", AD.explicit_output(), "alsa_output.Speaker__sink")
sig.append("c")
check("choice ends on plug", AD.explicit_output(), None)
check("choice file gone", AD.CHOICE_FILE.exists(), False)

# ── Jarvis's wake-word mic ──
spec = importlib.util.spec_from_file_location("jarvis_main", os.path.join(ROOT, "jarvis.py"))
JV = importlib.util.module_from_spec(spec)
saved = sys.argv
sys.argv = ["jarvis.py"]
spec.loader.exec_module(JV)
sys.argv = saved


class Cfg(dict):
    def __getitem__(self, k):
        return self.get(k)


AD.devices = lambda direction="out": INS if direction == "in" else OUTS
cfg = Cfg(jarvisMic="auto", jarvisMicBluetooth=False)
mic = JV.Mic(cfg)
check("auto: no wired headset, BT off → DMIC", mic.pick()[0], "alsa_input.Mic1__source")
cfg["jarvisMicBluetooth"] = True
check("auto: BT headset never picked by AUTO", mic.pick()[0], "alsa_input.Mic1__source")
cfg["jarvisMicBluetooth"] = False
INS[0]["available"] = True
check("auto: wired headset plugged → still the laptop mic", mic.pick()[0], "alsa_input.Mic1__source")
cfg["jarvisMicBluetooth"] = True
check("auto: laptop mic over wired and BT", mic.pick()[0], "alsa_input.Mic1__source")
cfg["jarvisMic"] = "default"
check("default", mic.pick()[0], "")
cfg["jarvisMic"] = ""
check("legacy empty = default", mic.pick()[0], "")
cfg["jarvisMic"] = "alsa_input.gone"
check("pinned but missing → auto's pick (laptop)", mic.pick()[0], "alsa_input.Mic1__source")
cfg["jarvisMic"] = "alsa_input.Headset__source"
check("headset only when picked by name", mic.pick()[0], "alsa_input.Headset__source")
cfg["jarvisMic"] = "alsa_input.Mic1__source"
check("pinned", mic.pick()[0], "alsa_input.Mic1__source")

# ── fast path ──
from core import fastpath as F  # noqa: E402


def fp(t):
    r = F.match(t)
    return [(s["tool"], s["args"]) for s in r] if r else r


check("fp switch to headphones", fp("switch audio to my headphones"), [("set_audio_output", {"device": "headphones"})])
check("fp back to speakers", fp("back to speakers"), [("set_audio_output", {"device": "speakers"})])
check("fp headset mic", fp("use my headset mic"), [("set_audio_input", {"device": "headset"})])
check("fp laptop mic", fp("switch the mic to the laptop"), [("set_audio_input", {"device": "laptop"})])
check("fp tv needs an audio word", fp("switch to the tv"), None)
check("fp music on the TV is a screen role", fp("put music on the TV")[0][0], "set_screen_role")
check("fp connect headphones isn't a switch", fp("connect my headphones"), None)
check("fp calendar widget", fp("show my calendar widget on monitor 2"),
      [("widget_add", {"type": "calendar", "size": "", "screen": "monitor 2", "position": ""})])
check("fp calendar without widget → Claude", fp("show my calendar"), None)
check("fp weather widget", fp("show the weather widget")[0][1]["type"], "weather")
check("fp usage widget", fp("show a claude usage widget")[0][1]["type"], "usage")
check("fp remove due widget", fp("remove the due widget"), [("widget_remove", {"target": "due", "screen": ""})])
check("fp integration intent still guarded", F.is_integration_intent("what's on my calendar"), True)
check("fp widget phrase not integration", F.is_integration_intent("move the agenda widget to the left"), False)
# free widget placement: voice moves / reset stay on the fast path
check("fp move to a corner of a monitor", fp("move the calendar widget to the top right of monitor 2"),
      [("widget_move", {"target": "calendar", "screen": "monitor 2", "position": "the top right"})])
import stark_actions as SA  # noqa: E402
_ws = SA.widget_showing
SA.widget_showing = lambda kind: kind == "weather"          # a weather card is up, no media card
check("fp put without an article", fp("put weather in the centre of the laptop screen"),
      [("widget_move", {"target": "weather", "screen": "the laptop screen", "position": "the centre"})])
check("fp put without an article, none up → add", fp("put music on the laptop screen")[0][0] != "widget_move", True)
check("fp reset widget layout", fp("reset widget layout"), [("widget_reset", {})])
check("fp reset the widgets", fp("reset the widgets"), [("widget_reset", {})])
check("fp widgets back", fp("put the widgets back"), [("widget_reset", {})])
check("fp reset with a screen isn't a reset", (fp("reset the widgets on monitor 2") or [("", {})])[0][0] != "widget_reset", True)
check("fp put music on a monitor still asks", fp("put music on monitor 2"), [(None, {})])
SA.widget_showing = _ws

# widget_move → `qs ipc call widgets move <id> <screen> <x> <y>` (four args since free placement)
_calls = []
_orig = (SA._ipc_widgets, SA._widget_list, SA.DRY_RUN)
SA._widget_list = lambda: [{"id": "weather9", "type": "weather", "screen": "diag"}]
SA._ipc_widgets = lambda *a: (_calls.append(a), {"ok": True, "id": "weather9"})[1]
SA.DRY_RUN = False
SA.widget_move("weather", "laptop screen", "the centre")
SA.widget_reset()
SA._ipc_widgets, SA._widget_list, SA.DRY_RUN = _orig
check("widget_move ipc shape", _calls[0], ("move", "weather9", "media", "center", "-"))
check("widget_reset ipc", _calls[1], ("reset",))

import stark_actions as A  # noqa: E402
check("say ambiguous", A.audio_said({"ok": True, "ambiguous": True, "say": "Which one, sir: A or B?"}), "Which one, sir: A or B?")
check("say output", A.audio_said({"ok": True, "kind": "headphones"}), "Audio's on your headphones, sir.")
check("say mic", A.audio_said({"ok": True, "kind": "headphones"}, mic=True), "Using your headset mic, sir.")

# ── agenda: a tracker row's own calendar event becomes the row ──
from core import feed  # noqa: E402
import datetime as dt  # noqa: E402
day = dt.datetime(2026, 11, 4)
ms = lambda d: int(d.timestamp() * 1000)  # noqa: E731
events = [{"title": "[MATH 135] Weekly assessment W6 (Möbius)", "start": ms(day), "end": ms(day + dt.timedelta(days=1)), "all_day": True},
          {"title": "SE 101 lecture", "start": ms(day.replace(hour=10)), "end": ms(day.replace(hour=11)), "all_day": False}]
due = [{"title": "Weekly assessment W6", "course": "MATH 135", "label": "MATH 135 W6", "due": ms(day.replace(hour=23, minute=59)), "days": 1, "status": "Not Started"},
       {"title": "A5", "course": "CS 137", "label": "CS 137 A5", "due": ms(day.replace(hour=23, minute=59)), "days": 1, "status": "Not Started"}]
ev2, due2 = feed.link_due(events, due)
check("linked event marked", ev2[0].get("tracker"), True)
check("timed event untouched", ev2[1].get("tracker"), None)
check("linked row dropped", [d["label"] for d in due2], ["CS 137 A5"])

# ── token accounting ──
import jarvis_db as db  # noqa: E402
check("temp db", str(db.DB_PATH), str(TMP / "test.db"))
t0 = time.time() - 1
db.add_usage("test-audio-widgets", types.SimpleNamespace(model_usage={
    "claude-haiku-5-5": {"inputTokens": 10, "outputTokens": 5, "cacheReadInputTokens": 100, "cacheCreationInputTokens": 7},
    "claude-sonnet-5-5": {"inputTokens": 30, "outputTokens": 20}}, usage=None))
db.add_usage("test-audio-widgets", types.SimpleNamespace(model_usage={}, usage={"input_tokens": 1, "output_tokens": 2}, model="claude-haiku-5-5"))
u = db.usage_since(t0)
check("haiku tokens", (u["models"]["haiku"]["input"], u["models"]["haiku"]["output"], u["models"]["haiku"]["cache_write"]), (11, 7, 7))
check("sonnet tokens", u["models"]["sonnet"]["output"], 20)
check("requests", u["models"]["haiku"]["requests"], 2)
with db._db() as c:
    c.execute("DELETE FROM claude_usage WHERE source = 'test-audio-widgets'")

print("FAILED: " + ", ".join(FAILS) if FAILS else "all audio / widget checks passed")
sys.exit(1 if FAILS else 0)
