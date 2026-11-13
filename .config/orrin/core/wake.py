"""
Custom wake words: what orrin.py loads, and the `orrin wake …` commands.

Installed models live in DATA_DIR/wake/<word>.onnx + <word>.json {"threshold", "persona", …} (+ an
optional <word>.verifier.pkl: openWakeWord's custom verifier, trained on his own recordings). "hey Jarvis"
is always loaded too: it stays the fallback for both personas, so enabling a word never takes away a way
to wake Orrin.

  orrin wake status                 one line: training stage, progress, ETA (from wake-train/status.json)
  orrin wake record [orrin|selene]  guided capture of his own voice (40 "hey …" + 15 other lines per word)
  orrin wake test orrin|selene      the trained model on those recordings (recall / false accepts)
  orrin wake enable orrin|selene [--force]   install the model for its persona (+ verifier), restart Orrin
  orrin wake disable orrin|selene   back to "hey Jarvis" only for that persona
"""
import json
import os
import shutil
import subprocess
import sys
import time
import wave
from pathlib import Path

from . import config as C
from . import persona

DEST = C.DATA_DIR / "wake"
W = Path(os.environ.get("WAKE_TRAIN_DIR", Path.home() / ".local/share/orrin/wake-train"))
REAL = W / "real"
TOOLS = Path(__file__).resolve().parent.parent / "tools/wakeword"
DEFAULT_PERSONA = {"hey_friday": "selene", "hey_selene": "selene", "hey_orrin": "orrin"}
NAMES = {"orrin": "hey_orrin", "selene": "hey_selene"}
SAY = {"hey_orrin": "hey Orrin", "hey_selene": "hey Selene"}
N_POS, CLIP_S, VERIFIER_THRESHOLD = 40, 2.0, 0.3
# other things to say for the verifier's "not the wake word" side: near misses + ordinary commands
OTHER = {
    "hey_orrin": ["hey Erin", "orange juice", "hey Aaron", "Oren is here", "hey Warren", "or in the morning",
                  "turn the lights on", "what's the weather", "hey Jarvis", "play some music", "boring",
                  "hey Lauren", "set a timer", "pouring rain", "what time is it"],
    "hey_selene": ["hey Celine", "serene", "selenium", "hey Serena", "hey Eileen", "hey Colleen", "saline",
                   "turn the lights on", "what's the weather", "hey Jarvis", "play some music", "hey Sally",
                   "set a timer", "hey Selena", "what time is it"],
}


# ── what orrin.py loads ─────────────────────────
def installed(dest=None):
    """[{"name", "path", "persona", "threshold", "verifier"}] for every DATA_DIR/wake/*.onnx."""
    out = []
    for m in sorted((dest or DEST).glob("*.onnx")):
        meta = {}
        try:
            meta = json.loads(m.with_suffix(".json").read_text())
        except (OSError, ValueError):
            pass
        try:
            thr = float(meta.get("threshold", 0.5))
        except (TypeError, ValueError):
            thr = 0.5
        ver = m.with_suffix(".verifier.pkl")
        out.append({"name": m.stem, "path": str(m), "threshold": thr,
                    "persona": persona.norm(meta.get("persona")) or DEFAULT_PERSONA.get(m.stem, "orrin"),
                    "verifier": str(ver) if ver.exists() else None})
    return out


# ── status ───────────────────────────────────────
GUESS = {"setup": 60, "gen": 9000, "download": 1800, "augment": 4500, "train": 3600, "eval": 900}
STAGES = ["gen", "augment", "train", "eval"]


def _dur(s):
    s = int(max(0, s))
    return f"{s // 3600} h {s % 3600 // 60:02d} min" if s >= 3600 else f"{max(1, s // 60)} min"


def status_line(st, now=None, active=True, done_marks=()):
    """status.json dict → one line. done_marks: '<word>.<stage>' already finished (for the ETA)."""
    now = now or time.time()
    state = st.get("state", "?")
    words = st.get("words") or list(NAMES.values())
    if state == "done":
        return "wake training done: " + " · ".join(report_line(w) for w in words) + " → orrin wake enable …"
    if state == "failed":
        return f"wake training stopped: {st.get('failed')}: {st.get('reason')} (train.log)"
    word, stage = st.get("word"), st.get("stage") or "?"
    prog = st.get("progress")
    parts = [f"{word or 'setup'} · {stage}"]
    left = None
    if prog and prog[1]:
        d, t = prog
        parts.append(f"{d:,}/{t:,} ({100 * d / t:.0f} %)")
        if st.get("stage_eta") is not None:
            left = st["stage_eta"]
        elif d and st.get("stage_started"):
            left = (now - st["stage_started"]) / d * (t - d)
    if left is None:
        left = GUESS.get(stage, 0) / 2
    for w in words:                                  # every stage not finished and not the current one
        for s in STAGES:
            if f"{w}.{s}" not in done_marks and (w, s) != (word, stage):
                left += GUESS[s]
    if "acav" not in done_marks and stage != "download":
        left += GUESS["download"]
    parts.append(f"ETA ~{_dur(left)}")
    if state == "paused":
        parts.append(f"PAUSED ({st.get('reason')})")
    if not active:
        parts.append("service not running (systemctl --user start orrin-wake-train)")
    return " · ".join(parts)


def report_line(word):
    try:
        r = json.loads((W / "out" / word / "eval.json").read_text())
    except (OSError, ValueError):
        return f"{word}: no report"
    t = r.get("threshold")
    rows = r.get("by_threshold", {})
    if t is None:
        best = max(rows.values(), key=lambda x: x["recall"] - x["fp_per_hour"]) if rows else None
        return f"{word}: below the bar" + (f" (best {best['recall']:.0%} at {best['fp_per_hour']:.2f} false/h)" if best else "")
    row = rows.get(str(t)) or rows.get(t)
    return f"{word}: {row['recall']:.0%} recall, {row['fp_per_hour']:.2f} false/h @ {t}"


def cmd_status():
    try:
        st = json.loads((W / "status.json").read_text())
    except (OSError, ValueError):
        print("no wake training has run (systemctl --user start orrin-wake-train)")
        return 1
    active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", "orrin-wake-train"]).returncode == 0
    marks = {p.name[:-5] for p in (W / "state").glob("*.done")}
    print(status_line(st, active=active or st.get("state") in ("done", "failed"), done_marks=marks))
    return 0


# ── record ───────────────────────────────────────
def _record(path, secs=CLIP_S, target=None):
    cmd = ["pw-record", "--raw", "--format", "s16", "--rate", "16000", "--channels", "1"]
    if target:
        cmd += ["--target", target]
    p = subprocess.Popen(cmd + ["-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    need, buf = int(secs * 16000) * 2, b""
    while len(buf) < need:
        b = p.stdout.read(need - len(buf))
        if not b:
            break
        buf += b
    p.terminate()
    p.wait(3)
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(16000)
        f.writeframes(buf)
    os.replace(tmp, path)
    import numpy as np
    a = np.frombuffer(buf, np.int16)
    return float(np.abs(a).max()) / 32768 if len(a) else 0.0


def cmd_record(args):
    target = None
    if "--target" in args:
        target = args[args.index("--target") + 1]
    words = [NAMES[a] for a in args if a in NAMES] or list(NAMES.values())
    print("Wake-word recordings: sit where you usually talk to Orrin, normal voice, one phrase per beep.\n"
          f"Each take is {CLIP_S:.0f} s from the moment you press Enter. Enter = record, r = redo the last, q = stop.\n"
          "(Orrin keeps running; it only reacts to \"hey Jarvis\".)\n")
    for word in words:
        d = REAL / word
        (d / "pos").mkdir(parents=True, exist_ok=True)
        (d / "neg").mkdir(parents=True, exist_ok=True)
        todo = [("pos", i, SAY[word]) for i in range(N_POS)] + [("neg", i, t) for i, t in enumerate(OTHER[word])]
        todo = [x for x in todo if not (d / x[0] / f"{x[1]:02d}.wav").exists()]
        print(f"── {SAY[word]}: {len(todo)} to go (saved in {d})")
        last = None
        k = 0
        while k < len(todo):
            kind, i, text = todo[k]
            hint = "  (vary it: closer, further, quieter, quick, slow)" if kind == "pos" and i % 8 == 7 else ""
            ans = input(f"[{kind} {i + 1:2d}] say \"{text}\"{hint}  ⏎ ").strip().lower()
            if ans == "q":
                return 0
            if ans == "r" and last is not None:
                k = last
                continue
            peak = _record(d / kind / f"{i:02d}.wav", target=target)
            warn = "  ← very quiet, check the mic" if peak < 0.02 else ("  ← clipped" if peak > 0.98 else "")
            print(f"   saved (peak {peak:.2f}){warn}")
            last, k = k, k + 1
    print("\nDone. Try them: orrin wake test orrin   ·   install: orrin wake enable orrin")
    return 0


# ── test / enable ────────────────────────────────
def _word(args):
    names = [a for a in args if not a.startswith("-")]
    if not names or names[0] not in NAMES:
        sys.exit("which one? orrin or selene")
    return NAMES[names[0]]


def _scores(model_path, files, verifier=None):
    """Peak score per WAV through the full openWakeWord pipeline (the way Jarvis listens)."""
    import numpy as np
    from openwakeword.model import Model
    kw = {"custom_verifier_models": {Path(model_path).stem: verifier}, "custom_verifier_threshold": VERIFIER_THRESHOLD} if verifier else {}
    m = Model(wakeword_models=[str(model_path)], inference_framework="onnx", **kw)
    out = []
    for f in files:
        with wave.open(str(f)) as w:
            a = np.frombuffer(w.readframes(w.getnframes()), np.int16)
        a = np.concatenate([np.zeros(16000, np.int16), a, np.zeros(8000, np.int16)])   # lead-in like the live stream
        m.reset()
        peak = 0.0
        for i in range(0, len(a) - 1279, 1280):
            peak = max(peak, m.predict(a[i:i + 1280]).get(Path(model_path).stem, 0.0))
        out.append(peak)
    return out


def _threshold(word):
    try:
        t = json.loads((W / "out" / word / "eval.json").read_text()).get("threshold")
    except (OSError, ValueError):
        t = None
    return t


def cmd_test(args):
    word = _word(args)
    model = W / "out" / f"{word}.onnx"
    if not model.exists():
        sys.exit(f"{word} isn't trained yet (jarvis wake status)")
    pos, neg = sorted((REAL / word / "pos").glob("*.wav")), sorted((REAL / word / "neg").glob("*.wav"))
    if not pos:
        sys.exit("no recordings yet: jarvis wake record " + word.split("_")[1])
    thr = _threshold(word) or 0.5
    ps, ns = _scores(model, pos), _scores(model, neg)
    print(f"{word} @ {thr}: your voice {sum(s >= thr for s in ps)}/{len(ps)} woke it, "
          f"{sum(s >= thr for s in ns)}/{len(ns)} other lines falsely did")
    print("  misses:", ", ".join(f"{p.name} {s:.2f}" for p, s in zip(pos, ps) if s < thr) or "none")
    print("  false:", ", ".join(f"{p.name} {s:.2f}" for p, s in zip(neg, ns) if s >= thr) or "none")
    return 0


def _restart_orrin():
    subprocess.run(["systemctl", "--user", "try-restart", "orrin.service"])


def cmd_enable(args):
    word = _word(args)
    model = W / "out" / f"{word}.onnx"
    if not model.exists():
        sys.exit(f"{word} isn't trained yet (jarvis wake status)")
    sys.path.insert(0, str(TOOLS))
    import wordcfg
    persona = wordcfg.load(word).get("persona") or DEFAULT_PERSONA[word]
    thr = _threshold(word)
    print(report_line(word))
    if thr is None:
        if "--force" not in args:
            sys.exit("the eval report says it's below the bar: not installing (--force to install anyway at 0.5)")
        thr = 0.5
    DEST.mkdir(parents=True, exist_ok=True)
    pos, neg = sorted((REAL / word / "pos").glob("*.wav")), sorted((REAL / word / "neg").glob("*.wav"))
    ver = DEST / f"{word}.verifier.pkl"
    if len(pos) >= 10 and len(neg) >= 5:
        from openwakeword.custom_verifier_model import train_custom_verifier
        try:
            train_custom_verifier([str(p) for p in pos], [str(n) for n in neg], str(ver) + ".tmp", str(model),
                                  inference_framework="onnx")
            os.replace(str(ver) + ".tmp", ver)
            print(f"custom verifier trained on {len(pos)} + {len(neg)} of your recordings")
        except Exception as e:     # e.g. none of his clips crossed the base model's threshold
            print(f"no custom verifier ({type(e).__name__}: {e}); the model alone is installed")
            ver.unlink(missing_ok=True)
    else:
        print("no recordings yet (jarvis wake record): installing without a custom verifier")
        ver.unlink(missing_ok=True)
    shutil.copy2(model, DEST / f"{word}.onnx")
    meta = {"threshold": thr, "persona": persona, "trained": time.strftime("%Y-%m-%d"), "report": report_line(word)}
    (DEST / f"{word}.json").write_text(json.dumps(meta, indent=1) + "\n")
    print(f"installed {word} for {persona} (threshold {thr}); \"hey Jarvis\" still works as before. Restarting Jarvis…")
    _restart_orrin()
    return 0


def cmd_disable(args):
    word = _word(args)
    for suf in (".onnx", ".json", ".verifier.pkl"):
        (DEST / f"{word}{suf}").unlink(missing_ok=True)
    print(f"{word} removed: that persona answers \"hey Jarvis\" again. Restarting Jarvis…")
    _restart_orrin()
    return 0


def cli(args):
    sub, rest = (args[0], args[1:]) if args else ("status", [])
    fn = {"status": lambda: cmd_status(), "record": lambda: cmd_record(rest), "test": lambda: cmd_test(rest),
          "enable": lambda: cmd_enable(rest), "disable": lambda: cmd_disable(rest)}.get(sub)
    if not fn:
        print(__doc__.strip().split("\n\n", 1)[1])
        return 2
    return fn()
