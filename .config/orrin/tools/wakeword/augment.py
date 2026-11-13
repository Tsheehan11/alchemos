#!/usr/bin/env python3
"""
Room + background augmentation and openWakeWord features for one word, in resumable shards.

Replaces train.py --augment_clips, which (openWakeWord 0.6.0) silently ignores augmentation_rounds > 1:
it repeats the clip list but sizes the features file for one pass, so the extra rounds are cut off.
Here every (split, round) is its own shard ($W/out/<word>/shards/<split>.r<k>.npy, renamed into place
when complete), each round a fresh shuffle with new random rooms, backgrounds and gains. A crash or
reboot redoes at most the shard in progress. The shards are then joined into the four files train.py
--train_model reads (positive/negative_features_train/test.npy).

Runs in the training venv:  $W/.venv/bin/python tools/wakeword/augment.py --word hey_orrin
"""
import argparse
import os
import random
import sys
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wordcfg  # noqa: E402

SPLITS = {   # folder → (features file train.py reads, rounds key)
    "positive_train": ("positive_features_train.npy", "rounds_positive_train"),
    "negative_train": ("negative_features_train.npy", "rounds_negative_train"),
    "positive_test": ("positive_features_test.npy", "rounds_test"),
    "negative_test": ("negative_features_test.npy", "rounds_test"),
}


def total_length(folder):
    """train.py's clip length rule (median + 750 ms, ≥ 2 s, snapped to 2 s when close), over more clips."""
    import scipy.io.wavfile
    clips = sorted(folder.glob("*.wav"))
    pick = random.Random(0).sample(clips, min(500, len(clips)))
    n = int(round(np.median([len(scipy.io.wavfile.read(str(c))[1]) for c in pick]) / 1000) * 1000) + 12000
    return 32000 if n < 32000 or abs(n - 32000) <= 4000 else n


def shard(word_dir, split, k, length, cfg, log):
    from openwakeword.data import augment_clips
    from openwakeword.utils import compute_features_from_generator
    out = word_dir / "shards" / f"{split}.r{k}.npy"
    if out.exists():
        return out
    out.parent.mkdir(parents=True, exist_ok=True)
    clips = sorted(str(c) for c in (word_dir / split).glob("*.wav"))
    random.Random(1000 * k + len(split)).shuffle(clips)
    bg = []
    for p, dup in zip(cfg["background_paths"], cfg.get("background_paths_duplication_rate", [1])):
        bg += [e.path for e in os.scandir(p)] * dup
    rirs = [e.path for p in cfg["rir_paths"] for e in os.scandir(p)]
    t0 = time.time()
    log(f"augment {split} round {k}: {len(clips)} clips")
    gen = augment_clips(clips, total_length=length, batch_size=cfg["augmentation_batch_size"],
                        background_clip_paths=bg, RIR_paths=rirs)
    tmp = out.with_suffix(".part.npy")
    compute_features_from_generator(gen, n_total=len(clips), clip_duration=length, output_file=str(tmp),
                                    device="cpu", ncpu=max(1, (os.cpu_count() or 2) // 2))
    os.replace(tmp, out)
    log(f"augment {split} round {k}: done in {time.time() - t0:.0f} s")
    return out


def join(parts, dest):
    from numpy.lib.format import open_memmap
    arrs = [np.load(p, mmap_mode="r") for p in parts]
    n = sum(len(a) for a in arrs)
    tmp = dest.with_suffix(".part.npy")
    out = open_memmap(tmp, mode="w+", dtype=np.float32, shape=(n,) + arrs[0].shape[1:])
    i = 0
    for a in arrs:
        for j in range(0, len(a), 20000):
            out[i:i + len(a[j:j + 20000])] = a[j:j + 20000]
            i += len(a[j:j + 20000])
    out.flush()
    del out
    os.replace(tmp, dest)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--word", required=True)
    a = ap.parse_args()
    cfg = wordcfg.load(a.word)
    word_dir = wordcfg.W / "out" / a.word

    def log(m):
        print(f"{time.strftime('%H:%M:%S')} {m}", flush=True)

    length = total_length(word_dir / "positive_test")
    log(f"clip length {length} samples")
    for split, (dest, key) in SPLITS.items():
        dest = word_dir / dest
        if dest.exists():
            continue
        parts = [shard(word_dir, split, k, length, cfg, log) for k in range(int(cfg.get(key, 1)))]
        join(parts, dest)
        log(f"{dest.name}: {np.load(dest, mmap_mode='r').shape}")
    log("augment done")


if __name__ == "__main__":
    main()
