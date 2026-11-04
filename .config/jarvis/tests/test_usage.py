#!/usr/bin/env python3
"""Whole-account usage (core/usage.py) on fake data: Claude Code logs parsed incrementally (byte offsets,
half-written lines wait, per-content-block duplicates counted once, Agent SDK sessions left to Jarvis,
message content never stored), Jarvis's DB rows, model names, the plan report's stale / missing states,
the remainder estimate, and the expired-login path (no network). Run: python tests/test_usage.py"""
import json
import os
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
from core import usage as U  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


tmp = Path(tempfile.mkdtemp())
U.PROJECTS = tmp / "projects"
U.DIR, U.STATE, U.OUT = tmp / "usage", tmp / "usage/state.json", tmp / "usage/usage.json"
U.JARVIS_DB = tmp / "jarvis.db"
U.CREDS = tmp / "creds.json"
U.STATUS = tmp / "status.json"
SECRET = "my bank password is hunter2"
now = time.time()


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime(ts))


def rec(mid, ts, model="claude-opus-5-5", entry="cli", i=10, o=100, cr=1000, cw=200, cw1=0, block="text"):
    return json.dumps({"type": "assistant", "entrypoint": entry, "timestamp": iso(ts), "requestId": "r" + mid,
                       "message": {"id": mid, "model": model, "role": "assistant",
                                   "content": [{"type": block, "text": SECRET}],
                                   "usage": {"input_tokens": i, "output_tokens": o, "cache_read_input_tokens": cr,
                                             "cache_creation_input_tokens": cw + cw1,
                                             "cache_creation": {"ephemeral_1h_input_tokens": cw1, "ephemeral_5m_input_tokens": cw}}}})


proj = U.PROJECTS / "-home-x"
proj.mkdir(parents=True)
f = proj / "s1.jsonl"
user = json.dumps({"type": "user", "timestamp": iso(now - 600), "message": {"content": SECRET}})
f.write_text("\n".join([user, rec("m1", now - 600), rec("m1", now - 600, block="tool_use"),     # same reply, 2 blocks
                        rec("m2", now - 300, model="claude-haiku-5-5", o=50, cr=0, cw=0),
                        rec("s1", now - 200, model="claude-haiku-5-5", entry="sdk-py"),        # Jarvis via the SDK
                        rec("old", now - 9 * 86400)]) + "\n")
(proj / "sub").mkdir()
(proj / "sub/agent.jsonl").write_text(rec("m3", now - 100, model="claude-sonnet-5-5", o=7, cr=0, cw=0, i=3) + "\n")

st = U.load_state()
check("first scan records", U.scan_code(st, now), 3)
t = U.totals(st, now - 3600)
check("code output (dupe once, sdk + old skipped)", t["code"]["total"]["output"], 100 + 50 + 7)
check("code requests", t["code"]["total"]["requests"], 3)
check("sdk not in code", "jarvis" in t, False)
check("versions learned from sdk too", st["versions"]["haiku"][0], "claude-haiku-5-5")
check("no content in state", SECRET in json.dumps(st), False)

# incremental: a half-written line waits, then counts once
with open(f, "a") as fh:
    fh.write(rec("m4", now - 50, o=1000)[:40])
check("partial line waits", U.scan_code(st, now), 0)
off = st["files"][str(f)][1]
with open(f, "a") as fh:
    fh.write(rec("m4", now - 50, o=1000)[40:] + "\n")
check("rest of line counted", U.scan_code(st, now), 1)
check("offset advanced", st["files"][str(f)][1] > off, True)
check("rescan adds nothing", U.scan_code(st, now), 0)
# a resumed / copied session repeating old messages doesn't double count
(proj / "copy.jsonl").write_text(rec("m1", now - 600) + "\n" + rec("m2", now - 300) + "\n")
check("copied messages deduped", U.scan_code(st, now), 0)

# 1-hour cache writes weigh 2× input, 5-minute 1.25×
check("weight cw1", round(U.weight("opus", 0, 0, 0, 0, 1_000_000), 3), 10.0)
check("weight cw5", round(U.weight("opus", 0, 0, 0, 1_000_000, 0), 3), 6.25)
check("weight haiku out", round(U.weight("haiku", 0, 1_000_000, 0, 0), 3), 5.0)

# ── Jarvis's DB ──
db = sqlite3.connect(U.JARVIS_DB)
db.execute("CREATE TABLE claude_usage (id INTEGER PRIMARY KEY, ts REAL, source TEXT, model TEXT, input INTEGER, "
           "output INTEGER, cache_read INTEGER, cache_write INTEGER)")
db.executemany("INSERT INTO claude_usage(ts, source, model, input, output, cache_read, cache_write) VALUES (?,?,?,?,?,?,?)",
               [(now - 400, "voice", "haiku", 500, 40, 9000, 100), (now - 9 * 86400, "voice", "haiku", 1, 1, 1, 1)])
db.commit()
check("jarvis rows", U.scan_jarvis(st), 1)
check("jarvis incremental", U.scan_jarvis(st), 0)
db.execute("INSERT INTO claude_usage(ts, source, model, input, output, cache_read, cache_write) VALUES (?,?,?,?,?,?,?)",
           (now - 10, "typed", "sonnet", 5, 6, 0, 0))
db.commit()
check("jarvis new row", U.scan_jarvis(st), 1)
db.close()

# ── model names ──
check("label opus", U.label("claude-opus-5-5"), "Opus 5.5")
check("label old haiku", U.label("claude-3-5-haiku-20241022"), "Haiku 3.5")
check("label sonnet dated", U.label("claude-sonnet-4-5-20250929"), "Sonnet 4.5")
check("label family", U.label("haiku"), "Haiku")
models = U._models(U.totals(st, now - 3600), st["versions"])
names = {m["name"]: m for m in models}
check("models listed (jarvis 'sonnet' named by the version the logs show)", sorted(names), ["Haiku 5.5", "Opus 5.5", "Sonnet 5.5"])
check("haiku merges code + jarvis", sorted(names["Haiku 5.5"]["sources"]), ["code", "jarvis"])
check("haiku tokens", names["Haiku 5.5"]["tokens"], (10 + 50) + (500 + 40))

# ── plan: none, current, stale ──
U.CREDS.write_text(json.dumps({"claudeAiOauth": {"accessToken": "x", "expiresAt": (now - 60) * 1000}}))
got = U.fetch_plan()
check("expired login: no request", "expired" in got.get("error", ""), True)
U.CREDS.unlink()
check("no login", "no Claude login" in U.fetch_plan()["error"], True)

U.fetch_plan = lambda: {"error": "usage report unreachable (URLError)"}
U.refresh_plan(st, now)
s = U.summary(st, now)
check("no report: plan None", s["plan"], None)
check("no report: says why", s["plan_error"], "usage report unreachable (URLError)")

# Jarvis's own rate-limit event counts when there's nothing newer
U.STATUS.write_text(json.dumps({"usage": {"plan": {"five_hour": {"pct": 40.0, "resets_at": now + 3600},
                                                    "seven_day": {"pct": 10.0, "resets_at": now + 86400}, "at": now - 30}}}))
U.refresh_plan(st, now)
s = U.summary(st, now)
check("jarvis event used", (s["plan"]["source"], s["plan"]["five_hour"]["pct"], s["plan"]["stale"]), ("jarvis", 40.0, False))
s = U.summary(st, now + U.STALE_S + 60)
check("old report is stale", s["plan"]["stale"], True)
check("stale says why", s["plan_error"], "usage report unreachable (URLError)")

# ── remainder estimate ──
# Window 1: only local use → bound k = (pct+0.5)/W. Window 2 at the same k plus claude.ai: other > 0.
st2 = U.load_state()
t0 = now - 4 * 3600
U.add(st2, t0 + 600, "code", "claude-opus-5-5", 0, 400_000)            # weight 10
W = U.weight("opus", 0, 400_000, 0, 0)
st2["samples"] = [{"at": t0 + 1200, "five_hour": {"pct": 19.5, "resets_at": t0 + 5 * 3600}}]   # k = 20/10 = 2 %/unit
st2["plan"] = {"at": t0 + 1200, "five_hour": {"pct": 19.5, "resets_at": t0 + 5 * 3600}}
a = U.attribute(st2, now)
check("calibrated", (a["five_hour"]["calibrated"], a["five_hour"]["code"], a["five_hour"]["other"]), (True, 19.5, 0.0))
check("k", round(st2["calib"]["five_hour"]["k"], 3), round(20.0 / W, 3))
# next window: same local use, plan says 50 % → 30 % is claude.ai + other
t1 = t0 + 5 * 3600
U.add(st2, t1 + 600, "code", "claude-opus-5-5", 0, 300_000)
U.add(st2, t1 + 700, "jarvis", "haiku", 0, 200_000)                     # weight 1
st2["samples"].append({"at": t1 + 1200, "five_hour": {"pct": 50.0, "resets_at": t1 + 5 * 3600}})
st2["plan"] = {"at": t1 + 1200, "five_hour": {"pct": 50.0, "resets_at": t1 + 5 * 3600}}
a = U.attribute(st2, t1 + 1300)["five_hour"]
check("split code", a["code"], round(2.0 * 7.5, 1))
check("split jarvis", a["jarvis"], round(2.0 * 1.0, 1))
check("split other", a["other"], round(50 - 2.0 * 8.5, 1))
check("k stays the tightest bound", round(st2["calib"]["five_hour"]["k"], 3), round(20.0 / W, 3))
# too little local use → not calibrated
st3 = U.load_state()
st3["plan"] = {"at": now, "five_hour": {"pct": 5.0, "resets_at": now + 3600}}
st3["samples"] = [{"at": now, "five_hour": {"pct": 5.0, "resets_at": now + 3600}}]
check("uncalibrated", U.attribute(st3, now)["five_hour"]["calibrated"], False)

# ── one full refresh writes the files, still no content ──
U.refresh(st, plan=False)
check("out written", U.OUT.exists() and U.STATE.exists(), True)
check("no content anywhere", SECRET in U.OUT.read_text() + U.STATE.read_text(), False)

print("FAILS:", len(FAILS)) if FAILS else print("ok: usage")
sys.exit(1 if FAILS else 0)
