"""Pocket TTS worker: runs in its own venv (~/.local/share/jarvis/pocket-venv, PyTorch), started by core/tts/pocket.py.
Not an engine module (the leading underscore keeps core/tts discovery away from it: it imports torch).

Protocol, one request at a time over stdin/stdout:
  → {"voice": "orrin_2", "text": "Good evening, sir."}\\n
  ← {"ok": true, "sr": 24000, "n": 41280}\\n  then n float32 samples (little-endian, mono)
  ← {"ok": false, "error": "..."}\\n
A voice is a state exported to ~/.local/share/jarvis/voices/pocket/<name>.safetensors, or one of Pocket's
built-in voices (peter_yearsley, anna…). The model loads once; voice states are kept after first use.

Threads: Pocket sets torch to 1 intra-op thread when imported, and that is the right setting (a generation
thread + a decoder thread ≈ 1.6 cores, real time ×3.7). Raising it after the import is what made the lab
use ~15 cores for the same speed (tts-lab/pocket_threads.jsonl), so nothing here touches torch threads.

  python _pocket_worker.py                      serve (what the engine runs)
  python _pocket_worker.py --export NAME WAV    clone WAV once → voices/pocket/NAME.safetensors
                                                (needs the gated kyutai/pocket-tts weights: hf auth login + accept the terms)
"""
import json
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
VOICE_DIR = Path(os.path.expanduser("~/.local/share/jarvis/voices/pocket"))


def main():
    if sys.argv[1:2] == ["--export"]:
        name, wav = sys.argv[2], sys.argv[3]
        from pocket_tts import TTSModel
        from pocket_tts.models.model_state import export_model_state
        m = TTSModel.load_model()
        if not m.has_voice_cloning:
            sys.exit("no voice-cloning weights: hf auth login, accept the terms at huggingface.co/kyutai/pocket-tts")
        VOICE_DIR.mkdir(parents=True, exist_ok=True)
        export_model_state(m.get_state_for_audio_prompt(Path(wav)), VOICE_DIR / f"{name}.safetensors")
        print(VOICE_DIR / f"{name}.safetensors")
        return

    os.environ.setdefault("HF_HUB_OFFLINE", "1")          # serving never touches the network: weights are cached
    logging.disable(logging.WARNING)
    out = sys.stdout.buffer
    sys.stdout = sys.stderr                                # stray prints must not corrupt the audio stream
    import numpy as np
    from pocket_tts import TTSModel
    from pocket_tts.utils.utils import _ORIGINS_OF_PREDEFINED_VOICES as BUILTIN
    model = TTSModel.load_model()
    states = {}
    out.write(json.dumps({"ready": True, "sr": model.sample_rate}).encode() + b"\n")
    out.flush()
    for line in sys.stdin.buffer:
        try:
            req = json.loads(line)
            voice = req["voice"]
            if voice not in states:
                f = VOICE_DIR / f"{voice}.safetensors"
                if not f.exists() and voice not in BUILTIN:
                    raise ValueError(f"unknown Pocket voice {voice!r} (no {f.name}, not a built-in)")
                states[voice] = model.get_state_for_audio_prompt(f if f.exists() else voice)
            chunks = [c.numpy().reshape(-1) for c in model.generate_audio_stream(states[voice], req["text"])]
            audio = np.concatenate(chunks).astype("<f4") if chunks else np.zeros(0, "<f4")
            out.write(json.dumps({"ok": True, "sr": model.sample_rate, "n": int(audio.size)}).encode() + b"\n")
            out.write(audio.tobytes())
        except Exception as e:
            out.write(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}).encode() + b"\n")
        out.flush()


if __name__ == "__main__":
    main()
