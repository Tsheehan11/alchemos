#!/usr/bin/env python3
"""
How good is a trained wake word model (--word hey_orrin; default hey_friday), measured the way Jarvis listens (score ≥ threshold, then the
model is reset, so one utterance fires once):

  recall             held-out positive clips (speakers / voices training never saw), with the training
                     pipeline's room + background augmentation
  adversarial        held-out "sounds like it" phrases ("due friday", "hey freddie", "hey jarvis", …)
  false / hour       openWakeWord's validation set (~11 h of speech, music, noise; not trained on)
  your desk          every recording Jarvis kept from the real mic (~/.local/state/jarvis/rec: commands,
                     follow-ups, near misses), none of which says "hey Friday": any trigger is a false one

Picks the threshold (highest recall, at least MIN_RECALL, with ≤ MAX_FP_H false triggers per hour on the
validation set, none on the desk recordings, ≤ 5 % adversarial accepts) and with --install puts the model where Jarvis loads it:
~/.local/share/jarvis/wake/hey_friday.onnx + hey_friday.json {threshold, …}.

  ~/.config/jarvis/.venv/bin/python tools/wakeword/eval.py --word hey_orrin [--report] [--install]

--report writes $W/out/<word>/eval.json (what `jarvis wake status` and `jarvis wake enable` read).
"""
import argparse
import json
import os
import shutil
import sys
import time
import wave
from pathlib import Path

import numpy as np

W = Path(os.environ.get("WAKE_TRAIN_DIR", Path.home() / ".local/share/jarvis/wake-train"))
OUT = W / "out"
MODEL = OUT / "hey_friday.onnx"   # main() points it at --word
WORD = "hey_friday"
REC = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local/state") / "jarvis/rec"
DEST = Path.home() / ".local/share/jarvis/wake"
THRESHOLDS = [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
MAX_FP_H = 0.5
MIN_RECALL = 0.5                  # on held-out clips with room + noise augmentation; missing half the time is
                                  # worse than both personas sharing "hey Jarvis"
FRAME_S = 0.08                    # one embedding frame
REFRACTORY = int(2.0 / FRAME_S)   # after a trigger Jarvis resets the model and talks for seconds


def session():
    import onnxruntime as ort
    so = ort.SessionOptions()
    so.intra_op_num_threads = 8
    s = ort.InferenceSession(str(MODEL), so, providers=["CPUExecutionProvider"])
    return s, s.get_inputs()[0].name


def scores_windows(sess, name, x, batch=4096):
    out = []
    if sess.get_inputs()[0].shape[0] == 1:          # openWakeWord exports with a fixed batch of 1
        return np.array([sess.run(None, {name: x[i:i + 1].astype(np.float32)})[0].reshape(-1)[0] for i in range(len(x))])
    for i in range(0, len(x), batch):
        out.append(sess.run(None, {name: x[i:i + batch].astype(np.float32)})[0].reshape(-1))
    return np.concatenate(out) if out else np.zeros(0)


def triggers(scores, thr):
    """Count activations with the refractory gap (one per utterance, like Jarvis's reset)."""
    n, i = 0, 0
    hits = np.flatnonzero(scores >= thr)
    last = -10 ** 9
    for h in hits:
        if h - last > REFRACTORY:
            n += 1
            last = h
    return n


def stream_scores(sess, name, feats, n_in):
    """Validation features are one long (frames, 96) stream: slide the model's window over it."""
    idx = np.arange(n_in)[None, :] + np.arange(len(feats) - n_in)[:, None]
    out = []
    for i in range(0, len(idx), 50000):
        out.append(scores_windows(sess, name, feats[idx[i:i + 50000]]))
    return np.concatenate(out)


def clip_max(sess, name, feats):
    """(clips, frames, 96) augmented clip features → each clip's best score over its windows."""
    n_in = sess.get_inputs()[0].shape[1]
    best = np.zeros(len(feats))
    for s in range(0, feats.shape[1] - n_in + 1):
        best = np.maximum(best, scores_windows(sess, name, feats[:, s:s + n_in]))
    return best


def desk(thresholds):
    """Every saved desk recording through the full openWakeWord pipeline with the model loaded the way Jarvis
    loads it (hey_jarvis + hey_friday). → (hours, {thr: friday triggers}, {thr: files}), and how often
    "hey jarvis" itself fired there (sanity: it should, they're mostly Jarvis commands)."""
    from openwakeword.model import Model
    files = sorted(REC.glob("*.wav"))
    m = Model(wakeword_models=["hey_jarvis", str(MODEL)], inference_framework="onnx")
    key = MODEL.stem
    total_s, fired, jarvis_files = 0.0, {t: 0 for t in thresholds}, 0
    worst = []
    for f in files:
        try:
            with wave.open(str(f)) as w:
                if w.getframerate() != 16000 or w.getnchannels() != 1:
                    continue
                a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        except (OSError, wave.Error, EOFError):
            continue
        total_s += len(a) / 16000
        m.reset()
        fs, js = [], []
        for i in range(0, len(a) - 1279, 1280):
            p = m.predict(a[i:i + 1280])
            fs.append(p.get(key, 0.0))
            js.append(p.get("hey_jarvis", 0.0))
        fs = np.array(fs)
        if max(js or [0]) >= 0.4:
            jarvis_files += 1
        for t in thresholds:
            fired[t] += triggers(fs, t)
        if len(fs) and fs.max() >= min(thresholds):
            worst.append((float(fs.max()), f.name))
    return total_s / 3600, fired, len(files), jarvis_files, sorted(worst, reverse=True)[:8]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--install", action="store_true")
    ap.add_argument("--no-desk", action="store_true")
    ap.add_argument("--word", default="hey_friday")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    global MODEL, WORD
    WORD, MODEL = a.word, OUT / f"{a.word}.onnx"
    if not MODEL.exists():
        sys.exit(f"no model at {MODEL} (run tools/wakeword/train.sh)")
    t0 = time.time()
    sess, name = session()
    n_in = sess.get_inputs()[0].shape[1]
    feat = OUT / WORD

    pos = clip_max(sess, name, np.load(feat / "positive_features_test.npy"))
    adv = clip_max(sess, name, np.load(feat / "negative_features_test.npy"))
    val = np.load(W / "data/validation_set_features.npy")
    vs = stream_scores(sess, name, val, n_in)
    val_h = len(val) * FRAME_S / 3600
    rows = {}
    for t in THRESHOLDS:
        rows[t] = {"recall": float((pos >= t).mean()), "adversarial": float((adv >= t).mean()),
                   "fp_per_hour": triggers(vs, t) / val_h}
    report = {"model": str(MODEL), "positive_clips": len(pos), "adversarial_clips": len(adv),
              "validation_hours": round(val_h, 2), "by_threshold": rows}
    if not a.no_desk and REC.exists():
        hours, fired, nfiles, jf, worst = desk(THRESHOLDS)
        report["desk"] = {"hours": round(hours, 2), "files": nfiles, "files_hey_jarvis_fired": jf,
                          "false_triggers": fired, "highest": worst}
    ok = [t for t in THRESHOLDS if rows[t]["fp_per_hour"] <= MAX_FP_H and rows[t]["adversarial"] <= 0.05
          and rows[t]["recall"] >= MIN_RECALL
          and report.get("desk", {}).get("false_triggers", {}).get(t, 0) == 0]
    pick = max(ok, key=lambda t: (rows[t]["recall"], -t)) if ok else None
    report["threshold"] = pick
    report["eval_s"] = round(time.time() - t0)
    report["word"], report["date"] = WORD, time.strftime("%Y-%m-%d %H:%M")
    print(json.dumps(report, indent=1))
    if a.report:
        (feat / "eval.json").write_text(json.dumps(report, indent=1) + "\n")
    if a.install:
        if pick is None:
            sys.exit("no threshold meets the bar: not installing (Jarvis keeps both personas on \"hey Jarvis\")")
        DEST.mkdir(parents=True, exist_ok=True)
        shutil.copy2(MODEL, DEST / f"{WORD}.onnx")
        (DEST / f"{WORD}.json").write_text(json.dumps({
            "threshold": pick, "recall": rows[pick]["recall"], "fp_per_hour": round(rows[pick]["fp_per_hour"], 3),
            "adversarial": rows[pick]["adversarial"], "desk": report.get("desk", {}).get("false_triggers", {}).get(pick),
            "desk_hours": report.get("desk", {}).get("hours"), "trained": time.strftime("%Y-%m-%d")}, indent=1) + "\n")
        print(f"installed → {DEST / (WORD + '.onnx')} (threshold {pick})")


if __name__ == "__main__":
    main()
