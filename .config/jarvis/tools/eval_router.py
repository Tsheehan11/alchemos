#!/usr/bin/env python3
"""
Evaluate the local router (core/router_local.py) on realistic utterances that are NOT in
intents.json: commands for every tool, ambiguous ones, and open-ended questions.

  .venv/bin/python tools/eval_router.py                 # current model + threshold sweep
  .venv/bin/python tools/eval_router.py --model bge-small --threshold 0.8 -v

Nothing runs: decide() only picks an intent and fills slots. Live lists (installed apps, theme
presets from the HUD) are used, as in Jarvis. Reports, for the router alone (as if the regex
fast path didn't exist) and for the real pipeline (fast path first):
  accuracy       right local action, or correctly left to Claude
  wrong actions  acted locally when it shouldn't have, or did the wrong thing (the number that matters)
  fall-through   commands that went to Claude anyway (costs time, not correctness)
  latency        decide() p50 / p95, embedding + slots
"""
import argparse
import os
import statistics
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import config as C  # noqa: E402
from core import fastpath  # noqa: E402
from core import router_local as R  # noqa: E402

CLAUDE = None
# (utterance as whisper writes it, expected): expected = CLAUDE, or (intent, {arg: value} that must match)
CASES = [
    # ── commands, one or more per tool ──
    ("Could you fire up Discord for me?", ("open_app", {"name": "discord"})),
    ("Launch Steam.", ("open_app", {"name": "steam"})),
    ("Open up Visual Studio Code.", ("open_app", {"name": "visual studio code"})),
    ("Bring up the terminal.", ("open_app", {"name": "terminal"})),
    ("Close this.", ("close_window", {})),
    ("Jump over to workspace four.", ("switch_workspace", {"n": 4})),
    ("Take me to desktop 2.", ("switch_workspace", {"n": 2})),
    ("Send this window to workspace three.", ("move_window", {"n": 3})),
    ("Switch the HUD to Matrix.", ("set_theme", {"preset": "MATRIX"})),
    ("Go with the Mark 3 theme.", ("set_theme", {"preset": "MARK III"})),
    ("Arctic theme please.", ("set_theme", {"preset": "ARCTIC"})),
    ("Shut the lights off.", ("lights.power", {"action": "off"})),
    ("Turn my LED strip on.", ("lights.power", {"action": "on"})),
    ("Dim the lights to 20%.", ("lights.brightness", {"value": 20})),
    ("Set the strip to forty five percent.", ("lights.brightness", {"value": 45})),
    ("Have the lights dance to the music.", ("lights.mode", {"value": "music"})),
    ("Resume my music.", ("media.play", {})),
    ("Pause it.", ("media.pause", {})),
    ("Skip this song.", ("media.next", {})),
    ("Go back one song.", ("media.previous", {})),
    ("Bit louder.", ("media.volume_up", {})),
    ("Turn it down a little.", ("media.volume_down", {})),
    ("Set the volume to 35.", ("media.set_volume", {"value": 35})),
    ("Mute everything.", ("media.mute", {"action": "mute"})),
    ("What song is playing?", ("what_is_playing", {})),
    ("Who's this by?", ("what_is_playing", {})),
    ("How's the computer holding up?", ("status.overview", {})),
    ("What's my battery at?", ("status.battery", {})),
    ("Is the CPU getting hot?", ("status.temperature", {})),
    ("Am I on a VPN right now?", ("vpn.status", {})),
    ("Hook me up to Proton.", ("vpn.control", {"action": "connect_proton"})),
    ("Disconnect from the VPN.", ("vpn.control", {"action": "disconnect"})),
    ("Open the UW CS servers.", ("open_uwcs", {})),
    ("Lock the computer.", ("lock_screen", {})),
    ("Could you grab me a screenshot?", ("screenshot.region", {"mode": "region"})),
    ("Screenshot this monitor.", ("screenshot.screen", {"mode": "screen"})),
    ("Snap a pic of this window.", ("screenshot.window", {"mode": "window"})),
    ("I want to annotate a screenshot.", ("screenshot.annotate", {"mode": "annotate"})),
    ("Where do my screenshots get saved?", CLAUDE),
    ("Delete my last screenshot.", CLAUDE),
    ("Restart the PC.", ("power", {"action": "reboot"})),
    ("Put the laptop to sleep.", ("power", {"action": "suspend"})),
    ("Start a timer for 8 minutes.", ("set_timer", {"minutes": 8})),
    ("Set an egg timer for six minutes.", ("set_timer", {"minutes": 6, "label": "egg"})),
    ("How much time is left on the timer?", ("list_reminders", {})),
    ("What's it like outside?", ("weather.now", {})),
    ("What's the weather in Montreal?", ("weather.now", {"place": "montreal"})),
    ("Is it going to rain tomorrow?", ("weather.tomorrow", {})),
    ("Put a clock for Tokyo on the second monitor.", ("widget.clock", {"tz": "tokyo"})),
    ("Show my system stats on the laptop screen.", ("widget.stats", {})),
    ("Clear all the widgets.", ("widget.clear", {})),
    ("Start a stopwatch.", ("widget.stopwatch", {})),
    ("Jarvis, could you talk a little quieter?", ("voice.volume_down", {})),
    ("Raise your voice a bit.", ("voice.volume_up", {})),
    ("Set your voice volume to 35%.", ("voice.set_volume", {"percent": 35})),
    # ── ambiguous / incomplete: must go to Claude ──
    ("Open it.", CLAUDE),                                   # no app named
    ("Set the volume.", CLAUDE),                            # no level
    ("Turn on the VPN.", CLAUDE),                           # which one?
    ("Make it brighter in here.", CLAUDE),                  # no number
    ("Don't turn off the lights.", CLAUDE),                 # negation
    ("Dim the lights and play some jazz.", CLAUDE),         # compound + a search
    ("Play something relaxing.", CLAUDE),                   # needs a choice
    ("Remind me at 6 to call Sam.", CLAUDE),                # free-text reminder
    ("Remember that the wifi password is on the fridge.", CLAUDE),
    ("Make your voice deeper.", CLAUDE),                    # "your voice", but not volume
    ("Set your volume.", CLAUDE),                           # no level, and music or voice?
    # ── open-ended ──
    ("Why do cats purr?", CLAUDE),
    ("Explain how a hash map works.", CLAUDE),
    ("What should I cook tonight with rice and eggs?", CLAUDE),
    ("Tell me something interesting.", CLAUDE),
    ("How long would it take to drive to Toronto?", CLAUDE),
    ("Who wrote Pride and Prejudice?", CLAUDE),
    # ── phase 2: claude-only, never local ──
    ("Do I have any new email?", CLAUDE),
    ("What's on my schedule tomorrow?", CLAUDE),
    ("When is CS 137 assignment 6 due?", CLAUDE),
    ("Has my midterm been graded yet?", CLAUDE),
    ("Find the lab report in my Drive.", CLAUDE),
]


def norm_val(k, v):
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v).strip().lower()
    if k == "preset":
        return R.A._preset_key(s)
    if k == "name":
        return R.A.find_app(s)[0] or s
    return s


def judge(d, expected):
    """→ 'ok' | 'wrong' (acted wrongly) | 'fell' (command left to Claude)."""
    if expected is CLAUDE:
        return "ok" if d.path != "local" else "wrong"
    intent, want = expected
    if d.path != "local":
        return "fell"
    if d.intent != intent:
        return "wrong"
    args = d.steps[0]["args"]
    for k, v in want.items():
        if k not in args or norm_val(k, args[k]) != norm_val(k, v):
            return "wrong"
    return "ok"


def run(router, threshold, verbose=False, pipeline=False):
    res, lat, reasons = [], [], {}
    for text, exp in CASES:
        if pipeline and fastpath.match(text) is not None:
            res.append("ok")    # the regex fast path is exact by design (e.g. "turn on the VPN" = Proton); not under test
            continue
        t0 = time.perf_counter()
        d = router.decide(text, threshold)
        lat.append((time.perf_counter() - t0) * 1000)
        j = judge(d, exp)
        res.append(j)
        if d.path != "local":
            reasons[d.path.split(":")[1]] = reasons.get(d.path.split(":")[1], 0) + 1
        if verbose and (j != "ok" or verbose > 1):
            top = " ".join(f"{n}:{s:.2f}" for n, s in d.top3)
            got = d.steps[0]["args"] if d.steps else ""
            print(f"  {j.upper():<5} {text:<52} → {d.path:<24} {got}   [{top}]")
    cmds = sum(1 for _, e in CASES if e is not CLAUDE)
    return {"acc": res.count("ok") / len(res), "wrong": res.count("wrong"), "fell": res.count("fell") / cmds,
            "p50": statistics.median(lat) if lat else 0, "p95": sorted(lat)[int(len(lat) * 0.95)] if lat else 0,
            "reasons": reasons}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=R.MODEL, choices=list(R.MODELS))
    ap.add_argument("--threshold", type=float, default=None, help="default: the Settings value")
    ap.add_argument("-v", "--verbose", action="count", default=0, help="-v: misses, -vv: every case")
    a = ap.parse_args()
    cfg = C.Config()
    th = a.threshold if a.threshold is not None else float(cfg["jarvisRouterThreshold"])
    t0 = time.perf_counter()
    router = R.LocalRouter(cfg, model=a.model, record=False)
    router.warm()
    print(f"model {a.model}: loaded in {(time.perf_counter() - t0) * 1000:.0f} ms, {len(router.texts)} examples, "
          f"{len(CASES)} cases ({sum(1 for _, e in CASES if e is not CLAUDE)} commands)\n")
    r = run(router, th, a.verbose)
    print(f"\nthreshold {th:.2f}, gap {R.GAP}: router alone")
    print(f"  accuracy {r['acc']:.1%}   wrong actions {r['wrong']}   fall-through {r['fell']:.1%}   "
          f"latency p50 {r['p50']:.1f} ms  p95 {r['p95']:.1f} ms")
    print(f"  fell through because: {', '.join(f'{k} {v}' for k, v in sorted(r['reasons'].items(), key=lambda kv: -kv[1]))}")
    p = run(router, th, pipeline=True)
    print(f"  with the regex fast path first: accuracy {p['acc']:.1%}, wrong {p['wrong']}, fall-through {p['fell']:.1%}")
    print("\nsweep (router alone):  threshold  accuracy  wrong  fall-through")
    for x in [0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]:
        s = run(router, x)
        print(f"                       {x:.2f}       {s['acc']:6.1%}   {s['wrong']:>4}   {s['fell']:6.1%}")


if __name__ == "__main__":
    main()
