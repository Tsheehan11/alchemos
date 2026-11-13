"""
Stage-by-stage trace of every exchange → ~/.local/state/orrin/trace.log
(`orrin --trace` tails it). Each line: wall time, ms since the wake word, stage, fields.

  12:04:31.512  #14 +0      wake        score=0.91
  12:04:33.020  #14 +1508   vad.end     reason=silence speech=1.10s max=0.97
  12:04:33.391  #14 +1879   stt         ms=371 text="what time is it"
  ...

Audio: `orrin --record [MIN]` also saves each exchange (and wake-word near
misses) as WAV in ~/.local/state/orrin/rec/ for MIN minutes (default 60), so
thresholds can be tuned from real recordings. Off unless asked; capped at 150 files.
"""
import os
import threading
import time
import wave
from datetime import datetime
from pathlib import Path

STATE_DIR = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "orrin"
TRACE_FILE = STATE_DIR / "trace.log"
REC_DIR = STATE_DIR / "rec"
RECORD_UNTIL = STATE_DIR / "record-until"
MAX_BYTES = 2_000_000
MAX_RECORDINGS = 150
WAKE_DIR = STATE_DIR / "wakes"   # the 2 s that woke it, every idle wake (local only; hard negatives for retraining)
MAX_WAKES = 100
WAKE_DAYS = 14

_lock = threading.Lock()
_ex = {"n": 0, "t0": None, "marks": {}}
_rec = {"checked": 0.0, "on": False}


def _fmt(v):
    if isinstance(v, float):
        return f"{v:.3f}".rstrip("0").rstrip(".") if abs(v) < 100 else f"{v:.0f}"
    if isinstance(v, str) and (not v or any(c in v for c in ' ="')):
        return '"' + v.replace('"', "'")[:300] + '"'
    return str(v)


def _write(line):
    with _lock:
        try:
            STATE_DIR.mkdir(parents=True, exist_ok=True)
            if TRACE_FILE.exists() and TRACE_FILE.stat().st_size > MAX_BYTES:
                TRACE_FILE.replace(TRACE_FILE.with_suffix(".log.old"))
            with open(TRACE_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


def begin():
    """A new exchange (the wake word fired). Returns its number."""
    _ex["n"] += 1
    _ex["t0"] = time.monotonic()
    _ex["marks"] = {}
    return _ex["n"]


def ms():
    """ms since the wake word, or None outside an exchange."""
    return None if _ex["t0"] is None else int((time.monotonic() - _ex["t0"]) * 1000)


def mark(name):
    """Remember when something happened in this exchange (e.g. end of speech)."""
    _ex["marks"][name] = time.monotonic()


def since(name):
    t = _ex["marks"].get(name)
    return None if t is None else int((time.monotonic() - t) * 1000)


def t(stage, **fields):
    now = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    rel = ms()
    where = f"#{_ex['n']:<3} +{rel:<6}" if rel is not None else f"{'':5} {'':7}"
    _write(f"{now}  {where} {stage:<11} " + " ".join(f"{k}={_fmt(v)}" for k, v in fields.items()))


def end():
    _ex["t0"] = None


# ── audio capture for tuning ──
def recording():
    now = time.time()
    if now - _rec["checked"] > 5:
        _rec["checked"] = now
        try:
            _rec["on"] = float(RECORD_UNTIL.read_text().strip()) > now
        except (OSError, ValueError):
            _rec["on"] = False
    return _rec["on"]


def set_recording(minutes):
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if minutes > 0:
        RECORD_UNTIL.write_text(str(time.time() + minutes * 60))
    else:
        RECORD_UNTIL.unlink(missing_ok=True)


def _wav(path, audio_int16, rate):
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(audio_int16.astype("<i2").tobytes())


def save_wake(model, raw, audio_int16, rate=16000):
    """WAV of the audio that woke it (always on, unlike save): wakes/<time>-<model>-<raw>.wav, the last
    MAX_WAKES and at most WAKE_DAYS old. mark_wake() later renames a false one. Returns the path."""
    try:
        WAKE_DIR.mkdir(parents=True, exist_ok=True)
        path = WAKE_DIR / f"{datetime.now():%m%d-%H%M%S}-{model}-{raw:.2f}.wav"
        _wav(path, audio_int16, rate)
        old = time.time() - WAKE_DAYS * 86400
        files = sorted(WAKE_DIR.glob("*.wav"), key=lambda f: f.stat().st_mtime)
        for i, f in enumerate(files):
            if i < len(files) - MAX_WAKES or f.stat().st_mtime < old:
                f.unlink(missing_ok=True)
        return path
    except OSError:
        return None


def mark_wake(path, verdict):
    """Rename a saved wake clip …-<verdict>.wav (verdict "false": nothing was said after it)."""
    if not path:
        return None
    try:
        new = path.with_name(f"{path.stem}-{verdict}.wav")
        path.rename(new)
        return new
    except OSError:
        return None


def save(kind, audio_int16, rate=16000):
    """WAV of one exchange / near miss (only while `orrin --record` is on). Returns the path."""
    if not recording():
        return None
    try:
        REC_DIR.mkdir(parents=True, exist_ok=True)
        path = REC_DIR / f"{datetime.now():%m%d-%H%M%S}-{_ex['n']:03d}-{kind}.wav"
        _wav(path, audio_int16, rate)
        files = sorted(REC_DIR.glob("*.wav"))
        for f in files[:-MAX_RECORDINGS]:
            f.unlink(missing_ok=True)
        return path
    except OSError:
        return None
