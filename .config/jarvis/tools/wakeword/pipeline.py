#!/usr/bin/env python3
"""
Unattended wake-word training: setup → for each word (wordcfg.WORDS): gen → augment → train → eval.

Run by the user unit jarvis-wake-train.service (Nice 19, idle IO; see tools/wakeword/README in setup.sh's
header for the manual steps). Resumable: a finished stage leaves $W/state/<word>.<stage>.done, and the
stages themselves resume inside (gen tops each folder up clip by clip, augment keeps finished shards,
downloads continue with curl -C -). Only training restarts its stage (openWakeWord can't resume a run;
it is the short one). A stage that fails is retried up to MAX_TRIES times over restarts, then the word
is given up with a toast instead of looping.

Pauses (SIGSTOP of the stage's process group, never a kill) on battery, undocked or in combat mode, and
continues (SIGCONT) once all three are fine again. Holds a systemd-inhibit sleep+idle lock only while
running docked on AC. Never installs a model: `jarvis wake enable orrin|selene` does that, after he
has looked at the reports.

  status   $W/status.json (`jarvis wake status`)    log   $W/train.log
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import wordcfg  # noqa: E402

W = wordcfg.W
LOG = W / "train.log"
STATUS = W / "status.json"
STATE = W / "state"
TRAIN_PY = W / ".venv/bin/python"
JARVIS_PY = Path.home() / ".config/jarvis/.venv/bin/python"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
GAME_STATE = RUNTIME / "stark-game/state.json"
STAGES = ["gen", "augment", "train", "eval"]
MAX_TRIES = 3
SPARE_GB = 20
ACAV_GB = 17.2
GEN_WORKERS = int(os.environ.get("WAKE_GEN_WORKERS", "12"))
# rough stage lengths for the ETA of stages not started yet (s); gen's comes from its own rate
GUESS = {"setup": 1800, "gen": 9000, "augment": 4500, "train": 3600, "eval": 900}

PROGRESS = [  # → (done, total, eta_s or None)
    (re.compile(r"^(\d+)/(\d+) · (\d+) s$"), lambda m: (int(m[1]), int(m[2]), None)),
    (re.compile(r"(\d+)/(\d+) \[[\d:]+<([\d:]+)"), lambda m: (int(m[1]), int(m[2]), _hms(m[3]))),
]


def _hms(t):
    s = 0
    for part in t.split(":"):
        s = s * 60 + int(part)
    return s


def log(msg):
    with LOG.open("a") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


# ── conditions ───────────────────────────────────
def on_ac():
    for p in Path("/sys/class/power_supply").glob("*"):
        try:
            if (p / "type").read_text().strip() == "Mains":
                return (p / "online").read_text().strip() == "1"
        except OSError:
            pass
    return True       # no mains supply listed: a desktop


def docked():
    """Any external display connected (stark-govee's rule)."""
    for st in Path("/sys/class/drm").glob("card*-*/status"):
        if st.parent.name.split("-", 1)[1].startswith(("eDP", "LVDS", "DSI", "Writeback")):
            continue
        try:
            if st.read_text().strip() == "connected":
                return True
        except OSError:
            pass
    return False


def combat():
    try:
        return bool(json.loads(GAME_STATE.read_text()).get("active"))
    except (OSError, ValueError, AttributeError):
        return False


def hold_reason():
    if not on_ac():
        return "on battery"
    if not docked():
        return "undocked"
    if combat():
        return "combat mode"
    return None


# ── status ───────────────────────────────────────
class Status:
    def __init__(self):
        self.d = {"state": "starting", "words": wordcfg.WORDS, "started": time.time()}
        try:
            old = json.loads(STATUS.read_text())
            self.d["started"] = old.get("started", self.d["started"])
            self.d["paused_s"] = old.get("paused_s", 0)
        except (OSError, ValueError):
            pass
        self.lock = threading.Lock()

    def set(self, **kw):
        with self.lock:
            self.d.update(kw)
            self.d["updated"] = time.time()
            tmp = STATUS.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.d, indent=1))
            os.replace(tmp, STATUS)


ST = Status()


class Inhibit:
    """systemd-inhibit sleep+idle, held while a stage runs docked on AC."""
    def __init__(self):
        self.p = None

    def on(self):
        if self.p is None or self.p.poll() is not None:
            self.p = subprocess.Popen(["systemd-inhibit", "--what=sleep:idle", "--who=jarvis wake training",
                                       "--why=training the hey Orrin / hey Selene wake words", "--mode=block",
                                       "sleep", "infinity"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def off(self):
        if self.p is not None and self.p.poll() is None:
            self.p.terminate()
            self.p.wait(5)
        self.p = None


INHIBIT = Inhibit()


def wait_ok():
    """Between stages: block until docked + AC + no combat."""
    r = hold_reason()
    if r:
        INHIBIT.off()
        log(f"waiting: {r}")
        t0 = time.time()
        while hold_reason():
            ST.set(state="paused", reason=hold_reason())
            time.sleep(15)
        ST.set(paused_s=ST.d.get("paused_s", 0) + time.time() - t0)
        log("conditions fine again: continuing")
    INHIBIT.on()
    ST.set(state="running", reason=None)


def run(cmd, env=None, label=""):
    """One stage's command in its own process group, paused/continued with the conditions. → exit code."""
    wait_ok()
    log(f"$ {' '.join(map(str, cmd))}")
    e = dict(os.environ, **(env or {}))
    p = subprocess.Popen([str(c) for c in cmd], stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         start_new_session=True, env=e, cwd=str(W))
    stopped = [False]
    done = threading.Event()

    def watch():
        t_stop = 0.0
        while not done.wait(10):
            r = hold_reason()
            if r and not stopped[0]:
                os.killpg(p.pid, signal.SIGSTOP)
                stopped[0], t_stop = True, time.time()
                INHIBIT.off()
                log(f"paused: {r}")
                ST.set(state="paused", reason=r)
            elif r and stopped[0]:
                ST.set(reason=r)
            elif not r and stopped[0]:
                INHIBIT.on()
                os.killpg(p.pid, signal.SIGCONT)
                stopped[0] = False
                ST.set(state="running", reason=None, paused_s=ST.d.get("paused_s", 0) + time.time() - t_stop)
                log("resumed")
    threading.Thread(target=watch, daemon=True).start()

    last_pct = -1
    buf = b""
    while True:
        chunk = p.stdout.read1(65536)
        if not chunk:
            break
        buf += chunk
        *lines, buf = re.split(rb"[\r\n]", buf)
        for raw in lines:
            line = raw.decode("utf-8", "replace").strip()
            if not line:
                continue
            prog = None
            for rx, fn in PROGRESS:
                m = rx.search(line)
                if m:
                    prog = fn(m)
                    break
            if prog:
                d, t, eta = prog
                ST.set(progress=[d, t], stage_eta=eta, progress_label=label or None)
                pct = int(100 * d / max(1, t))
                if pct // 5 != last_pct // 5:      # the log keeps every 5 %, not every tqdm redraw
                    last_pct = pct
                    log(f"  {label} {d}/{t} ({pct} %)" + (f", stage ETA {eta // 60} min" if eta else ""))
            elif "it/s]" not in line and "s/it]" not in line:
                log("  " + line[:300])
    rc = p.wait()
    done.set()
    return rc


# ── stages ───────────────────────────────────────
def mark(word, stage):
    return STATE / f"{word}.{stage}.done"


def tries(word, stage, bump=False):
    f = STATE / f"{word}.{stage}.tries"
    n = int(f.read_text()) if f.exists() else 0
    if bump:
        f.write_text(str(n + 1))
    return n


def free_gb():
    return shutil.disk_usage(W).free / 1e9


def check_disk():
    """The full ACAV100M negative features (17 GB) + ~6 GB of clips and features per word must fit with
    SPARE_GB to spare; checked before anything is generated, so it fails early (and says why)."""
    full = W / "data/acav100m_full.npy"
    have = full.stat().st_size / 1e9 if full.exists() else 0
    have += (W / "data/acav100m_full.npy.part").stat().st_size / 1e9 if (W / "data/acav100m_full.npy.part").exists() else 0
    need = max(0, ACAV_GB - have) + SPARE_GB + 6 * sum(not mark(w, "augment").exists() for w in wordcfg.WORDS)
    if free_gb() < need:
        fail("disk", f"{free_gb():.0f} GB free, {need:.0f} GB needed (17 GB ACAV100M + {SPARE_GB} GB spare + clips)")


def setup(acav=False):
    """Training venv + data (setup.sh); acav=True: the full ACAV100M features (before the first training)."""
    return run(["bash", HERE / "setup.sh"], env={"ACAV": "full" if acav else ""}, label="download" if acav else "setup")


def stage(word, st):
    cfgp = wordcfg.write_train_yml(word)
    if st == "gen":
        return run([JARVIS_PY, HERE / "gen_clips.py", "--word", word, "--workers", GEN_WORKERS], label="gen")
    if st == "augment":
        return run([TRAIN_PY, HERE / "augment.py", "--word", word], env={"OMP_NUM_THREADS": "11"}, label="augment")
    if st == "train":
        return run([TRAIN_PY, "-m", "openwakeword.train", "--training_config", cfgp, "--train_model"],
                   env={"OMP_NUM_THREADS": "12"}, label="train")
    if st == "eval":
        return run([JARVIS_PY, HERE / "eval.py", "--word", word, "--report"], label="eval")


def notify(title, text):
    subprocess.run(["notify-send", "-a", "Jarvis", "-i", "audio-input-microphone", title, text],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
    subprocess.run(["qs", "ipc", "call", "jarvis", "toast", title, text],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)


def fail(what, why):
    log(f"FAILED {what}: {why}")
    ST.set(state="failed", failed=what, reason=why)
    INHIBIT.off()
    notify("WAKE TRAINING STOPPED", f"{what}: {why}")
    sys.exit(0)          # a clean exit: the unit must not restart into the same failure


def summary(word):
    try:
        r = json.loads((W / "out" / word / "eval.json").read_text())
    except (OSError, ValueError):
        return f"{word}: no report"
    t = r.get("threshold")
    if t is None:
        best = max(r["by_threshold"].values(), key=lambda x: x["recall"] - x["fp_per_hour"])
        return f"{word}: below the bar (best {best['recall']:.0%} recall at {best['fp_per_hour']:.2f} false/h)"
    row = r["by_threshold"][str(t)] if str(t) in r["by_threshold"] else r["by_threshold"][t]
    return f"{word}: {row['recall']:.0%} recall, {row['fp_per_hour']:.2f} false/h at {t}"


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: (INHIBIT.off(), ST.set(state="stopped"), log("stopped (SIGTERM)"),
                                              os._exit(143)))
    log(f"== pipeline start (pid {os.getpid()}): {', '.join(wordcfg.WORDS)}")
    check_disk()
    if not (STATE / "setup.done").exists():
        ST.set(state="running", word=None, stage="setup", stage_started=time.time(), progress=None)
        if tries("_", "setup", bump=True) >= MAX_TRIES:
            fail("setup", "failed 3 times (see train.log)")
        if setup() != 0:
            log("setup failed: retrying in 60 s")
            time.sleep(60)
            sys.exit(1)
        (STATE / "setup.done").touch()
    for word in wordcfg.WORDS:
        for st in STAGES:
            if mark(word, st).exists():
                continue
            if tries(word, st, bump=True) >= MAX_TRIES:
                log(f"{word} {st}: failed {MAX_TRIES} times, skipping the word")
                notify("WAKE TRAINING", f"{word}: {st} failed {MAX_TRIES} times (train.log)")
                break
            if st == "train" and not (STATE / "acav.done").exists():
                ST.set(state="running", word=word, stage="download", stage_started=time.time(), progress=None)
                log("== full ACAV100M negative features")
                if tries("_", "acav", bump=True) >= MAX_TRIES:
                    fail("download", "the ACAV100M download failed 3 times (see train.log)")
                if setup(acav=True) != 0:
                    time.sleep(60)
                    sys.exit(1)
                (STATE / "acav.done").touch()
            ST.set(state="running", word=word, stage=st, stage_started=time.time(), progress=None, stage_eta=None)
            log(f"== {word} {st}")
            t0 = time.time()
            rc = stage(word, st)
            if rc != 0:
                log(f"{word} {st} exited {rc}: restarting the pipeline in 60 s")
                time.sleep(60)
                sys.exit(1)          # Restart=on-failure runs us again; the stage resumes
            mark(word, st).write_text(f"{time.time() - t0:.0f}\n")
            log(f"{word} {st} done in {(time.time() - t0) / 60:.0f} min")
        if mark(word, "eval").exists():
            s = summary(word)
            log("report " + s)
            notify("WAKE WORD TRAINED", s + " · jarvis wake status")
    INHIBIT.off()
    ST.set(state="done", stage=None, word=None, progress=None, finished=time.time())
    log("== all done")
    notify("WAKE TRAINING DONE", " · ".join(summary(w) for w in wordcfg.WORDS))
    subprocess.run(["systemctl", "--user", "disable", "jarvis-wake-train.service"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
