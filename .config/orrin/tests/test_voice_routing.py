#!/usr/bin/env python3
"""AUTO voice effect routing (core/effects.py): output classification (headphones / speaker / Bluetooth
speaker), each skin's per-persona voiceRouting over the base, the legacy skin unchanged (SUIT on
headphones, HOLOGRAM on speakers), names AUTO never touches. No pactl / HUD needed: both are stubbed.
Run: python tests/test_voice_routing.py"""
import os
import sys

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [ROOT]
from core import effects, persona  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def sink(bus=None, form=None, icon=None, port=None, api=None):
    p = {k: v for k, v in {"device.bus": bus, "device.form_factor": form, "device.icon_name": icon, "device.api": api}.items() if v}
    return {"name": "x", "properties": p, "active_port": port}


# ── classification ──
for name, s, want in [
    ("bt headphones", sink(bus="bluetooth", form="headphone", icon="audio-headphones-bluetooth"), "headphones"),
    ("bt headset", sink(bus="bluetooth", form="headset"), "headphones"),
    ("jack headphones", sink(bus="pci", port="analog-output-headphones"), "headphones"),
    ("usb dongle", sink(bus="usb", port="analog-output-speaker"), "headphones"),
    ("bt speaker (Google Home)", sink(bus="bluetooth", form="unknown", icon="audio-card-bluetooth"), "bt_speaker"),
    ("bluez api, no bus", sink(api="bluez5"), "bt_speaker"),
    ("laptop speakers", sink(bus="pci", port="analog-output-speaker", form="internal"), "speaker"),
    ("hdmi monitor", sink(bus="pci", port="hdmi-output-0"), "speaker"),
    ("nothing known", sink(), "speaker"),
]:
    check(f"classify {name}", effects.classify(s), want)

# ── routing per skin ──
ALCH = {"voiceRouting": {"orrin": {"headphones": "CHAMBER", "speaker": "ALEMBIC", "btSpeaker": "RESONANT"},
                         "selene": {"headphones": "RESONANT", "speaker": "ALEMBIC", "btSpeaker": "RESONANT"}}}
SKIN = {"data": ALCH}
persona.skin_data = lambda cfg=None: SKIN["data"]
effects.presets = lambda: {k: {} for k in ["CLEAN", "HOLOGRAM", "SUIT", "CHAMBER", "RESONANT", "ALEMBIC"]}


def auto(kind, who):
    effects._auto.update(at=1e18, kind=kind)       # the output, as if just checked
    return effects.resolve("AUTO", who)


for kind, j, f in [("headphones", "CHAMBER", "RESONANT"), ("speaker", "ALEMBIC", "ALEMBIC"), ("bt_speaker", "RESONANT", "RESONANT")]:
    check(f"alchemos orrin {kind}", auto(kind, "orrin"), j)
    check(f"alchemos friday {kind}", auto(kind, "selene"), f)

SKIN["data"] = {"personas": {}}                    # legacy: no voiceRouting → AUTO as it always was
for kind, want in [("headphones", "SUIT"), ("speaker", "HOLOGRAM"), ("bt_speaker", "HOLOGRAM")]:
    check(f"legacy jarvis {kind}", auto(kind, "orrin"), want)
    check(f"legacy friday {kind}", auto(kind, "selene"), want)

SKIN["data"] = {"voiceRouting": {"orrin": {"headphones": "NOPE", "speaker": "clean"}}}   # unknown preset, lower case
check("unknown preset falls back to base", auto("headphones", "orrin"), "SUIT")
check("names are upper-cased", auto("speaker", "orrin"), "CLEAN")
check("missing persona → base", auto("bt_speaker", "selene"), "HOLOGRAM")

check("non-AUTO untouched", effects.resolve("CHAMBER", "selene"), "CHAMBER")
effects.output_kind = lambda: "headphones"
check("on_headphones follows the classification", effects.on_headphones(), True)

if FAILS:
    print(f"{len(FAILS)} failing")
    sys.exit(1)
print("ok voice routing")
