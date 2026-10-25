"""
The effect chain on every Jarvis line, in-process with pedalboard (no sox, no
extra processes): pitch → band limits → warm EQ → drive → compressor → chorus →
small-room reverb → limiter. Presets live in effects.json (CLEAN, HOLOGRAM, SUIT);
every knob there can be edited, and Settings → JARVIS adds its pitch on top.
Costs ~6 ms per sentence, ~75 ms with the pitch shifter on.
"""
import json

import numpy as np

from .config import JARVIS_DIR

PRESETS_FILE = JARVIS_DIR / "effects.json"
DEFAULT_PRESET = "HOLOGRAM"
TAIL_S = 0.18          # silence after each sentence: the reverb tail plus a natural pause

_boards = {}
_presets = {"mtime": None, "data": {}}


def presets():
    try:
        m = PRESETS_FILE.stat().st_mtime
        if m != _presets["mtime"]:
            data = json.loads(PRESETS_FILE.read_text())
            _presets.update(mtime=m, data={k: v for k, v in data.items() if not k.startswith("_")})
    except (OSError, ValueError):
        pass
    return _presets["data"]


def preset(name):
    p = presets()
    return p.get(name) or p.get(DEFAULT_PRESET) or {}


def _board(fx, pitch):
    from pedalboard import (Chorus, Compressor, Distortion, Gain, HighpassFilter, HighShelfFilter, Limiter,
                            LowpassFilter, LowShelfFilter, Pedalboard, PeakFilter, PitchShift, Reverb)
    chain = []
    if abs(pitch) >= 0.05:
        chain.append(PitchShift(semitones=pitch))
    if fx.get("highpass_hz"):
        chain.append(HighpassFilter(fx["highpass_hz"]))
    if fx.get("lowpass_hz"):
        chain.append(LowpassFilter(fx["lowpass_hz"]))
    if fx.get("warmth_db"):
        chain.append(LowShelfFilter(220, gain_db=fx["warmth_db"]))
    if fx.get("presence_db"):
        chain.append(PeakFilter(fx.get("presence_hz", 2500), gain_db=fx["presence_db"], q=0.9))
    if fx.get("air_db"):
        chain.append(HighShelfFilter(7000, gain_db=fx["air_db"]))
    if fx.get("drive_db"):
        chain.append(Distortion(drive_db=fx["drive_db"]))
        chain.append(Gain(-fx["drive_db"] / 2))
    if fx.get("compress"):
        chain.append(Compressor(threshold_db=-20, ratio=2.5, attack_ms=5, release_ms=80))
    if fx.get("chorus_mix"):
        chain.append(Chorus(rate_hz=0.5, depth=fx.get("chorus_depth", 0.05), centre_delay_ms=6,
                            feedback=0.0, mix=fx["chorus_mix"]))
    if fx.get("reverb_wet"):
        chain.append(Reverb(room_size=fx.get("reverb_room", 0.2), damping=0.6, wet_level=fx["reverb_wet"],
                            dry_level=1.0 - fx["reverb_wet"] / 2, width=0.5))
    chain.append(Gain(fx.get("gain_db", 0)))
    chain.append(Limiter(threshold_db=-2.0))
    return Pedalboard(chain)


def apply(audio, sr, fx, pitch=0.0):
    """One sentence (float32 mono) → processed, with the tail padded on."""
    audio = np.concatenate([audio.astype(np.float32), np.zeros(int(sr * TAIL_S), np.float32)])
    key = (json.dumps(fx, sort_keys=True), round(pitch, 2), sr)
    if key not in _boards:
        _boards.clear()
        _boards[key] = _board(fx, pitch)
    return np.clip(_boards[key](audio, sr, reset=True), -0.95, 0.95)   # the limiter can overshoot a little
