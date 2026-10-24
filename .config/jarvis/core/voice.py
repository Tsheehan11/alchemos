"""
Jarvis's voice: piper (local neural TTS, British male by default) streamed
straight into pw-play, so the first words start ~0.2 s after a reply arrives.
Music playing through MPRIS (Spotify etc.) is ducked while it talks.
"""
import re
import subprocess
import threading

from .config import VOICES_DIR

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


class Voice:
    def __init__(self, cfg):
        self.cfg = cfg
        self._voice = None
        self._voice_name = None
        self._proc = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.ducker = Ducker()
        self.speaking = False

    def _load(self):
        name = self.cfg["jarvisVoice"]
        if self._voice is None or name != self._voice_name:
            from piper import PiperVoice
            path = VOICES_DIR / f"{name}.onnx"
            if not path.exists():
                path = VOICES_DIR / "en_GB-alan-medium.onnx"
            self._voice = PiperVoice.load(str(path))
            self._voice_name = name
        return self._voice

    def warm(self):
        self._load()

    def speak(self, text):
        """Speak text, blocking. Returns False if stop() cut it short."""
        text = clean(text)
        if not text:
            return True
        from piper import SynthesisConfig
        with self._lock:
            self._stop.clear()
            voice = self._load()
            speed = max(0.5, min(2.0, float(self.cfg["jarvisSpeed"] or 1.0)))
            syn = SynthesisConfig(length_scale=1.0 / speed)
            self.speaking = True
            duck = self.cfg["jarvisDuck"]
            if duck:
                self.ducker.duck()
            self._proc = subprocess.Popen(
                ["pw-play", "--raw", "--rate", str(voice.config.sample_rate), "--channels", "1",
                 "--format", "s16", "--media-role", "Assistant", "-P", "media.name=Jarvis", "-"],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                for chunk in voice.synthesize(text, syn_config=syn):
                    if self._stop.is_set():
                        break
                    self._proc.stdin.write(chunk.audio_int16_bytes)
                    self._proc.stdin.flush()
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
            return not self._stop.is_set()

    def stop(self):
        self._stop.set()
        p = self._proc
        if p and p.poll() is None:
            p.kill()
