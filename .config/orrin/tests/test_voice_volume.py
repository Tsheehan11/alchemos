#!/usr/bin/env python3
"""Voice volume: loudness matching across presets, the limiter, the playback gain (incl. the
Bluetooth speaker's own level) and the orrin_volume action (against a temp settings.json).
No audio is played. Run: python tests/test_voice_volume.py"""
import json
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import effects  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


SR = 24000
rng = np.random.default_rng(1)


def speechlike(level, seconds=2.5):
    """Syllable-rate bursts of band-limited noise with pauses, at roughly `level` amplitude."""
    t = np.arange(int(SR * seconds)) / SR
    env = np.clip(np.sin(2 * np.pi * 3.5 * t), 0, None) ** 2 * (np.sin(2 * np.pi * 0.4 * t) > -0.6)
    noise = np.convolve(rng.standard_normal(len(t)), np.ones(8) / 8, mode="same")
    return (level * env * noise / np.abs(noise).max()).astype(np.float32)


# ── loudness ──
a = speechlike(0.5)
l1, l2 = effects.loudness(a, SR), effects.loudness(a / 2, SR)
check("half amplitude = -6 LU", round(l1 - l2, 1), 6.0)
check("silence", effects.loudness(np.zeros(SR, np.float32), SR), float("-inf"))
check("normalize hits target", round(effects.loudness(effects.normalize(a, SR, -21.0), SR), 1), -21.0)
check("normalize leaves silence", effects.normalize(np.zeros(100, np.float32), SR, -21.0).max(), 0.0)

# ── limiter ──
loud = speechlike(3.0)
lim = effects.limit(loud, SR)
check("limiter ceiling", float(np.abs(lim).max()) <= 10 ** (effects.CEILING_DB / 20) + 1e-6, True)
quiet = speechlike(0.2)
check("limiter leaves quiet audio alone", np.array_equal(effects.limit(quiet, SR), quiet), True)

# ── every preset comes out equally loud, whatever goes in ──
levels = {}
for name in ("CLEAN", "HOLOGRAM", "SUIT"):
    fx = effects.presets()[name]
    for inp in (0.05, 0.3, 0.9):
        out = effects.apply(speechlike(inp), SR, fx, fx.get("pitch", 0))
        levels[(name, inp)] = effects.loudness(out, SR)
        check(f"{name} @ {inp}: peak under ceiling", float(np.abs(out).max()) <= 10 ** (effects.CEILING_DB / 20) + 1e-6, True)
spread = max(levels.values()) - min(levels.values())
check(f"presets × input levels within 1.5 LU of each other (spread {spread:.2f})", spread <= 1.5, True)
check("level near OUT_LUFS", all(abs(v - effects.OUT_LUFS) <= 1.5 for v in levels.values()), True)

# ── playback gain ──
from core import voice as V  # noqa: E402


class Spk:
    def sink(self):
        return "bluez_output.AA_BB_CC_DD_EE_01.1"


v = V.Voice.__new__(V.Voice)
v.overrides, v.speaker = {}, Spk()
v.cfg = {"orrinVoiceVolume": 60, "orrinSpeakerVolume": -1}
check("default 60 %", v.volume(), 0.6)
check("speaker follows voice when SAME", v.volume("bluez_output.AA_BB_CC_DD_EE_01.1"), 0.6)
v.cfg["orrinSpeakerVolume"] = 35
check("speaker's own level on the speaker", v.volume("bluez_output.AA_BB_CC_DD_EE_01.1"), 0.35)
check("…not on other outputs", v.volume("alsa_output.pci-0000_00_1f.3.analog-stereo"), 0.6)
v.cfg["orrinVoiceVolume"] = 0
check("0 % is silent", v.volume(), 0.0)
v.cfg["orrinVoiceVolume"] = 140
check("clamped to 100 %", v.volume(), 1.0)

# ── the orrin_volume action (temp settings.json) ──
import alchemos_actions as A  # noqa: E402

tmp = Path(tempfile.mkdtemp())
A.HUD_SETTINGS = tmp / "settings.json"
A.HUD_SETTINGS.write_text(json.dumps({"orrinVoiceVolume": 60, "orrinSpeaker": "", "other": "kept"}, indent=4))
read = lambda: json.loads(A.HUD_SETTINGS.read_text())
check("up one step", A.orrin_volume("up")["percent"], 75)
check("written", read()["orrinVoiceVolume"], 75)
check("other keys kept", read()["other"], "kept")
check("set 40", (A.orrin_volume("set", 40)["percent"], read()["orrinVoiceVolume"]), (40, 40))
check("set accepts '40%'", A.orrin_volume("set", "40%")["percent"], 40)
check("out of range refused", A.orrin_volume("set", 140)["ok"], False)
A.orrin_volume("set", 15)
check("a step down stops at 10", (A.orrin_volume("down")["percent"], A.orrin_volume("down")["percent"]), (10, 10))
check("set 0 allowed", A.orrin_volume("set", 0)["percent"], 0)
A.orrin_volume("set", 95)
check("up stops at 100", (A.orrin_volume("up")["percent"], A.orrin_volume("up").get("note")), (100, "already at the limit"))
A.HUD_SETTINGS.write_text(json.dumps({"orrinVoiceVolume": 60, "orrinSpeakerVolume": 30, "orrinSpeaker": "AA:BB:CC:DD:EE:01"}))
A._speaker_in_use = lambda mac: True
check("on the speaker with its own level: changes that", (A.orrin_volume("up")["where"], read()["orrinSpeakerVolume"], read()["orrinVoiceVolume"]),
      ("Bluetooth speaker", 45, 60))
A._speaker_in_use = lambda mac: False
check("on headphones: changes voice volume", (A.orrin_volume("up")["where"], read()["orrinVoiceVolume"]), ("voice", 75))
A.set_dry_run(True)
check("dry run writes nothing", (A.orrin_volume("set", 20)["percent"], read()["orrinVoiceVolume"]), (20, 75))
A.set_dry_run(False)
check("labels", A.tool_label("orrin_volume", {"action": "set", "percent": 40}), "VOICE → 40%")
check("never needs a yes", A.confirmation_prompt("orrin_volume", {"action": "set", "percent": 0}), None)

# laptop mode: the Bluetooth room speaker is never wanted
from core import config as CF, voice as VV  # noqa: E402
spk = VV.Speaker({"orrinSpeaker": "AA:BB:CC:DD:EE:01"}, log=lambda *a: None)
VV.effects.on_headphones = lambda: False
import audio_devices as AD  # noqa: E402
AD.explicit_output = lambda sig=None: None   # not the live $XDG_RUNTIME_DIR/orrin/audio-choice.json: a real output pick
AD.choice_mtime = lambda: 0.0                # (Settings → AUDIO, "switch to my headphones") made this check fail
check("docked, not on headphones: speaker wanted", spk.wanted(), True)
CF.LAPTOP, spk._wanted = True, (0.0, False)
check("laptop mode: speaker not wanted", spk.wanted(), False)
CF.LAPTOP = False

print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
