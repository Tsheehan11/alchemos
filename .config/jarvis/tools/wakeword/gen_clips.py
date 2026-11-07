#!/usr/bin/env python3
"""
Synthetic clips for openWakeWord's training pipeline, made with the TTS engines Jarvis already
runs (no pickled models): piper's en_US-libritts_r-medium ONNX voice (904 LibriTTS-R speakers,
the same speaker set piper-sample-generator uses) for ~75 %, Kokoro's English voices and random
blends of two of them (new "speakers") for the rest. Varied speed and noise, a few prosody variants.

Writes 16 kHz mono WAVs into $W/out/<word>/{positive,negative}_{train,test} (counts, phrases, voice
weights and pitch range from words/<word>.yml via wordcfg.py). Held-out speakers: test clips use
speakers / voices train never sees. Resumable: each folder is topped up to its count, and a clip is
written under a .tmp name and renamed, so a crash never leaves a truncated WAV behind.

Run with Jarvis's venv (it has piper + kokoro-onnx):
  ~/.config/jarvis/.venv/bin/python tools/wakeword/gen_clips.py --word hey_orrin [--workers 12]
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
sys.path.insert(0, str(HERE))
import wordcfg  # noqa: E402

W = wordcfg.W
LIBRITTS = W / "data/piper/en_US-libritts_r-medium.onnx"


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
    """job: (path, text, engine, voice spec, speed, pitch, seed) → seconds of audio (0 on failure).
    pitch: resample factor (> 1 = higher and shorter, formants move with it, like a smaller speaker)."""
    path, text, engine, spec, speed, pitch, seed = job
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
        a = to16k(np.asarray(a, np.float32), int(round(sr * pitch)))
        peak = np.abs(a).max() or 1.0
        a = a / peak * rng.uniform(0.3, 0.9)
        tmp = path.with_suffix(".tmp")
        with wave.open(str(tmp), "wb") as f:
            f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
            f.writeframes((a * 32767).astype(np.int16).tobytes())
        os.replace(tmp, path)
        return len(a) / 16000
    except Exception as e:
        print(f"clip failed ({engine} {spec}): {e}", flush=True)
        return 0.0


def jobs_for(folder, texts, n, split, rng, cfg):
    """split: train speakers = LibriTTS ids not ≡ 0 (mod 7) + 80 % of Kokoro voices; test = the rest.
    The favourite voices (his picks) always train and get favourite_share of the Kokoro clips."""
    kv = kokoro_names()
    fav = [v for v in cfg.get("favourite_voices", []) if v in kv]
    rng_v = random.Random(7)
    rest = [v for v in kv if v not in fav]
    kv_test = set(rng_v.sample(rest, max(3, len(rest) // 5)))
    kv_pool = [v for v in kv if (v in kv_test) == (split == "test")]
    fav = fav if split == "train" else []
    k_share, f_share, p_rng = cfg.get("kokoro_share", 0.25), cfg.get("favourite_share", 0.0), cfg.get("pitch_range", 0.0)
    lib = [i for i in range(904) if (i % 7 == 0) == (split == "test")]
    folder.mkdir(parents=True, exist_ok=True)
    for t in folder.glob("*.tmp"):
        t.unlink()
    have = len(list(folder.glob("*.wav")))
    out = []
    for _ in range(max(0, n - have)):
        text = rng.choice(texts)
        speed = rng.uniform(0.8, 1.3)
        if rng.random() >= k_share:
            job = ("piper", rng.choice(lib))
        elif fav and rng.random() < f_share:
            a = rng.choice(fav)          # his pick, pure or lightly blended
            b = rng.choice(kv_pool) if rng.random() < 0.3 else None
            job = ("kokoro", (a, b, rng.uniform(0.1, 0.35) if b else 0.0))
        else:
            a = rng.choice(kv_pool)
            b = rng.choice(kv_pool) if rng.random() < 0.6 else None
            job = ("kokoro", (a, b, rng.uniform(0.2, 0.8) if b else 0.0))
        pitch = 1.0 + rng.uniform(-p_rng, p_rng)
        out.append((folder / (uuid.uuid4().hex + ".wav"), text, job[0], job[1], speed, pitch, rng.random()))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--word", default="hey_friday")
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()
    if not LIBRITTS.exists():
        sys.exit(f"missing {LIBRITTS} (setup.sh downloads it)")
    cfg = wordcfg.load(args.word)
    out = W / "out" / args.word
    rng = random.Random(1234 + len(list(out.glob("*/*.wav"))))      # a resumed run doesn't redo the same draws
    pos, neg = cfg["positive_texts"], cfg["custom_negative_phrases"]
    jobs = (jobs_for(out / "positive_train", pos, cfg["n_positive_train"], "train", rng, cfg)
            + jobs_for(out / "positive_test", pos, cfg["n_positive_test"], "test", rng, cfg)
            + jobs_for(out / "negative_train", neg, cfg["n_negative_train"], "train", rng, cfg)
            + jobs_for(out / "negative_test", neg, cfg["n_negative_test"], "test", rng, cfg))
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
