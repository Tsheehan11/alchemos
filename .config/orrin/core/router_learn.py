"""
What the local router (core/router_local.py) has learned, and the rules for learning it. No model here
except for `orrin router approve`, which runs the promotion gate.

Evidence comes only from what already happened (no Claude call is ever made to learn):
  claude     a request went to Claude and Claude made exactly one alchemos tool call that a local intent
             covers, with arguments the router can pull out of the words itself      → candidate, 1 confirm
  correction "no, I meant X" / a reworded repeat right after a local action resolved to a different
             intent whose arguments are in the original words                         → candidate, 1 confirm
  ask        "Did you mean X?" answered yes                                            → candidate, 1 confirm
  seen       the same words (or near-identical ones) again                             → seen + 1
Candidates become ACTIVE examples once they have enough evidence (seen ≥ 2 or ≥ 1 confirm), no negatives,
words that actually support the intent, AND the promotion gate passes: the router eval
(tools/eval_router.py) still makes 0 wrong actions and nothing in his own outcome history changes for the
worse. Otherwise they're REJECTED and the reason is logged (events). He can approve a rejected one (the
gate still runs) or forget any learned example.

Negatives (correction, undo, reworded repeat, inverse command within 10 s, the kill switch, a declined
confirmation): the matched learned example is demoted (first) or deleted (second); the exact words stop
acting locally for that intent; the intent's threshold is recalibrated from its outcomes. Built-in
examples (intents.json) are never touched.

Never learned, never asked about, thresholds only ever raised: email / calendar / docs / assignment /
grade intents (claude-only), window control, deletions, power, lock, VPN control, anything that sends.

Store: ~/.local/share/orrin/learned_intents.json (untracked). Outcomes: orrin_db.router_outcomes.
Shared by both personas: nothing here knows who answered.
"""
import fcntl
import json
import re
import time
from contextlib import contextmanager

from . import config as C

VERSION = 2
DOC = ("What Orrin's local router learned (core/router_learn.py). Untracked; shared by ORRIN and SELENE. "
       "Manage with: orrin router stats | review | approve ID | forget ID | reset-learned")

# never learned, never asked about, never given a lower threshold
BLOCKED_INTENTS = {"power", "lock_screen", "close_window", "move_window", "widget.clear", "vpn.control"}
BLOCKED_TOOLS = {"power", "lock_screen", "close_focused_window", "move_window_to_workspace", "widget_remove",
                 "forget", "cancel_reminder", "remember", "set_reminder", "start_task", "open_in_browser",
                 "orrin_persona", "set_skin", "control_run", "control_look"}

PROMOTE_SEEN = 2            # sightings that promote without a confirm
LEARN_CAP = 25              # active learned examples per intent
LEARN_MAX_WORDS = 12
DUP_COS = 0.93              # this similar to an example of the same intent = the same example
MIN_OWN_SIM = 0.45          # a candidate this unlike its intent's built-in examples is a mishearing
DECAY_DAYS = 45             # active learned examples unused this long are dropped
CANDIDATE_DAYS = 30         # candidates / rejections that long without new evidence are dropped
EVENTS_KEEP = 100
OUTCOME_S = 30              # no correction within this long after a local action = weak positive
INVERSE_S = 10              # the opposite command this soon after a local action = negative
ASK_BAND = 0.06             # this far under an intent's threshold: "Did you mean …?"
MAX_RAISE = 0.10            # calibration range around Settings → Local confidence
MAX_LOWER = 0.05
LOWER_MIN_YES = 3           # "yes" answers needed in a band before the threshold drops into it
NEG_RATE = 0.10             # tolerated share of negatives above a threshold (with ≥ 10 outcomes)

# Opposite intents: one right after the other means the first one was wrong.
INVERSE = {}
for a, b in [("media.play", "media.pause"), ("media.next", "media.previous"), ("media.volume_up", "media.volume_down"),
             ("voice.volume_up", "voice.volume_down"), ("dj.start", "dj.stop"), ("dj.more", "dj.less")]:
    INVERSE[a], INVERSE[b] = b, a

# Corrections said right after a local action
UNDO = re.compile(r"^(?:no,? )?(?:undo(?: that| it| this)?|revert(?: that| it)?|put it back|change it back|"
                  r"go back to how it was|cancel that|take that back)$")
WRONG = re.compile(r"^(?:no,? |nope,? )?(?:that's|that is|that was|thats) (?:wrong|not (?:it|right|what i (?:said|meant|asked)))|"
                   r"^(?:no,? |nope,? )?wrong(?: one| thing)?$|^(?:no,? |nope,? )?not that(?: one)?$")
MEANT = re.compile(r"^(?:no,? |nope,? )?(?:that's wrong,? |wrong,? )?(?:i meant|i said|i asked for|i wanted)\s+(?:to\s+)?(.+)$")


def blocked(name, intent=None):
    intent = intent or {}
    return (name in BLOCKED_INTENTS or name.startswith(("claude.", "choice.")) or intent.get("kind", "tool") != "tool"
            or intent.get("tool") in BLOCKED_TOOLS)


def correction(t):
    """Normalised text → ("undo" | "wrong", None) | ("meant", what he meant) | None."""
    if UNDO.match(t):
        return "undo", None
    m = MEANT.match(t)
    if m and len(m.group(1).split()) >= 1:
        return "meant", m.group(1)
    if WRONG.match(t):
        return "wrong", None
    return None


# ── the store ──
def path():
    return C.DATA_DIR / "learned_intents.json"           # looked up each time: tests point DATA_DIR elsewhere


def empty():
    return {"_doc": DOC, "version": VERSION, "next_id": 1, "examples": {}, "offsets": {}, "negatives": {},
            "forgotten": {}, "choices": {}, "events": []}


def _upgrade(raw):
    """v1 ({"learned": {intent: [text]}}) → v2. Old learned examples come back as candidates with one
    Claude confirm, so the router re-checks each one with today's rules and the gate before using it."""
    if raw.get("version") == VERSION:
        d = empty()
        d.update(raw)
        return d
    d, now = empty(), time.time()
    for intent, texts in (raw.get("learned") or {}).items():
        for t in texts:
            if intent.startswith("choice."):
                d["choices"].setdefault(intent.split(".", 1)[1], []).append(t)
                continue
            rid = str(d["next_id"])
            d["next_id"] += 1
            d["examples"][rid] = new_record(rid, intent, t, "legacy", confirms=1, now=now)
    if d["examples"] or d["choices"]:
        event(d, "migrated", None, "", f"{len(d['examples'])} examples from the old learned file, re-checking each")
    return d


def read():
    try:
        return _upgrade(json.loads(path().read_text()))
    except (OSError, ValueError):
        return empty()


def write(data):
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data["_doc"], data["version"] = DOC, VERSION
    data["events"] = data["events"][-EVENTS_KEEP:]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n")
    tmp.replace(p)


@contextmanager
def edit():
    """Read-modify-write under a lock: the voice loop, the app and `orrin router` all write this file."""
    p = path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p.with_suffix(".lock"), "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)
        data = read()
        yield data
        write(data)


def mtime():
    try:
        return path().stat().st_mtime_ns
    except OSError:
        return 0


def new_record(rid, intent, text, source, confirms=0, now=None):
    now = now or time.time()
    return {"id": rid, "intent": intent, "text": text, "state": "candidate", "source": source, "seen": 1,
            "confirms": confirms, "pos": 0, "neg": 0, "created": now, "updated": now, "last_used": 0,
            "promoted": 0, "why": ""}


def add_record(data, intent, text, source, confirms=0):
    rid = str(data["next_id"])
    data["next_id"] += 1
    data["examples"][rid] = rec = new_record(rid, intent, text, source, confirms)
    return rec


def find(data, intent, text):
    return next((r for r in data["examples"].values() if r["intent"] == intent and r["text"] == text), None)


def ready(rec):
    """Enough evidence to try promoting (the gate still decides)."""
    return rec["state"] == "candidate" and rec["neg"] == 0 and (rec["seen"] >= PROMOTE_SEEN or rec["confirms"] >= 1)


def active(data):
    """{intent: [(id, text)]} of the examples the router uses."""
    out = {}
    for r in data["examples"].values():
        if r["state"] == "active":
            out.setdefault(r["intent"], []).append((r["id"], r["text"]))
    return out


def event(data, kind, rec, intent, why=""):
    data["events"].append({"ts": time.time(), "kind": kind, "id": rec["id"] if rec else "",
                           "text": rec["text"] if rec else "", "intent": rec["intent"] if rec else intent, "why": why})


def tidy(data, now=None):
    """Decay: unused active examples after DECAY_DAYS, stale candidates / rejections after CANDIDATE_DAYS.
    Cap: at most LEARN_CAP active per intent (the least useful go). Returns how many were dropped."""
    now, dropped = now or time.time(), 0
    for rid, r in list(data["examples"].items()):
        last = max(r["last_used"], r["promoted"], r["updated"])
        if r["state"] == "active" and now - last > DECAY_DAYS * 86400:
            event(data, "decayed", r, r["intent"], f"unused for {DECAY_DAYS} days")
        elif r["state"] in ("candidate", "rejected") and now - r["updated"] > CANDIDATE_DAYS * 86400:
            pass                                      # quietly: it never did anything
        else:
            continue
        del data["examples"][rid]
        dropped += 1
    for intent, items in active(data).items():
        if len(items) <= LEARN_CAP:
            continue
        recs = sorted((data["examples"][i] for i, _ in items), key=lambda r: (r["pos"] - 2 * r["neg"], r["last_used"], r["promoted"]))
        for r in recs[:len(items) - LEARN_CAP]:
            event(data, "dropped", r, intent, f"over the cap of {LEARN_CAP}")
            del data["examples"][r["id"]]
            dropped += 1
    return dropped


# ── calibration ──
def calibrate(outcomes, base, may_lower=True):
    """Per-intent offset from Settings → Local confidence, from logged outcomes [(score, ok)]:
    the lowest threshold in [base − MAX_LOWER, base + MAX_RAISE] above which negatives are absent (or ≤ 10 %
    once there are ≥ 10 outcomes), and below base only where ≥ LOWER_MIN_YES "yes" answers and no
    negatives sit between it and base. No outcomes → 0. Lowering is then still gated by the eval."""
    lo = -MAX_LOWER if may_lower else 0.0
    steps = [round(lo + i / 100, 2) for i in range(int(round((MAX_RAISE - lo) * 100)) + 1)]
    for off in steps:
        t = base + off
        above = [ok for s, ok in outcomes if s >= t - 1e-9]
        negs = above.count(False)
        if negs and not (len(above) >= 10 and negs / len(above) <= NEG_RATE):
            continue
        if off < 0:
            band = [(s, ok) for s, ok in outcomes if t - 1e-9 <= s < base]
            yes = [s for s, ok in band if ok]
            # enough yes answers, no no's, and never below the lowest score he actually said yes to
            if len(yes) < LOWER_MIN_YES or any(not ok for _, ok in band) or t < int(min(yes) * 100) / 100 - 1e-9:
                continue
        return off
    return MAX_RAISE


# ── `orrin router …` ──
USAGE = "usage: orrin router stats [--json] | review [--json] | approve ID | forget ID | reset-learned [--yes]"


def stats(days=7):
    import orrin_db as db
    data = read()
    since = time.time() - days * 86400
    c = db.router_counts(since)
    today = db.router_counts(time.mktime(time.localtime()[:3] + (0, 0, 0, 0, 0, -1)))
    outs = db.router_outcomes(days)
    n = c["requests"] or 1
    states = {}
    for r in data["examples"].values():
        states[r["state"]] = states.get(r["state"], 0) + 1

    def pct(x, of):
        return round(100.0 * x / of, 1) if of else 0.0
    return {
        "days": days, "requests": c["requests"],
        "local_pct": pct(c["fast"] + c["local"] + c["ask"], n), "router_pct": pct(c["local"], n), "fast_pct": pct(c["fast"], n),
        "claude_pct": pct(c["claude"], n), "ask_pct": pct(c["ask"], n),
        "today": {"requests": today["requests"], "local_pct": pct(today["fast"] + today["local"] + today["ask"], today["requests"])},
        "router_decisions": c["router"], "router_hit_pct": pct(c["router_local"], c["router"]),
        "outcomes": {k: sum(1 for o in outs if o["outcome"] == k) for k in ("pos", "neg", "ask_yes", "ask_no")},
        "learned": states, "offsets": {k: v for k, v in data["offsets"].items() if v},
        "events": list(reversed(data["events"][-12:])),
        "review": review_list(data),
    }


def review_list(data=None):
    data = data or read()
    order = {"active": 0, "candidate": 1, "rejected": 2}
    return sorted(({k: r[k] for k in ("id", "intent", "text", "state", "source", "seen", "confirms", "pos", "neg", "why")}
                   for r in data["examples"].values()),
                  key=lambda r: (order.get(r["state"], 3), r["intent"], r["text"]))


def forget(rid):
    with edit() as d:
        r = d["examples"].pop(str(rid), None)
        if r:
            d["forgotten"].setdefault(r["text"], []).append(r["intent"])   # don't learn it straight back
            event(d, "forgotten", r, r["intent"], "removed by you")
    return r


def reset_learned():
    p = path()
    if p.exists():
        p.with_suffix(".json.bak").write_text(p.read_text())
    with edit() as d:
        n = len(d["examples"])
        d.clear()
        d.update(empty())
        event(d, "reset", None, "", f"{n} learned examples, thresholds and blocked phrasings cleared")
    return n


def cli(argv):
    import sys
    cmd = argv[0] if argv else "stats"
    js = "--json" in argv
    if cmd == "stats":
        s = stats()
        if js:
            print(json.dumps(s))
            return 0
        print(f"last {s['days']} days: {s['requests']} requests · handled locally {s['local_pct']}% "
              f"(fast path {s['fast_pct']}%, router {s['router_pct']}%) · Claude {s['claude_pct']}% · asked {s['ask_pct']}%")
        print(f"today: {s['today']['requests']} requests, {s['today']['local_pct']}% local · "
              f"router acted on {s['router_hit_pct']}% of {s['router_decisions']} decisions")
        print("outcomes: " + ", ".join(f"{k} {v}" for k, v in s["outcomes"].items()))
        print("learned: " + (", ".join(f"{k} {v}" for k, v in s["learned"].items()) or "none"))
        if s["offsets"]:
            print("thresholds: " + ", ".join(f"{k} {v:+.2f}" for k, v in s["offsets"].items()))
        for e in s["events"]:
            print(f"  {time.strftime('%m-%d %H:%M', time.localtime(e['ts']))}  {e['kind']:<10} {e['intent']:<20} "
                  f"{e['text'][:40]:<40} {e['why']}")
        return 0
    if cmd == "review":
        rows = review_list()
        if js:
            print(json.dumps(rows))
            return 0
        if not rows:
            print("Nothing learned yet.")
        for r in rows:
            print(f"{r['id']:>4}  {r['state']:<9} {r['intent']:<20} {r['text']:<44} seen {r['seen']} "
                  f"+{r['pos']} −{r['neg']}  {r['source']}{'  · ' + r['why'] if r['why'] else ''}")
        return 0
    if cmd in ("forget", "remove") and len(argv) > 1:
        gone = [r for r in map(forget, argv[1:]) if r]
        print(f"Forgot {len(gone)}: " + ", ".join(f'"{r["text"]}" → {r["intent"]}' for r in gone) if gone else "No such id.")
        return 0 if gone else 1
    if cmd == "approve" and len(argv) > 1:
        from .router_local import LocalRouter
        r = LocalRouter(C.Config(), record=False, log=lambda *a: None)
        ok, why = r.approve(argv[1])
        print(("Approved: " if ok else "Not approved: ") + why)
        return 0 if ok else 1
    if cmd == "reset-learned":
        if "--yes" not in argv and sys.stdin.isatty() and input("Clear everything the router learned? [y/N] ").lower() != "y":
            return 1
        print(f"Cleared {reset_learned()} learned examples (backup: {path().with_suffix('.json.bak')}).")
        return 0
    print(USAGE)
    return 2
