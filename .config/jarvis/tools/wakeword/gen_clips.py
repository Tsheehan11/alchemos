#!/usr/bin/env python3
"""
Synthetic clips for openWakeWord's training pipeline, made with the TTS engines Jarvis already
runs (no pickled models): piper's en_US-libritts_r-medium ONNX voice (904 LibriTTS-R speakers,
the same speaker set piper-sample-generator uses) for ~75 %, Kokoro's English voices and random
blends of two of them (new "speakers") for the rest. Varied speed and noise, a few prosody variants.

Writes 16 kHz mono WAVs into $W/out/hey_friday/{positive,negative}_{train,test}; train.py's
--generate_clips then sees enough clips and skips its own generator, and --augment_clips /
--train_model run as usual. Held-out speakers: test clips use speakers / voices train never sees.

Run with Jarvis's venv (it has piper + kokoro-onnx):
  ~/.config/jarvis/.venv/bin/python tools/wakeword/gen_clips.py [--n 8000 --n-val 2000 --workers 6]
"""
import argparse
import os
import random
import sys
import time
import uuid
import wave
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
W = Path(os.environ.get("WAKE_TRAIN_DIR", Path.home() / ".local/share/jarvis/wake-train"))
OUT = W / "out/hey_friday"
LIBRITTS = W / "data/piper/en_US-libritts_r-medium.onnx"

POSITIVE = ["hey friday", "hey friday", "hey friday", "hey, friday", "hey friday!", "hey friday?", "hey friday."]


def negatives():
    import yaml
    cfg = yaml.safe_load((HERE / "hey_friday.yml").read_text())
    return cfg["custom_negative_phrases"]


def kokoro_names():
    from core.voice import kokoro_voices
    return [v for v in kokoro_voices() if v[:2] in ("af", "am", "bf", "bm")]


_k = _p = None


def _engines():
    global _k, _p
    if _k is None:
        import onnxruntime as ort
        from kokoro_onnx import Kokoro
        from piper import PiperVoice
        from core.voice import KOKORO_MODEL, KOKORO_VOICES
        so = ort.SessionOptions()
        so.intra_op_num_threads = 2
        so.add_session_config_entry("session.intra_op.allow_spinning", "0")
        _k = Kokoro.from_session(ort.InferenceSession(str(KOKORO_MODEL), so, providers=["CPUExecutionProvider"]),
                                 str(KOKORO_VOICES))
        _p = PiperVoice.load(str(LIBRITTS))
    return _k, _p


def to16k(a, sr):
    if sr == 16000:
        return a
    n = int(len(a) * 16000 / sr)
    return np.interp(np.linspace(0, len(a) - 1, n), np.arange(len(a)), a).astype(np.float32)


def render(job):
    """job: (path, text, engine, voice spec, speed, seed) → seconds of audio (0 on failure)."""
    path, text, engine, spec, speed, seed = job
    rng = random.Random(seed)
    k, p = _engines()
    try:
        if engine == "piper":
            from piper import SynthesisConfig
            syn = SynthesisConfig(speaker_id=spec, length_scale=1.0 / speed, volume=0.8,
                                  noise_scale=rng.uniform(0.5, 0.9), noise_w_scale=rng.uniform(0.6, 1.0))
            a = np.concatenate([c.audio_float_array for c in p.synthesize(text, syn_config=syn)])
            sr = p.config.sample_rate
        else:
            a_name, b_name, w = spec
            style = k.get_voice_style(a_name) * (1 - w) + k.get_voice_style(b_name) * w if b_name else a_name
            lang = "en-gb" if a_name.startswith("b") else "en-us"
            a, sr = k.create(text, voice=style, speed=speed, lang=lang)
        a = to16k(np.asarray(a, np.float32), sr)
        peak = np.abs(a).max() or 1.0
        a = a / peak * rng.uniform(0.3, 0.9)
        with wave.open(str(path), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
            f.writeframes((a * 32767).astype(np.int16).tobytes())
        return len(a) / 16000
    except Exception as e:
        print(f"clip failed ({engine} {spec}): {e}", flush=True)
        return 0.0


def jobs_for(folder, texts, n, split, rng):
    """split: train speakers = LibriTTS ids not ≡ 0 (mod 7) + 80 % of Kokoro voices; test = the rest."""
    kv = kokoro_names()
    rng_v = random.Random(7)
    kv_test = set(rng_v.sample(kv, max(3, len(kv) // 5)))
    kv_pool = [v for v in kv if (v in kv_test) == (split == "test")]
    lib = [i for i in range(904) if (i % 7 == 0) == (split == "test")]
    folder.mkdir(parents=True, exist_ok=True)
    have = len(list(folder.glob("*.wav")))
    out = []
    for _ in range(max(0, n - have)):
        text = rng.choice(texts)
        speed = rng.uniform(0.8, 1.3)
        if rng.random() < 0.75:
            job = ("piper", rng.choice(lib))
        else:
            a = rng.choice(kv_pool)
            b = rng.choice(kv_pool) if rng.random() < 0.6 else None
            job = ("kokoro", (a, b, rng.uniform(0.2, 0.8) if b else 0.0))
        out.append((folder / (uuid.uuid4().hex + ".wav"), text, job[0], job[1], speed, rng.random()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8000)
    ap.add_argument("--n-val", type=int, default=2000)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if not LIBRITTS.exists():
        sys.exit(f"missing {LIBRITTS} (setup.sh downloads it)")
    rng = random.Random(1234)
    neg = negatives()
    jobs = (jobs_for(OUT / "positive_train", POSITIVE, args.n, "train", rng)
            + jobs_for(OUT / "positive_test", POSITIVE, args.n_val, "test", rng)
            + jobs_for(OUT / "negative_train", neg, args.n, "train", rng)
            + jobs_for(OUT / "negative_test", neg, args.n_val, "test", rng))
    rng.shuffle(jobs)
    t0 = time.time()
    print(f"{len(jobs)} clips to render with {args.workers} workers", flush=True)
    done = secs = 0
    with Pool(args.workers) as pool:
        for s in pool.imap_unordered(render, jobs, chunksize=16):
            done += 1
            secs += s
            if done % 1000 == 0:
                print(f"{done}/{len(jobs)} · {time.time() - t0:.0f} s", flush=True)
    print(f"rendered {done} clips ({secs / 60:.0f} min of audio) in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    main()
