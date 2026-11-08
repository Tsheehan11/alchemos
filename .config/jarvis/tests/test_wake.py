#!/usr/bin/env python3
"""Custom wake words (core/wake.py): the installed-model registry jarvis.py loads (persona from the json,
hey_friday's old json without one, a verifier next to it), the one-line training status (progress, ETA,
paused, done, failed), the report line, and the per-word training configs (tools/wakeword/wordcfg.py).
No audio, no models. Run: python tests/test_wake.py"""
import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [ROOT, os.path.join(ROOT, "tools/wakeword")]
tmp = Path(tempfile.mkdtemp())
os.environ["WAKE_TRAIN_DIR"] = str(tmp / "train")
from core import wake  # noqa: E402
import wordcfg  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


# ── registry ──
d = tmp / "wake"
d.mkdir()
(d / "hey_friday.onnx").write_bytes(b"x")
(d / "hey_friday.json").write_text(json.dumps({"threshold": 0.6}))
(d / "hey_orrin.onnx").write_bytes(b"x")
(d / "hey_orrin.json").write_text(json.dumps({"threshold": 0.7, "persona": "jarvis"}))
(d / "hey_orrin.verifier.pkl").write_bytes(b"x")
(d / "hey_selene.onnx").write_bytes(b"x")          # no json: defaults
got = {w["name"]: (w["persona"], w["threshold"], bool(w["verifier"])) for w in wake.installed(d)}
check("installed", got, {"hey_friday": ("friday", 0.6, False), "hey_orrin": ("jarvis", 0.7, True),
                         "hey_selene": ("friday", 0.5, False)})
check("nothing installed", wake.installed(tmp / "none"), [])

# ── status line ──
now = 10_000.0
st = {"state": "running", "words": ["hey_orrin", "hey_selene"], "word": "hey_orrin", "stage": "gen",
      "stage_started": now - 1000, "progress": [10000, 108000]}
line = wake.status_line(st, now=now)
check("status head", line.startswith("hey_orrin · gen · "), True)
check("status count", "10,000/108,000 (9 %)" in line, True)
# gen left 9800 s + 7 other stages (augment+train+eval for orrin, all 4 for selene) + download
left = 9800 + (4500 + 3600 + 900) + (9000 + 4500 + 3600 + 900) + 1800
check("status eta", f"ETA ~{wake._dur(left)}" in line, True)
st2 = dict(st, state="paused", reason="on battery", stage_eta=600)
check("status paused", line != wake.status_line(st2, now=now) and "PAUSED (on battery)" in wake.status_line(st2, now=now), True)
check("status inactive", "service not running" in wake.status_line(st, now=now, active=False), True)
marks = {"hey_orrin.gen", "hey_orrin.augment", "acav"}
st3 = dict(st, stage="train", progress=[60000, 120000], stage_eta=1200)
check("status later eta", f"ETA ~{wake._dur(1200 + 900 + 9000 + 4500 + 3600 + 900)}" in wake.status_line(st3, now=now, done_marks=marks), True)
check("status failed", wake.status_line({"state": "failed", "failed": "disk", "reason": "full"}).startswith("wake training stopped: disk"), True)
out = tmp / "train/out/hey_orrin"
out.mkdir(parents=True)
(out / "eval.json").write_text(json.dumps({"threshold": 0.7, "by_threshold": {"0.7": {"recall": 0.83, "fp_per_hour": 0.21}}}))
check("report", wake.report_line("hey_orrin"), "hey_orrin: 83% recall, 0.21 false/h @ 0.7")
check("report missing", wake.report_line("hey_selene"), "hey_selene: no report")
done = wake.status_line({"state": "done", "words": ["hey_orrin", "hey_selene"]})
check("status done", done.startswith("wake training done: hey_orrin: 83%") and "enable" in done, True)

# ── word configs ──
for w, persona in (("hey_orrin", "jarvis"), ("hey_selene", "friday")):
    c = wordcfg.load(w)
    check(f"{w} persona", c["persona"], persona)
    check(f"{w} model name", c["model_name"], w)
    check(f"{w} scale", (c["n_positive_train"] >= 50000, c["steps"] >= 100000, c["rounds_positive_train"] >= 2), (True, True, True))
    check(f"{w} paths filled", "{W}" in json.dumps(c), False)
    check(f"{w} target not a negative", any(t.strip("!?., ").replace(",", "") == w.replace("_", " ")
                                            for t in c["custom_negative_phrases"]), False)
check("friday cfg", wordcfg.load("hey_friday")["persona"], "friday")
check("favourites", wordcfg.load("hey_orrin")["favourite_voices"], ["bm_george", "af_nicole"])

# ── pipeline: openWakeWord's train.py exits 1 after saving the ONNX (its TFLite export needs onnx_tf) ──
import time  # noqa: E402
import pipeline  # noqa: E402
o = Path(os.environ["WAKE_TRAIN_DIR"]) / "out"
o.mkdir(parents=True, exist_ok=True)
t0 = time.time()
check("no model yet", pipeline.fresh_model("hey_selene", t0 - 5), False)
wordcfg.write_train_yml("hey_selene")
(o / "hey_selene.onnx").write_bytes(b"model")
check("fresh model", pipeline.fresh_model("hey_selene", t0 - 5), True)
check("older than the run", pipeline.fresh_model("hey_selene", time.time() + 60), False)
check("kept: same config", pipeline.kept_model("hey_selene"), True)
y = o / "hey_selene.yml"
y.write_text(y.read_text().replace("max_negative_weight:", "max_negative_weight: 1 #"))
check("not kept: config changed", pipeline.kept_model("hey_selene"), False)
check("not kept: no model", pipeline.kept_model("hey_orrin"), False)

print("FAILS:", len(FAILS)) if FAILS else print("ok: wake")
sys.exit(1 if FAILS else 0)
