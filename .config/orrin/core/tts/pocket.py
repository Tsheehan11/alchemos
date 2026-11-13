"""Pocket TTS (Kyutai, CC-BY-4.0; local, CPU): Orrin's and Selene's voices. Names are "pocket/<voice>":
the designed voices cloned once into ~/.local/share/orrin/voices/pocket/<voice>.safetensors (orrin_2, selene_1),
or a Pocket built-in (pocket/peter_yearsley, pocket/anna…).

Pocket needs PyTorch, which the Orrin venv doesn't carry, so it runs in its own venv as a worker process
(core/tts/_pocket_worker.py): started on first use, kept loaded, one request at a time, restarted if it dies or
stalls. Any failure raises, and core/voice.py falls back to piper as it does for every engine.

Setup (outside the repo):
  uv venv --python 3.11 ~/.local/share/orrin/pocket-venv
  uv pip install --python ~/.local/share/orrin/pocket-venv/bin/python pocket-tts==4.0.1 \\
      --extra-index-url https://download.pytorch.org/whl/cpu --index-strategy unsafe-best-match
  hf auth login   (then accept the terms at huggingface.co/kyutai/pocket-tts: only cloning needs them)
  ~/.local/share/orrin/pocket-venv/bin/python -I ~/.config/orrin/core/tts/_pocket_worker.py \\
      --export orrin_2 ~/.local/share/orrin/voices/pocket/orrin_2.wav     (and selene_1)

Speed: Pocket has no rate control, so a speed other than 1 is a pitch-preserving time stretch (pedalboard)."""
import json
import os
import subprocess
import threading
from pathlib import Path

import numpy as np

from . import Engine
from ..config import DATA_DIR

VENV_PY = DATA_DIR / "pocket-venv" / "bin" / "python"
WORKER = Path(__file__).with_name("_pocket_worker.py")
VOICE_DIR = DATA_DIR / "voices" / "pocket"
BUILTIN = ("peter_yearsley", "stuart_bell", "charles", "george", "michael", "paul", "bill_boerst",
           "anna", "vera", "fantine", "alba", "eve", "mary", "jane", "cosette", "caro_davy")
FEMALE = ("selene_1", "anna", "vera", "fantine", "alba", "eve", "mary", "jane", "cosette", "caro_davy")
START_TIMEOUT_S = 90      # model load (cold disk) before the first answer
SYNTH_TIMEOUT_S = 30      # one sentence; Pocket runs ~3-4x real time


class Pocket(Engine):
    id = "pocket"
    priority = 30
    female = FEMALE

    def __init__(self, python=None, worker=None, env=None):
        self.python = Path(python) if python else VENV_PY
        self.worker = Path(worker) if worker else WORKER
        self.env = env
        self._proc = None
        self._lock = threading.Lock()

    def available(self):
        return self.python.exists() and self.worker.exists()

    def voices(self):
        designed = sorted(p.stem for p in VOICE_DIR.glob("*.safetensors")) if VOICE_DIR.is_dir() else []
        return designed + [v for v in BUILTIN if v not in designed]

    def cache_tag(self):
        return "pocket-4.0.1"

    # ── worker ──
    def _read_line(self, p, timeout):
        box = []
        t = threading.Thread(target=lambda: box.append(p.stdout.readline()), daemon=True)
        t.start()
        t.join(timeout)
        if not box or not box[0]:
            raise RuntimeError("pocket worker stalled" if not box else "pocket worker exited")
        return json.loads(box[0])

    def _read_exact(self, p, n, timeout):
        box = []
        t = threading.Thread(target=lambda: box.append(p.stdout.read(n)), daemon=True)
        t.start()
        t.join(timeout)
        if not box or len(box[0]) != n:
            raise RuntimeError("pocket worker cut off mid-audio")
        return box[0]

    def _start(self):
        env = dict(os.environ if self.env is None else self.env)
        env.setdefault("HF_HUB_OFFLINE", "1")
        env.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
        p = subprocess.Popen([str(self.python), "-I", str(self.worker)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, env=env, preexec_fn=lambda: os.nice(10))
        try:
            hello = self._read_line(p, START_TIMEOUT_S)
            if not hello.get("ready"):
                raise RuntimeError(f"pocket worker: {hello}")
        except Exception:
            self._kill(p)
            raise
        return p

    @staticmethod
    def _kill(p):
        try:
            p.kill()
            p.wait(timeout=2)
        except Exception:
            pass

    def close(self):
        with self._lock:
            if self._proc:
                self._kill(self._proc)
                self._proc = None

    def synth(self, voice, text, speed):
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                self._proc = self._start()
            p = self._proc
            try:
                p.stdin.write(json.dumps({"voice": voice, "text": text}).encode() + b"\n")
                p.stdin.flush()
                head = self._read_line(p, SYNTH_TIMEOUT_S)
                if head.get("ok"):
                    audio = np.frombuffer(self._read_exact(p, 4 * int(head["n"]), SYNTH_TIMEOUT_S), "<f4").astype(np.float32)
                    sr = int(head["sr"])
            except (OSError, ValueError, RuntimeError):      # dead, stalled or garbled: start afresh next time
                self._kill(p)
                self._proc = None
                raise
            if not head.get("ok"):                            # the worker is fine, this request wasn't (unknown voice…)
                raise RuntimeError(head.get("error", "pocket worker error"))
        if abs(speed - 1.0) > 0.01 and len(audio):
            import pedalboard
            audio = pedalboard.time_stretch(audio[None, :], sr, stretch_factor=max(0.5, min(2.0, speed)))[0].astype(np.float32)
        return audio, sr


ENGINE = Pocket
