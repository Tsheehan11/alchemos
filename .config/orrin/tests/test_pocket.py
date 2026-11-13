#!/usr/bin/env python3
"""Pocket engine + pacing, without Pocket: the worker protocol against a fake worker (start, audio, an error
that keeps the worker, a crash and a stall that restart it, speed as a time stretch), voice.trim(), fixed lines
rendered whole vs Claude's live reply per sentence, and the AlchemOS routing naming presets that exist.
Run: python tests/test_pocket.py"""
import json
import os
import sys
import tempfile

import numpy as np

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [ROOT]
from core import effects, voice  # noqa: E402
from core.tts import pocket  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")
    else:
        print(f"ok  {name}")


FAKE = r'''
import json, os, sys, time
out = sys.stdout.buffer
pidfile = sys.argv[1]
open(pidfile, "a").write(f"{os.getpid()}\n")
out.write(b'{"ready": true, "sr": 24000}\n'); out.flush()
for line in sys.stdin.buffer:
    req = json.loads(line)
    t = req["text"]
    if t == "crash":
        os._exit(1)
    if t == "stall":
        time.sleep(30)
    if req["voice"] == "nobody":
        out.write(b'{"ok": false, "error": "unknown Pocket voice"}\n'); out.flush(); continue
    n = 2400 * len(t.split())
    out.write(json.dumps({"ok": True, "sr": 24000, "n": n}).encode() + b"\n")
    out.write(bytes(4 * n)); out.flush()
'''

with tempfile.TemporaryDirectory() as d:
    worker = os.path.join(d, "fake_worker.py")
    pids = os.path.join(d, "pids")
    open(worker, "w").write(FAKE)
    # the engine runs `<python> -I <worker>`; a wrapper script passes the pid file along
    wrap = os.path.join(d, "py")
    open(wrap, "w").write(f"#!/bin/sh\nexec {sys.executable} \"$2\" {pids}\n")
    os.chmod(wrap, 0o755)
    e = pocket.Pocket(python=wrap, worker=worker, env=dict(os.environ))
    check("available with a python + worker", e.available(), True)

    a, sr = e.synth("orrin_2", "one two three", 1.0)
    check("audio length from the header", (len(a), sr, a.dtype.name), (7200, 24000, "float32"))
    a, _ = e.synth("orrin_2", "one two three four", 1.0)
    check("one worker for many requests", len(open(pids).read().split()), 1)

    try:
        e.synth("nobody", "hello", 1.0)
        check("worker error raises", False, True)
    except RuntimeError as err:
        check("worker error raises", "unknown" in str(err), True)
    e.synth("orrin_2", "still the same worker", 1.0)
    check("an error reply keeps the worker", len(open(pids).read().split()), 1)

    try:
        e.synth("orrin_2", "crash", 1.0)
        check("crash raises", False, True)
    except RuntimeError:
        check("crash raises", True, True)
    a, _ = e.synth("orrin_2", "back again", 1.0)
    check("a crash restarts the worker next time", (len(open(pids).read().split()), len(a)), (2, 4800))

    old = pocket.SYNTH_TIMEOUT_S
    pocket.SYNTH_TIMEOUT_S = 0.5
    try:
        e.synth("orrin_2", "stall", 1.0)
        check("stall raises", False, True)
    except RuntimeError as err:
        check("stall raises", "stalled" in str(err), True)
    pocket.SYNTH_TIMEOUT_S = old
    e.synth("orrin_2", "fresh worker", 1.0)
    check("a stall restarts the worker", len(open(pids).read().split()), 3)

    a, _ = e.synth("orrin_2", "one two three four five six seven eight nine ten", 1.25)
    check("speed 1.25 shortens by ~1/1.25", abs(len(a) / 24000 - 1.0 / 1.25) < 0.05, True)
    e.close()

check("pocket voices are prefixed (no clash with Kokoro / piper names)", pocket.Pocket().handles("orrin_2"), False)

# ── trim ──
sr = 24000
tone = np.sin(np.arange(sr) * 2 * np.pi * 220 / sr).astype(np.float32) * 0.5
padded = np.concatenate([np.zeros(sr), tone, np.zeros(sr)]).astype(np.float32)
t = voice.trim(padded, sr)
check("trim keeps ~60 ms before and ~120 ms after", abs(len(t) / sr - (1.0 + voice.TRIM_LEAD_S + voice.TRIM_TAIL_S)) < 0.03, True)
check("trim leaves silence alone", len(voice.trim(np.zeros(sr, np.float32), sr)), sr)


# ── pacing: fixed lines whole, live replies per sentence ──
class Q(list):
    def put(self, x):
        self.append(x)


def queued(text, live):
    u = voice.Utterance.__new__(voice.Utterance)
    u.v, u.live, u.texts, u.n_added, u.chars, u.who, u.params = None, live, Q(), 0, 0, "orrin", None
    u.add(text)
    return [(x[0], x[2]) for x in u.texts]


line = "Your timer is done, sir. Shall I start another?"
check("fixed line: one cached render", queued(line, False), [("Your timer is done, sir. Shall I start another?", True)])
check("live reply: per sentence", queued(line, True),
      [("Your timer is done, sir.", None), ("Shall I start another?", None)])
long_line = "First " + " ".join(["word"] * 11) + ". Then " + " ".join(["more"] * 11) + "."
check("long fixed line falls back to per sentence", len(queued(long_line, False)), 2)

# ── AlchemOS routing names presets that exist ──
skin = json.load(open(os.path.expanduser("~/.config/quickshell/skins/alchemos/skin.json")))
names = {v for who in skin["voiceRouting"].values() for v in who.values()}
check("AlchemOS routing presets exist in effects.json", sorted(names - set(effects.presets())), [])
check("AlchemOS voices are Pocket's designed ones",
      (skin["voices"]["orrin"]["voice"], skin["voices"]["selene"]["voice"]), ("pocket/orrin_2", "pocket/selene_1"))

print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
