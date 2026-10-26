"""
Jarvis's voice. Kokoro (local, ONNX on CPU) by default, piper as the fallback,
then the effect chain (effects.py), streamed into pw-play.

Every line goes through speech.normalize first (times, dates, numbers, units,
symbols → words), then plays as an Utterance: sentences can be added while it's
already talking (Claude's reply streams in sentence by sentence), each is
rendered in the background and written to one pw-play stream. The stream is
opened as soon as Jarvis knows what you said, so Bluetooth is awake and the
first syllable isn't clipped. A long first sentence is split at its first comma
so the first sound comes sooner. Short stock lines are cached on disk.

Voice names: Kokoro voices as-is (bm_george, bm_fable…); piper voices by model
file, with a speaker for multi-speaker models (en_GB-semaine-medium:obadiah).

Output: the default sink, except when it isn't headphones and a Bluetooth speaker
is set (Settings → JARVIS → Speaker): then Jarvis connects to it when it hears
"Hey Jarvis" and plays only its own voice there. If it isn't connected within
1.5 s of a reply being ready, that reply plays on the laptop speakers instead.
Other audio (Spotify, browsers) is turned down while Jarvis listens and talks.

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

from . import effects, speech, trace
from .config import DATA_DIR, VOICES_DIR

KOKORO_DIR = DATA_DIR / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.int8.onnx"   # int8: ~5× real time on CPU, 300 MB; fp32 file is 40% slower
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"
FALLBACK_PIPER = "en_GB-alan-medium"
CACHE_DIR = DATA_DIR / "tts-cache"
CACHE_MAX_WORDS = 6        # sentences this short get cached on disk
CACHE_MAX_FILES = 400
COMMON = ["Right away, sir.", "Done, sir.", "Very well, sir.", "Very good, sir.", "Online.",
          "You're welcome, sir.", "Goodnight, sir.", "Your timer is done, sir.", "Nothing's playing, sir.",
          "Sorry sir, I didn't catch that.", "I'm having trouble reaching the network, sir."]

RATE = 24000               # the output stream's rate (Kokoro's); piper audio is resampled to it
DUCK_SPEAK = 0.3           # other audio while Jarvis talks (fraction of its volume)
DUCK_LISTEN = 0.2          # ...and while it listens, so a song isn't taken for a command
SPEAKER_WAIT_S = 1.5       # Bluetooth speaker not ready by then → laptop speakers for this reply
COMMA_GAP_S = 0.06         # pause where a long first sentence was split at its comma
JARVIS_STREAMS = ("Jarvis", "Jarvis chime")
# WirePlumber remembers a stream's volume per app and applies it to the next one. Ducking once caught a
# pw-play stream (the timer alarm) and saved ~0 % for "pw-play", which silenced every Jarvis line after.
# So Jarvis's streams opt out of that memory, and the ducker leaves pw-play streams alone.
NO_RESTORE = "state.restore-props = false"


def clean(text):
    return speech.normalize(text)


def first_split(parts):
    """Split a long first sentence at its first comma: ['A, b c d.'] → ['A,', 'b c d.']."""
    if not parts or len(parts[0].split()) < 9:
        return parts, False
    m = re.search(r",\s", parts[0])
    if not m or len(parts[0][:m.start()].split()) < 3 or len(parts[0][m.end():].split()) < 3:
        return parts, False
    return [parts[0][:m.start() + 1], parts[0][m.end():]] + parts[1:], True


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


def chime_audio(kind):
    """Soft chimes from the HUD's own notes (unlock.wav is E5 / B5 / E6). listen: rising, error: falling."""
    notes = {"listen": [(659.3, 0.0), (987.8, 0.07)], "error": [(493.9, 0.0), (329.6, 0.11)]}[kind]
    dur = 0.34 if kind == "listen" else 0.42
    t = np.arange(int(RATE * dur)) / RATE
    out = np.zeros_like(t)
    for f, start in notes:
        tt = np.clip(t - start, 0, None)
        env = (t >= start) * (1 - np.exp(-tt / 0.006)) * np.exp(-tt / (0.09 if kind == "listen" else 0.12))
        out += env * (np.sin(2 * np.pi * f * tt) + 0.25 * np.sin(4 * np.pi * f * tt))
    if kind == "listen":    # faint E6 shimmer
        out += 0.12 * np.exp(-np.clip(t - 0.07, 0, None) / 0.15) * (t >= 0.07) * np.sin(2 * np.pi * 1318.5 * t)
    out = 0.22 * out / np.abs(out).max()
    return np.concatenate([np.zeros(int(RATE * 0.12)), out]).astype(np.float32)   # lead-in: a waking BT sink drops the start


class Ducker:
    """Turns other apps' audio streams down (pactl, so any app: Spotify, browsers) and back up.
    What it turned down is also written to a file, so if Jarvis is stopped mid-reply (a HUD
    reload restarts it) the next start puts the music back (restore_leftover)."""

    FILE = trace.STATE_DIR / "ducked.json"

    def __init__(self):
        self.saved = {}
        self._lock = threading.Lock()

    def _write(self):
        try:
            if self.saved:
                self.FILE.parent.mkdir(parents=True, exist_ok=True)
                self.FILE.write_text(json.dumps({str(k): v for k, v in self.saved.items()}))
            else:
                self.FILE.unlink(missing_ok=True)
        except OSError:
            pass

    def restore_leftover(self):
        """At startup: volumes a previous run turned down and never restored."""
        try:
            left = json.loads(self.FILE.read_text())
        except (OSError, ValueError):
            return
        with self._lock:
            self.saved = {int(k): v for k, v in left.items()}
        self.restore()

    @property
    def held(self):
        return bool(self.saved)

    def duck(self, level):
        """False if already ducked (someone else will restore)."""
        with self._lock:
            if self.saved:
                return False
            try:
                inputs = json.loads(subprocess.run(["pactl", "-f", "json", "list", "sink-inputs"], capture_output=True,
                                                   text=True, timeout=2).stdout or "[]")
            except (OSError, ValueError, subprocess.TimeoutExpired):
                return False
            for si in inputs:
                props = si.get("properties", {})
                if si.get("corked") or props.get("media.name") in JARVIS_STREAMS or props.get("application.name") == "pw-play":
                    continue
                vols = [v["value"] for v in si.get("volume", {}).values()]
                if not vols:
                    continue
                self.saved[si["index"]] = vols
                subprocess.run(["pactl", "set-sink-input-volume", str(si["index"])] + [str(int(v * level)) for v in vols],
                               capture_output=True, timeout=2)
            self._write()
            return True

    def restore(self):
        with self._lock:
            for idx, vols in self.saved.items():
                subprocess.run(["pactl", "set-sink-input-volume", str(idx)] + [str(v) for v in vols],
                               capture_output=True, timeout=2)
            self.saved = {}
            self._write()


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
        self._wanted = (0.0, False)

    @property
    def mac(self):
        try:
            return (self.cfg["jarvisSpeaker"] or "").strip()
        except KeyError:
            return ""

    def wanted(self):
        """Speaker set and not on headphones (checked at most every 3 s)."""
        at, val = self._wanted
        if time.monotonic() - at > 3:
            val = bool(self.mac) and not effects.on_headphones()
            self._wanted = (time.monotonic(), val)
        return val

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

    def target(self, wait=SPEAKER_WAIT_S):
        """(sink for pw-play or None for the default output, fell_back). Waits up to `wait`
        for a connect in progress; if the speaker isn't there by then, this reply goes to the
        laptop speakers (the connect carries on for the next one)."""
        if not self.wanted():
            return None, False
        self.prepare()
        if self._thread and self._thread.is_alive():
            t0 = time.monotonic()
            self._thread.join(wait)
            trace.t("speaker.wait", ms=int((time.monotonic() - t0) * 1000), ready=bool(self.sink()))
        s = self.sink()
        if s:
            return s, False
        return laptop_sink(), True

    def now(self):
        """Sink for a sound that can't wait (the chime): the speaker if it's already up."""
        return (self.sink() if self.wanted() else None) or None


def laptop_sink():
    return next((s for s in sink_names() if "Speaker__sink" in s or ("alsa_output" in s and "speaker" in s.lower())), None)


class Utterance:
    """One spoken reply. add() sentences any time (even while it's talking), finish()
    when there's no more, wait() until it's done. Opens the output stream right away."""

    def __init__(self, voice):
        self.v = voice
        self.texts = queue.Queue()
        self.audio = queue.Queue()
        self.stopped = threading.Event()
        self.done = threading.Event()
        self.started = False          # any audio written yet
        self.fell_back = False        # speaker unreachable → laptop speakers
        self.n_added = 0
        self.params = voice.params()
        self.proc = None
        threading.Thread(target=self._produce, daemon=True).start()
        threading.Thread(target=self._play, daemon=True).start()

    def add(self, text):
        parts = speech.sentences(speech.normalize(text))
        split = False
        if self.n_added == 0:
            parts, split = first_split(parts)
        for i, p in enumerate(parts):
            self.texts.put((p, COMMA_GAP_S if split and i == 0 else None))
        self.n_added += len(parts)

    def finish(self):
        self.texts.put(None)

    def stop(self):
        self.stopped.set()
        p = self.proc
        if p and p.poll() is None:
            p.kill()

    def wait(self, timeout=None):
        """True if it finished, False if stopped (or still going after timeout)."""
        self.done.wait(timeout)
        return self.done.is_set() and not self.stopped.is_set()

    def _produce(self):
        while not self.stopped.is_set():
            item = self.texts.get()
            if item is None:
                break
            text, gap = item
            try:
                audio, sr = self.v.render(text, self.params)
                audio = resample(audio, sr, RATE)
                if gap is not None:      # comma split: shorter pause than a full stop
                    audio = audio[:max(0, len(audio) - int((effects.TAIL_S - gap) * RATE))]
                self.audio.put(audio)
            except Exception as e:
                self.v.log(f"JARVIS: speech failed: {e}")
                trace.t("error", where="tts", err=f"{type(e).__name__}: {e}")
        self.audio.put(None)

    def _play(self):
        ducked = False
        try:
            target, self.fell_back = self.v.speaker.target()
            if self.fell_back:
                trace.t("speaker.fallback", sink=target or "default")
            if self.stopped.is_set():
                return
            self.proc = self.v.open_stream(target)
            first = True
            while not self.stopped.is_set():
                audio = self.audio.get()
                if audio is None:
                    break
                if first:
                    first = False
                    self.started = True
                    trace.t("tts.audio", sink=target or "default", since_speech_end=trace.since("speech_end"))
                    if self.v.cfg["jarvisDuck"]:
                        ducked = self.v.ducker.duck(DUCK_SPEAK)
                self.proc.stdin.write((audio * self.v.volume()).astype(np.float32).tobytes())
                self.proc.stdin.flush()
            self.proc.stdin.close()
            while self.proc.poll() is None and not self.stopped.wait(0.03):
                pass
        except (BrokenPipeError, OSError, ValueError):
            pass
        finally:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
            if self.proc:
                self.proc.wait()
            if ducked:
                self.v.ducker.restore()
            self.done.set()
            if self.v.prewarm:
                self.v.warm()    # re-render the stock phrases if the voice settings changed


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
        self._lock = threading.Lock()
        self._warmed = None
        self._current = None           # the Utterance playing now
        self._chimes = {}
        self.ducker = Ducker()
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
    def volume(self):
        """Settings → JARVIS → Volume (read per sentence, so a change applies straight away)."""
        try:
            return max(0.05, min(1.0, float(self._setting("volume", "jarvisVolume", 0.7))))
        except (TypeError, ValueError):
            return 0.7

    def open_stream(self, target=None):
        return subprocess.Popen(
            ["pw-play", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "f32",
             "--media-role", "Assistant", "-P", f'{{ media.name = "Jarvis" {NO_RESTORE} }}']
            + (["--target", target] if target else []) + ["-"],
            stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def utterance(self):
        """Start a reply now (opens the output); add sentences to it as they come."""
        u = Utterance(self)
        with self._lock:
            self._current = u
        return u

    def speak(self, text):
        """Speak text, blocking. Returns False if stop() cut it short."""
        u = self.utterance()
        u.add(text)
        u.finish()
        return u.wait()

    def chime(self, kind="listen"):
        """Non-blocking: the soft "I'm listening" (or error) tone."""
        target = self.speaker.now()

        def play():
            try:
                p = subprocess.Popen(["pw-play", "--raw", "--rate", str(RATE), "--channels", "1", "--format", "f32",
                                      "--media-role", "Notification", "-P", f'{{ media.name = "Jarvis chime" {NO_RESTORE} }}']
                                     + (["--target", target] if target else []) + ["-"],
                                     stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                p.communicate((self._chimes.setdefault(kind, chime_audio(kind)) * self.volume()).astype(np.float32).tobytes(), timeout=5)
            except (OSError, subprocess.TimeoutExpired):
                pass
        threading.Thread(target=play, daemon=True).start()

    @property
    def speaking(self):
        u = self._current
        return bool(u and not u.done.is_set())

    def stop(self):
        u = self._current
        if u:
            u.stop()
