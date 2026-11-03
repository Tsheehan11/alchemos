"""
The effect chain on every Jarvis line, in-process with pedalboard (no sox, no
extra processes): pitch → band limits → warm EQ → drive → compressor → chorus →
small-room reverb → limiter. Presets live in effects.json (CLEAN, HOLOGRAM, SUIT;
AUTO = SUIT on headphones, HOLOGRAM on speakers); every knob there can be edited, and Settings → JARVIS adds its pitch on top.
Costs ~6 ms per sentence, ~75 ms with the pitch shifter on.

Loudness is matched on both sides of the chain (BS.1770-style K-weighted, gated LUFS per sentence):
Kokoro voices come out between -23 and -19 LUFS, so the input is levelled to IN_LUFS first (the drive
and compressor then behave the same for every voice); the presets themselves moved the level by up
to 3 dB (HOLOGRAM loudest), so every preset's output is levelled to OUT_LUFS, then a look-ahead
limiter keeps peaks under CEILING_DB. OUT_LUFS is the level at VOICE VOLUME 100 %; the volume
setting is a plain gain applied at playback (core/voice.py), after all of this.
"""
import json
import re
import subprocess
import time

import numpy as np

from .config import JARVIS_DIR

PRESETS_FILE = JARVIS_DIR / "effects.json"
DEFAULT_PRESET = "HOLOGRAM"
TAIL_S = 0.18          # silence after each sentence: the reverb tail plus a natural pause
IN_LUFS = -21.0        # Kokoro before the chain (its voices measured -23 to -19)
OUT_LUFS = -15.0       # every preset after the chain = VOICE VOLUME 100 %; the 60 % default ≈ -19.4
CEILING_DB = -1.0      # sample peak after the limiter
MAX_GAIN_DB = 24.0     # never boost more than this (near-silent input)
NORM_VERSION = 1       # part of the tts-cache key: bump when the levelling changes

_boards = {}
_auto = {"at": 0.0, "name": DEFAULT_PRESET}
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


def on_headphones():
    """Is the default output personal (headphones / a headset) rather than a room speaker?
    Personal: anything that says headphone / headset (Bluetooth, the jack), and any USB audio
    device: USB headsets and dongles report a plain "USB Audio" card with an "analog-output-speaker"
    port and no form factor, so the name can't be trusted. Room: the laptop speakers, HDMI /
    DisplayPort monitors, and Bluetooth speakers (the Google Home reports "unknown")."""
    try:
        default = subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=2).stdout.strip()
        sinks = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sinks"], capture_output=True,
                                          text=True, timeout=2).stdout)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False
    for s in sinks:
        if s.get("name") == default:
            p = s.get("properties", {})
            hints = " ".join(str(x) for x in (p.get("device.form_factor"), p.get("device.icon_name"), s.get("active_port")))
            return bool(re.search(r"head(phone|set)", hints, re.I)) or p.get("device.bus") == "usb"
    return False


def forget_auto():
    """The output just changed (his explicit switch): work AUTO out again on the next sentence."""
    _auto["at"] = 0.0


def resolve(name):
    """AUTO → SUIT on headphones, HOLOGRAM on speakers (checked at most every 3 s)."""
    if name != "AUTO":
        return name
    if time.monotonic() - _auto["at"] > 3:
        _auto.update(at=time.monotonic(), name="SUIT" if on_headphones() else "HOLOGRAM")
    return _auto["name"]


def preset(name):
    name = resolve(name)
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
    chain.append(Limiter(threshold_db=-2.0))     # part of the tone (it squeezes); the level is set afterwards
    return Pedalboard(chain)


_kweight = {}


def loudness(audio, sr):
    """Integrated loudness in LUFS, BS.1770 style: K-weighting (38 Hz high-pass + 4 dB shelf at
    1.5 kHz), 400 ms blocks with 75 % overlap, -70 LUFS absolute and -10 LU relative gates.
    A sentence shorter than one block is measured whole. -inf for silence."""
    from pedalboard import HighpassFilter, HighShelfFilter, Pedalboard
    if sr not in _kweight:
        _kweight[sr] = Pedalboard([HighpassFilter(38), HighShelfFilter(1500, gain_db=4.0)])
    k = _kweight[sr](np.asarray(audio, np.float32), sr, reset=True).astype(np.float64)
    n, hop = int(0.4 * sr), int(0.1 * sr)
    sq = k * k
    if len(sq) <= n:
        blocks = np.array([sq.mean()]) if len(sq) else np.array([0.0])
    else:
        c = np.concatenate([[0.0], np.cumsum(sq)])
        starts = np.arange(0, len(sq) - n + 1, hop)
        blocks = (c[starts + n] - c[starts]) / n
    blocks = blocks[blocks > 10 ** ((-70 + 0.691) / 10)]
    if not len(blocks):
        return float("-inf")
    rel = 10 * np.log10(blocks.mean()) - 0.691 - 10
    blocks = blocks[10 * np.log10(blocks) - 0.691 > rel]
    return float(10 * np.log10(blocks.mean()) - 0.691)


def normalize(audio, sr, target):
    """Gain so the sentence measures `target` LUFS (silence is left alone, boosts capped)."""
    lu = loudness(audio, sr)
    if not np.isfinite(lu):
        return audio
    return (audio * 10 ** (min(target - lu, MAX_GAIN_DB) / 20)).astype(np.float32)


def limit(audio, sr, ceiling_db=CEILING_DB, lookahead_ms=3.0, release_ms=60.0):
    """Look-ahead peak limiter: gain reaches its minimum before the peak arrives (no clipped
    edges), then recovers over release_ms. Untouched when nothing is over the ceiling."""
    from scipy.ndimage import minimum_filter1d
    from scipy.signal import lfilter
    ceiling = 10 ** (ceiling_db / 20)
    peak = np.abs(audio)
    if peak.max(initial=0.0) <= ceiling:
        return audio
    need = np.minimum(1.0, ceiling / np.maximum(peak, 1e-9))
    la = max(1, int(sr * lookahead_ms / 1000))
    need = minimum_filter1d(need, size=2 * la + 1, mode="nearest")      # starts la samples early
    a = np.exp(-1.0 / (sr * release_ms / 1000))
    # release: gain may rise only slowly, never above what's needed → run a smoothed max of (1 - gain)
    red = 1.0 - need
    smooth = np.maximum(red, lfilter([1 - a], [1, -a], red))
    out = audio * (1.0 - np.maximum(red, smooth))
    return np.clip(out, -ceiling, ceiling).astype(np.float32)        # float rounding only


def apply(audio, sr, fx, pitch=0.0):
    """One sentence (float32 mono) → processed, with the tail padded on, at OUT_LUFS (+ the
    preset's deliberate gain_db), peaks under CEILING_DB."""
    audio = normalize(np.asarray(audio, np.float32), sr, IN_LUFS)
    audio = np.concatenate([audio, np.zeros(int(sr * TAIL_S), np.float32)])
    key = (json.dumps(fx, sort_keys=True), round(pitch, 2), sr)
    if key not in _boards:
        _boards.clear()
        _boards[key] = _board(fx, pitch)
    out = _boards[key](audio, sr, reset=True)
    out = normalize(out, sr, OUT_LUFS + float(fx.get("gain_db", 0) or 0))
    return limit(out, sr)
