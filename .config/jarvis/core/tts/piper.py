"""piper (local, CPU): the fallback engine. Voice names by model file in ~/.local/share/jarvis/voices, with a
speaker for multi-speaker models (en_GB-semaine-medium:obadiah)."""
import json
import threading

import numpy as np

from . import Engine
from ..config import VOICES_DIR
from .kokoro import KOKORO_MODEL

FALLBACK = "en_GB-alan-medium"


class Piper(Engine):
    id = "piper"
    priority = 90                      # anything nobody else claims, if it's a model on disk

    def __init__(self):
        self._voices = {}
        self._lock = threading.Lock()

    def available(self):
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return True

    def handles(self, voice):
        model = (voice or "").partition(":")[0]
        return bool(model) and "/" not in model and (VOICES_DIR / f"{model}.onnx").exists()

    def voices(self):
        out = []
        for f in sorted(VOICES_DIR.glob("*.onnx")):
            try:
                spk = json.loads(f.with_suffix(".onnx.json").read_text()).get("speaker_id_map") or {}
            except (OSError, ValueError):
                spk = {}
            out += [f"{f.stem}:{s}" for s in spk] if len(spk) > 1 else [f.stem]
        return out

    def model(self, name):
        with self._lock:
            if name not in self._voices:
                from piper import PiperVoice
                path = VOICES_DIR / f"{name}.onnx"
                if not path.exists():
                    path = VOICES_DIR / f"{FALLBACK}.onnx"
                self._voices[name] = PiperVoice.load(str(path))
            return self._voices[name]

    def synth(self, voice, text, speed):
        from piper import SynthesisConfig
        model, _, speaker = voice.partition(":")
        v = self.model(model)
        sid = (v.config.speaker_id_map or {}).get(speaker) if speaker else None
        # volume 0.7: piper hits full scale and clips; lower noise scales cut its vocoder buzz
        syn = SynthesisConfig(speaker_id=sid, length_scale=1.0 / max(0.5, min(2.0, speed)),
                              volume=0.7, noise_scale=0.4, noise_w_scale=0.6)
        audio = np.concatenate([c.audio_float_array for c in v.synthesize(text, syn_config=syn)] or [np.zeros(1)])
        return audio.astype(np.float32), v.config.sample_rate

    def cache_tag(self):
        return KOKORO_MODEL.name           # the cache key has always carried the Kokoro model's name


ENGINE = Piper
