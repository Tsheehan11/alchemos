"""Kokoro (kokoro-onnx, local, CPU): the default engine. Voice names as Kokoro has them (bm_george, af_nicole…).
Models: kokoro-v1.0.int8.onnx + voices-v1.0.bin from github.com/thewh1teagle/kokoro-onnx releases
(model-files-v1.0) → ~/.local/share/orrin/kokoro/"""
import re
import threading

import numpy as np

from . import Engine
from ..config import DATA_DIR

KOKORO_DIR = DATA_DIR / "kokoro"
KOKORO_MODEL = KOKORO_DIR / "kokoro-v1.0.int8.onnx"   # int8: ~5× real time on CPU, 300 MB; fp32 file is 40% slower
KOKORO_VOICES = KOKORO_DIR / "voices-v1.0.bin"


class Kokoro(Engine):
    id = "kokoro"
    priority = 10

    def __init__(self):
        self._model = None
        self._lock = threading.Lock()

    def available(self):
        try:
            import kokoro_onnx  # noqa: F401
        except ImportError:
            return False
        return KOKORO_MODEL.exists() and KOKORO_VOICES.exists()

    def handles(self, voice):
        return bool(re.match(r"^[abefhijpz][fm]_", voice or ""))

    @property
    def female(self):
        return [v for v in self.voices() if v[1:2] == "f"]

    def voices(self):
        try:
            return sorted(np.load(KOKORO_VOICES).files)
        except Exception:
            return []

    def model(self):
        with self._lock:
            if self._model is None:
                import onnxruntime as ort
                from kokoro_onnx import Kokoro as K
                # 8 threads, no spin-waiting: ~14% slower than the default, a third of the CPU (13 s → 4 s per sentence)
                so = ort.SessionOptions()
                so.intra_op_num_threads = 8
                so.add_session_config_entry("session.intra_op.allow_spinning", "0")
                sess = ort.InferenceSession(str(KOKORO_MODEL), so, providers=["CPUExecutionProvider"])
                self._model = K.from_session(sess, str(KOKORO_VOICES))
            return self._model

    def synth(self, voice, text, speed):
        lang = "en-gb" if voice.startswith("b") else "en-us"
        audio, sr = self.model().create(text, voice=voice, speed=max(0.5, min(2.0, speed)), lang=lang)
        return np.asarray(audio, np.float32), sr

    def cache_tag(self):
        return KOKORO_MODEL.name


ENGINE = Kokoro
