"""
Jarvis's voice. Kokoro (local, ONNX on CPU) by default, piper as the fallback,
then the effect chain (effects.py), streamed into pw-play.

Low latency: the reply is split into sentences; the first one starts playing
while the rest are still being generated (~0.35 s to first sound with Kokoro).
Short stock lines ("Done, sir.", "Very well, sir.") are rendered once and cached
on disk, so they play instantly.

Voice names: Kokoro voices as-is (bm_george, bm_fable…); piper voices by model
file, with a speaker for multi-speaker models (en_GB-semaine-medium:obadiah).
Music playing through MPRIS (Spotify etc.) is ducked while it talks.

Output: the default sink, except when it isn't headphones and a Bluetooth speaker
is set (Settings → JARVIS → Speaker): then Jarvis connects to it when it hears
"Hey Jarvis" (ready by the time you finish talking) and plays only its own voice
there. The system default output is left alone.

Setup (venv): uv pip install --python ~/.config/jarvis/.venv/bin/python kokoro-onnx pedalboard
Models: kokoro-v1.0.int8.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx
releases (model-files-v1.0) → ~/.local/share/jarvis/kokoro/
"""
import hashlib
import json
import queue
import re
import subprocess
import threading
import time

import numpy as np

from . import effects, trace
from .config import DATA_DIR, VOICES_DIR

KOKORO_DIR = DATA_DIR / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.int8.onnx"   # int8: ~5× real time on CPU, 300 MB; fp32 file is 40% slower
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
FALLBACK_PIPER = "en_GB-alan-medium"
CACHE_DIR = DATA_DIR / "tts-cache"
CACHE_MAX_WORDS = 6        # sentences this short get cached on disk
CACHE_MAX_FILES = 400
COMMON = ["Right away, sir.", "Done, sir.", "Very well, sir.", "Very good, sir.", "Online.",
          "You're welcome, sir.", "Goodnight, sir.", "Your timer is done, sir.", "Nothing's playing, sir."]

DUCK_TO = 0.3   # fraction of the player's volume while Jarvis speaks
ROMAN = {"II": "two", "III": "three", "IV": "four", "VI": "six", "VII": "seven", "VIII": "eight", "IX": "nine"}


def clean(text):
    """Make a reply speakable: no markdown, URLs or symbols read aloud."""
    t = re.sub(r"https?://\S+", "a link", text)
    t = re.sub(r"[`*_#>|]+", "", t)
    t = re.sub(r"^\s*[-•]\s+", "", t, flags=re.M)
    t = t.replace("°C", " degrees").replace("%", " percent").replace("→", "to")
    # "MARK III" → "Mark three" (lone "I" stays a pronoun)
    t = re.sub(r"\b(II|III|IV|VI|VII|VIII|IX)\b", lambda m: ROMAN[m.group(1)], t)
    return re.sub(r"\s+", " ", t).strip()


def sentences(text):
    parts = [p.strip() for p in re.split(r"(?<=[.!?;])\s+", text) if p.strip()]
    out = []
    for p in parts:   # glue fragments of one or two words onto the previous sentence
        if out and len(p.split()) <= 2 and not p.endswith((".", "!", "?")):
            out[-1] += " " + p
        else:
            out.append(p)
    return out


def is_kokoro(name):
    return bool(re.match(r"^[abefhijpz][fm]_", name or ""))


def kokoro_voices():
    try:
        from kokoro_onnx import Kokoro  # noqa: F401
        return sorted(np.load(KOKORO_VOICES).files)
    except Exception:
        return []


def piper_voices():
    """Piper voices on disk, multi-speaker models expanded (en_GB-semaine-medium:obadiah)."""
    out = []
    for f in sorted(VOICES_DIR.glob("*.onnx")):
        try:
            spk = json.loads(f.with_suffix(".onnx.json").read_text()).get("speaker_id_map") or {}
        except (OSError, ValueError):
            spk = {}
        out += [f"{f.stem}:{s}" for s in spk] if len(spk) > 1 else [f.stem]
    return out


class Ducker:
    def __init__(self):
        self.saved = {}

    def _players(self):
        p = subprocess.run(["playerctl", "-l"], capture_output=True, text=True)
        return p.stdout.split() if p.returncode == 0 else []

    def duck(self):
        self.saved = {}
        for pl in self._players():
            st = subprocess.run(["playerctl", "-p", pl, "status"], capture_output=True, text=True).stdout.strip()
            if st != "Playing":
                continue
            vol = subprocess.run(["playerctl", "-p", pl, "volume"], capture_output=True, text=True).stdout.strip()
            try:
                v = float(vol)
            except ValueError:
                continue
            self.saved[pl] = v
            subprocess.run(["playerctl", "-p", pl, "volume", f"{v * DUCK_TO:.3f}"], capture_output=True)

    def restore(self):
        for pl, v in self.saved.items():
            subprocess.run(["playerctl", "-p", pl, "volume", f"{v:.3f}"], capture_output=True)
        self.saved = {}


class Engines:
    """Loads each TTS model once. synth(name, text, speed) → (float32 audio, sample rate)."""

    def __init__(self):
        self._kokoro = None
        self._piper = {}
        self._lock = threading.Lock()

    def kokoro(self):
        with self._lock:
            if self._kokoro is None:
                import onnxruntime as ort
                from kokoro_onnx import Kokoro
                # 8 threads, no spin-waiting: ~14% slower than the default, a third of the CPU (13 s → 4 s per sentence)
                so = ort.SessionOptions()
                so.intra_op_num_threads = 8
                so.add_session_config_entry("session.intra_op.allow_spinning", "0")
                sess = ort.InferenceSession(str(KOKORO_MODEL), so, providers=["CPUExecutionProvider"])
                self._kokoro = Kokoro.from_session(sess, str(KOKORO_VOICES))
            return self._kokoro

    def piper(self, model):
        with self._lock:
            if model not in self._piper:
                from piper import PiperVoice
                path = VOICES_DIR / f"{model}.onnx"
                if not path.exists():
                    path = VOICES_DIR / f"{FALLBACK_PIPER}.onnx"
                self._piper[model] = PiperVoice.load(str(path))
            return self._piper[model]

    def synth(self, name, text, speed):
        if is_kokoro(name):
            k = self.kokoro()
            lang = "en-gb" if name.startswith("b") else "en-us"
            audio, sr = k.create(text, voice=name, speed=max(0.5, min(2.0, speed)), lang=lang)
            return np.asarray(audio, np.float32), sr
        from piper import SynthesisConfig
        model, _, speaker = name.partition(":")
        v = self.piper(model)
        sid = (v.config.speaker_id_map or {}).get(speaker) if speaker else None
        # volume 0.7: piper hits full scale and clips; lower noise scales cut its vocoder buzz
        syn = SynthesisConfig(speaker_id=sid, length_scale=1.0 / max(0.5, min(2.0, speed)),
                              volume=0.7, noise_scale=0.4, noise_w_scale=0.6)
        audio = np.concatenate([c.audio_float_array for c in v.synthesize(text, syn_config=syn)] or [np.zeros(1)])
        return audio.astype(np.float32), v.config.sample_rate


def bt_connected(mac):
    try:
        out = subprocess.run(["bluetoothctl", "info", mac], capture_output=True, text=True, timeout=3).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    return "Connected: yes" in out


def sink_names():
    try:
        out = subprocess.run(["pactl", "list", "sinks", "short"], capture_output=True, text=True, timeout=2).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return [line.split("\t")[1] for line in out.splitlines() if "\t" in line]


def default_sink():
    try:
        return subprocess.run(["pactl", "get-default-sink"], capture_output=True, text=True, timeout=2).stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        return ""


class Speaker:
    """The Bluetooth speaker Jarvis uses when you're not on headphones."""

    def __init__(self, cfg, log):
        self.cfg = cfg
        self.log = log
        self._thread = None
        self._lock = threading.Lock()

    @property
    def mac(self):
        try:
            return (self.cfg["jarvisSpeaker"] or "").strip()
        except KeyError:
            return ""

    def wanted(self):
        return bool(self.mac) and not effects.on_headphones()

    def sink(self):
        name = "bluez_output." + self.mac.replace(":", "_")
        return next((s for s in sink_names() if s.startswith(name)), None)

    def _connect(self):
        with self._lock:
            mac = self.mac
            if not mac or bt_connected(mac):
                return
            before = default_sink()
            for _ in range(3):           # the first page after idle often times out; the next one works
                try:
                    subprocess.run(["bluetoothctl", "--timeout", "8", "connect", mac], capture_output=True, timeout=12)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                if bt_connected(mac):
                    break
            for _ in range(20):          # the PipeWire sink shows up a moment after the link
                if self.sink():
                    break
                threading.Event().wait(0.2)
            now = default_sink()
            if before and now != before and now == self.sink():
                subprocess.run(["pactl", "set-default-sink", before], capture_output=True)   # only Jarvis goes there
            self.log(f"JARVIS: speaker {'connected' if self.sink() else 'unreachable'}")
            trace.t("speaker", state="connected" if self.sink() else "unreachable")

    def prepare(self):
        """Start connecting in the background (on the wake word)."""
        if self.wanted() and not (self._thread and self._thread.is_alive()):
            self._thread = threading.Thread(target=self._connect, daemon=True)
            self._thread.start()

    def target(self):
        """Sink name for pw-play, or None for the default output. Waits up to 8 s for a
        connect in progress; if the speaker still isn't there, this line uses the default output."""
        if not self.wanted():
            return None
        self.prepare()
        if self._thread and self._thread.is_alive():
            t0 = time.monotonic()
            self._thread.join(8)
            trace.t("speaker.wait", ms=int((time.monotonic() - t0) * 1000), ready=bool(self.sink()))
        return self.sink()


def resample(audio, sr, to):
    if sr == to:
        return audio
    n = int(len(audio) * to / sr)
    return np.interp(np.linspace(0, len(audio) - 1, n), np.arange(len(audio)), audio).astype(np.float32)


class Voice:
    def __init__(self, cfg, log=lambda *a: None, prewarm=False):
        self.cfg = cfg
        self.prewarm = prewarm         # long-running Jarvis only: one-shot runs exit mid-render otherwise
        self.log = log
        self.engines = Engines()
        self._proc = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._warmed = None
        self.ducker = Ducker()
        self.speaking = False
        self.overrides = {}            # audition / preview: {"voice", "preset", "pitch", "speed"}
        self.speaker = Speaker(cfg, log)

    # ── settings ──
    def _setting(self, key, cfg_key, default):
        if key in self.overrides:
            return self.overrides[key]
        try:
            return self.cfg[cfg_key]
        except KeyError:
            return default

    def params(self):
        name = self._setting("voice", "jarvisVoice", "bm_george")
        fx = effects.preset(self._setting("preset", "jarvisEffect", "AUTO"))
        speed = float(self._setting("speed", "jarvisSpeed", 1.0) or 1.0) * float(fx.get("speed", 1.0))
        pitch = float(self._setting("pitch", "jarvisPitch", 0.0) or 0.0) + float(fx.get("pitch", 0.0))
        return name, fx, speed, pitch

    # ── rendering ──
    def render(self, text, params=None):
        """One sentence → (processed float32 audio, sample rate). Kokoro failing falls back to piper."""
        name, fx, speed, pitch = params or self.params()
        cached = len(text.split()) <= CACHE_MAX_WORDS
        if cached:
            key = hashlib.sha1(json.dumps([name, round(speed, 3), round(pitch, 2), fx, text, KOKORO_MODEL.name],
                                          sort_keys=True).encode()).hexdigest()[:20]
            hit = next(CACHE_DIR.glob(f"{key}-*.npy"), None)
            if hit:
                try:
                    return np.load(hit), int(hit.stem.rsplit("-", 1)[1])
                except (OSError, ValueError):
                    pass
        try:
            audio, sr = self.engines.synth(name, text, speed)
        except Exception as e:
            self.log(f"JARVIS: {name} failed ({type(e).__name__}: {e}), using piper")
            audio, sr = self.engines.synth(FALLBACK_PIPER, text, speed)
            cached = False
        out = effects.apply(audio, sr, fx, pitch)
        if cached:
            try:
                CACHE_DIR.mkdir(parents=True, exist_ok=True)
                np.save(CACHE_DIR / f"{key}-{sr}.npy", out)
                self._prune_cache()
            except OSError:
                pass
        return out, sr

    def _prune_cache(self):
        files = sorted(CACHE_DIR.glob("*.npy"), key=lambda f: f.stat().st_mtime)
        for f in files[:-CACHE_MAX_FILES]:
            f.unlink(missing_ok=True)

    def warm(self):
        """Load the model now and pre-render the stock phrases (in the background)."""
        params = self.params()
        sig = json.dumps(params, sort_keys=True)
        if sig == self._warmed:
            return
        self._warmed = sig

        def run():
            for t in COMMON:
                try:
                    self.render(clean(t), params)
                except Exception as e:
                    self.log(f"JARVIS: voice warm-up failed: {e}")
                    return
        threading.Thread(target=run, daemon=True).start()

    # ── playback ──
    def speak(self, text):
        """Speak text, blocking. Returns False if stop() cut it short."""
        parts = sentences(clean(text))
        if not parts:
            return True
        with self._lock:
            self._stop.clear()
            params = self.params()
            q = queue.Queue()

            def produce():
                for s in parts:
                    if self._stop.is_set():
                        break
                    try:
                        q.put(self.render(s, params))
                    except Exception as e:
                        self.log(f"JARVIS: speech failed: {e}")
                        break
                q.put(None)
            threading.Thread(target=produce, daemon=True).start()

            trace.t("tts", sentences=len(parts), voice=params[0])
            target = self.speaker.target()
            first = q.get()
            if first is None:
                return True
            audio, rate = first
            self.speaking = True
            duck = self.cfg["jarvisDuck"]
            if duck:
                self.ducker.duck()
            self._proc = subprocess.Popen(
                ["pw-play", "--raw", "--rate", str(rate), "--channels", "1", "--format", "f32",
                 "--media-role", "Assistant", "-P", "media.name=Jarvis"]
                + (["--target", target] if target else []) + ["-"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            trace.t("tts.audio", sink=target or "default", since_speech_end=trace.since("speech_end"))
            try:
                while audio is not None and not self._stop.is_set():
                    self._proc.stdin.write(audio.tobytes())
                    self._proc.stdin.flush()
                    nxt = q.get()
                    if nxt is None:
                        break
                    audio, sr = nxt
                    audio = resample(audio, sr, rate)
                self._proc.stdin.close()
                while self._proc.poll() is None and not self._stop.wait(0.05):
                    pass
            except (BrokenPipeError, OSError):
                pass
            finally:
                if self._proc.poll() is None:
                    self._proc.kill()
                self._proc.wait()
                if duck:
                    self.ducker.restore()
                self.speaking = False
                if self.prewarm:
                    self.warm()    # re-render the stock phrases if the voice settings changed
            return not self._stop.is_set()

    def stop(self):
        self._stop.set()
        p = self._proc
        if p and p.poll() is None:
            p.kill()
