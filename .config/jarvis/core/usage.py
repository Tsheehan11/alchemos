"""
Whole-account Claude usage for the HUD's CLAUDE // USAGE widget, without spending a token.

  jarvis usage            one refresh, prints the summary JSON
  jarvis usage --watch    what the HUD runs while a usage widget is up (quickshell OrrinFeed.qml):
                          local logs every LOG_S, the plan report every PLAN_S
  jarvis usage --plan     just the plan report (debug)

Sources
  plan     the Pro plan's 5-hour and weekly utilization + reset times: the same report the Claude CLI's
           /usage screen shows (api.anthropic.com/api/oauth/usage, read with the CLI's own login in
           ~/.claude/.credentials.json; GET only, no model call, no tokens). The token is never refreshed
           here (that would rotate the CLI's refresh token under it): when it has expired, the report is
           "not available" until Claude Code runs again. Jarvis's own rate-limit events (status.json
           usage.plan) count too, whichever is newer. Older than STALE_S → shown as stale, never as current.
  jarvis   Jarvis's Agent SDK usage records (jarvis_db.claude_usage, read-only).
  code     Claude Code sessions on this machine: ~/.claude/projects/**/*.jsonl, assistant records'
           message.usage + model only (never message content), deduped by message id (a reply is
           logged once per content block), read incrementally from a saved byte offset per file.
           Agent SDK sessions (entrypoint sdk-*) are Jarvis's and are left to its own records.
  other    claude.ai and other devices have no local logs or API: estimated as the remainder,
           plan % minus what Jarvis and Claude Code explain (see attribute()).

State (offsets, 5-minute token buckets, plan samples, calibration): ~/.local/share/jarvis/usage/state.json.
Output: ~/.local/share/jarvis/usage/usage.json (the widget watches it).
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

from . import config as C

DIR = C.DATA_DIR / "usage"
STATE = DIR / "state.json"
OUT = DIR / "usage.json"
PROJECTS = Path.home() / ".claude/projects"
CREDS = Path.home() / ".claude/.credentials.json"
JARVIS_DB = C.DATA_DIR / "jarvis.db"
STATUS = C.RUNTIME / "jarvis/status.json"
PLAN_URL = "https://api.anthropic.com/api/oauth/usage"

BUCKET_S = 300                 # token buckets: 5 minutes
KEEP_S = 8 * 86400             # buckets / dedupe ids / samples kept this long (the weekly window + a day)
LOG_S = 60                     # --watch: local logs this often (only new bytes are read)
PLAN_S = 300                   # --watch: plan report this often (one small GET)
STALE_S = 15 * 60              # a plan report older than this isn't "current"
WINDOW_S = {"five_hour": 5 * 3600, "seven_day": 7 * 86400}

# Relative cost of a token, from the API list prices (per MTok input / output). Plan limits are
# compute-based, so this is the best local proxy for "how much of the plan a request used".
# Cache reads cost 0.1× input, cache writes 1.25× (5-minute) or 2× (1-hour).
PRICE = {"haiku": (1.0, 5.0), "sonnet": (3.0, 15.0), "opus": (5.0, 25.0), "fable": (5.0, 25.0)}
FAMILIES = tuple(PRICE)


# ── models ──
def family(model):
    m = str(model or "").lower()
    return next((f for f in FAMILIES if f in m), "other")


def label(model):
    """'claude-opus-5-5' → 'Opus 5.5'; 'claude-3-5-haiku-20241022' → 'Haiku 3.5'; 'haiku' → 'Haiku'."""
    m = str(model or "").lower().replace("claude-", "")
    fam = family(m)
    nums = [n for n in re.findall(r"\d+", m) if len(n) < 8]
    name = fam.capitalize() if fam != "other" else (re.findall(r"[a-z]+", m) or ["?"])[0].capitalize()
    return name + (" " + ".".join(nums[:2]) if nums else "")


def weight(fam, inp, out, cr, cw5, cw1=0):
    pi, po = PRICE.get(fam, PRICE["sonnet"])
    return (pi * (inp + 0.1 * cr + 1.25 * cw5 + 2.0 * cw1) + po * out) / 1e6


# ── state ──
def load_state():
    try:
        s = json.loads(STATE.read_text())
        if s.get("v") == 1:
            return s
    except (OSError, ValueError):
        pass
    return {"v": 1, "files": {}, "seen": {}, "buckets": {}, "jarvis_id": 0, "versions": {}, "samples": [], "plan": {}}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":")))
    tmp.replace(path)


def add(st, ts, source, model, inp=0, out=0, cr=0, cw=0, cw1=0, n=1):
    """Tokens into the 5-minute bucket of ts: buckets[bucket][source][model] = [in, out, cr, cw, req, weight]."""
    b = str(int(ts // BUCKET_S * BUCKET_S))
    row = st["buckets"].setdefault(b, {}).setdefault(source, {}).setdefault(model, [0, 0, 0, 0, 0, 0.0])
    row[0] += inp; row[1] += out; row[2] += cr; row[3] += cw + cw1; row[4] += n
    row[5] += weight(family(model), inp, out, cr, cw, cw1)


# ── Claude Code logs ──
def _ts(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def scan_code(st, now=None):
    """New bytes of every session log since the last scan. Returns records added."""
    now = now or time.time()
    files, seen, added = st["files"], st["seen"], 0
    live = set()
    for f in PROJECTS.glob("**/*.jsonl"):
        try:
            stt = f.stat()
        except OSError:
            continue
        key = str(f)
        live.add(key)
        ino, off = files.get(key, (stt.st_ino, 0))
        if ino != stt.st_ino or stt.st_size < off:      # replaced or truncated: start over (dedupe keeps counts right)
            off = 0
        if stt.st_size == off:
            files[key] = (stt.st_ino, off)
            continue
        if off == 0 and stt.st_mtime < now - KEEP_S:     # old and never read: nothing in the window
            files[key] = (stt.st_ino, stt.st_size)
            continue
        with open(f, "rb") as fh:
            fh.seek(off)
            chunk = fh.read()
        end = chunk.rfind(b"\n") + 1                      # only whole lines; a line being written waits
        for line in chunk[:end].split(b"\n"):
            # cheap filter before parsing: only assistant records that carry a usage block
            if b'"usage"' not in line or b'"assistant"' not in line:
                continue
            try:
                r = json.loads(line)
            except ValueError:
                continue
            if r.get("type") != "assistant":
                continue
            msg = r.get("message") or {}
            u, model = msg.get("usage"), msg.get("model")
            if not isinstance(u, dict) or not model or model.startswith("<"):
                continue
            ts = _ts(r.get("timestamp"))
            if ts is None or ts < now - KEEP_S:
                continue
            fam = family(model)
            if fam != "other":
                v = st["versions"].get(fam)
                if not v or ts >= v[1]:
                    st["versions"][fam] = [model, ts]        # which version "haiku" means lately (Jarvis's rows)
            if str(r.get("entrypoint") or "").startswith("sdk"):
                continue                                      # Agent SDK = Jarvis: counted from its own records
            mid = msg.get("id") or r.get("requestId") or r.get("uuid")
            if not mid or mid in seen:
                continue
            seen[mid] = ts
            cc = u.get("cache_creation") or {}
            cw1 = int(cc.get("ephemeral_1h_input_tokens") or 0)
            cw = int(u.get("cache_creation_input_tokens") or 0) - cw1
            add(st, ts, "code", model, int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0),
                int(u.get("cache_read_input_tokens") or 0), max(0, cw), cw1)
            added += 1
        files[key] = (stt.st_ino, off + end)
    for k in [k for k in files if k not in live]:
        del files[k]
    return added


# ── Jarvis ──
def scan_jarvis(st):
    if not JARVIS_DB.exists():
        return 0
    try:
        db = sqlite3.connect(f"file:{JARVIS_DB}?mode=ro", uri=True, timeout=2)
        rows = db.execute("SELECT id, ts, model, input, output, cache_read, cache_write FROM claude_usage "
                          "WHERE id > ? AND ts >= ? ORDER BY id", (st["jarvis_id"], time.time() - KEEP_S)).fetchall()
        last = db.execute("SELECT COALESCE(MAX(id), 0) FROM claude_usage").fetchone()[0]
        db.close()
    except sqlite3.Error:
        return 0
    for _id, ts, model, i, o, cr, cw in rows:
        add(st, ts, "jarvis", model, i or 0, o or 0, cr or 0, cw or 0)
    st["jarvis_id"] = max(st["jarvis_id"], last)
    return len(rows)


# ── plan ──
def fetch_plan(timeout=8):
    """The CLI's /usage report → {"five_hour": {"pct", "resets_at"}, "seven_day": {…}} or {"error": why}."""
    try:
        o = json.loads(CREDS.read_text()).get("claudeAiOauth") or {}
    except (OSError, ValueError):
        return {"error": "no Claude login on this machine"}
    tok = o.get("accessToken")
    if not tok:
        return {"error": "no Claude login on this machine"}
    if o.get("expiresAt") and o["expiresAt"] / 1000 < time.time() + 30:
        return {"error": "Claude login token expired; it renews the next time Claude Code runs"}
    req = urllib.request.Request(PLAN_URL + "?skip_spend=1", headers={
        "Authorization": "Bearer " + tok, "anthropic-beta": "oauth-2025-04-20", "User-Agent": "stark-os-usage"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.load(r)
    except urllib.error.HTTPError as e:
        return {"error": f"usage report refused (HTTP {e.code})"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"error": f"usage report unreachable ({type(e).__name__})"}
    out = {}
    for k in WINDOW_S:
        w = d.get(k) or {}
        if w.get("utilization") is not None:
            out[k] = {"pct": float(w["utilization"]), "resets_at": _ts(w.get("resets_at"))}
    return out or {"error": "usage report had no plan windows"}


def jarvis_plan():
    """Jarvis's own last rate-limit event (status.json, core/status.py): {"five_hour", "seven_day", "at"}."""
    try:
        p = json.loads(STATUS.read_text()).get("usage", {}).get("plan") or {}
    except (OSError, ValueError):
        return {}
    out = {k: {"pct": float(p[k]["pct"]), "resets_at": p[k].get("resets_at")} for k in WINDOW_S if p.get(k)}
    if out and p.get("at"):
        out["at"] = float(p["at"])
        return out
    return {}


def refresh_plan(st, now=None):
    now = now or time.time()
    got = fetch_plan()
    plan = st["plan"]
    if "error" not in got:
        plan.update({"at": now, "source": "cli", "error": None, **got})
    else:
        plan["error"] = got["error"]
    j = jarvis_plan()
    if j and j["at"] > plan.get("at", 0):
        plan.update({"at": j["at"], "source": "jarvis", **{k: j[k] for k in WINDOW_S if k in j}})
    if plan.get("at") and (not st["samples"] or st["samples"][-1]["at"] != plan["at"]):
        st["samples"].append({"at": plan["at"], **{k: plan[k] for k in WINDOW_S if k in plan}})
    st["samples"] = [s for s in st["samples"] if s["at"] >= now - KEEP_S]


# ── sums ──
def totals(st, since, until=None):
    """{source: {"total": rec, "models": {model: rec}}}; rec = {input, output, cache_read, cache_write, requests, weight}."""
    out = {}
    for b, srcs in st["buckets"].items():
        t = int(b)
        if t + BUCKET_S <= since or (until is not None and t >= until):
            continue
        for src, models in srcs.items():
            s = out.setdefault(src, {"total": _rec(), "models": {}})
            for model, row in models.items():
                for rec in (s["total"], s["models"].setdefault(model, _rec())):
                    for i, k in enumerate(("input", "output", "cache_read", "cache_write", "requests", "weight")):
                        rec[k] += row[i]
    return out


def _rec():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "requests": 0, "weight": 0.0}


def window_start(win, kind):
    return (win or {}).get("resets_at") and win["resets_at"] - WINDOW_S[kind]


def attribute(st, now=None):
    """How much of each plan window Jarvis and Claude Code explain; the rest is claude.ai + other devices.

    Model: plan % = k · (price-weighted local tokens) + other, with other ≥ 0, so for every report in a
    window k ≤ (pct + 0.5) / W_local(window start → report) (+0.5: the report is rounded to whole %).
    Each window gives such an upper bound; windows where claude.ai was idle give a tight one, so k is the
    smallest bound seen (over windows with enough local use to measure). Local % = min(pct, k · W) split
    by each source's share of W; other = pct − local. An estimate, and labelled as one."""
    now = now or time.time()
    calib = st.setdefault("calib", {})
    for kind in WINDOW_S:
        c = calib.setdefault(kind, {"bounds": {}, "upto": 0})
        for s in st["samples"]:
            if s["at"] <= c["upto"]:
                continue                                  # each report is used once
            c["upto"] = s["at"]
            w = s.get(kind)
            start = window_start(w, kind)
            if not start or s["at"] < start:
                continue
            W = sum(v["total"]["weight"] for k, v in totals(st, start, s["at"]).items() if k in ("jarvis", "code"))
            if W < (0.5 if kind == "five_hour" else 2.0):    # too little local use to say anything (≈ $0.50 / $2 at API prices)
                continue
            key = str(int(start))
            bound = (w["pct"] + 0.5) / W
            c["bounds"][key] = min(c["bounds"].get(key, bound), bound)
        c["bounds"] = {k: v for k, v in c["bounds"].items() if float(k) >= now - 5 * 7 * 86400}
        c["k"] = min(c["bounds"].values()) if c["bounds"] else None
        c["windows"] = len(c["bounds"])
    out = {}
    plan = st["plan"]
    for kind in WINDOW_S:
        w = plan.get(kind)
        if not w:
            continue
        start = window_start(w, kind) or now - WINDOW_S[kind]
        t = totals(st, start)
        W = {k: t.get(k, {}).get("total", _rec())["weight"] for k in ("jarvis", "code")}
        k = calib[kind]["k"]
        pct = w["pct"]
        if k is None:
            out[kind] = {"calibrated": False, "windows": 0}
            continue
        local = min(pct, k * (W["jarvis"] + W["code"]))
        tw = (W["jarvis"] + W["code"]) or 1.0
        out[kind] = {"calibrated": True, "windows": calib[kind]["windows"],
                     "jarvis": round(local * W["jarvis"] / tw, 1), "code": round(local * W["code"] / tw, 1),
                     "other": round(max(0.0, pct - local), 1)}
    return out


def _models(src_totals, versions):
    """[{name, tokens, sources}] sorted by tokens; Jarvis's rows say only the family ('haiku'),
    named with the version Claude Code / the SDK resolved that family to lately."""
    merged = {}
    for src, s in src_totals.items():
        for model, rec in s["models"].items():
            m = versions.get(model, [model])[0] if model in FAMILIES else model
            name = label(m)
            e = merged.setdefault(name, {"name": name, "family": family(m), "tokens": 0, "cache": 0, "requests": 0, "sources": []})
            e["tokens"] += rec["input"] + rec["output"]
            e["cache"] += rec["cache_read"] + rec["cache_write"]
            e["requests"] += rec["requests"]
            if src not in e["sources"]:
                e["sources"].append(src)
    return sorted(merged.values(), key=lambda e: -(e["tokens"] + e["cache"] / 10))


def handled_locally(since):
    """Jarvis requests since `since` answered without Claude (regex fast path, local router, a "Did you mean"
    yes) vs sent to Claude, from jarvis.db action_log (read-only). → {"local", "claude", "pct"}."""
    out = {"local": 0, "claude": 0, "pct": None}
    if not JARVIS_DB.exists():
        return out
    try:
        db = sqlite3.connect(f"file:{JARVIS_DB}?mode=ro", uri=True, timeout=2)
        tiers = [r[0] for r in db.execute("SELECT tier FROM action_log WHERE ts >= ?", (since,))]
        db.close()
    except sqlite3.Error:
        return out
    for t in tiers:
        if t == "fast" or t.startswith(("local:", "ask:")):
            out["local"] += 1
        elif t.startswith(("claude", "error:")):
            out["claude"] += 1
    n = out["local"] + out["claude"]
    out["pct"] = round(100.0 * out["local"] / n, 1) if n else None
    return out


def summary(st, now=None):
    now = now or time.time()
    midnight = datetime.combine(datetime.now().date(), datetime.min.time()).timestamp()
    plan = st["plan"]
    week = window_start(plan.get("seven_day"), "seven_day")
    week = week if week and week <= now else now - 7 * 86400
    today_t, week_t = totals(st, midnight), totals(st, week)

    def src(t):
        return {k: {kk: (round(vv, 4) if isinstance(vv, float) else vv) for kk, vv in t.get(k, {}).get("total", _rec()).items()}
                for k in ("jarvis", "code")}
    p = None
    if plan.get("at"):
        p = {"at": plan["at"], "source": plan.get("source"), "stale": now - plan["at"] > STALE_S,
             "error": plan.get("error"), "split": attribute(st, now),
             **{k: plan[k] for k in WINDOW_S if k in plan}}
    return {"updated": now, "week_start": week,
            "plan": p, "plan_error": plan.get("error") if not p or p["stale"] else None,
            "today": src(today_t), "week": src(week_t),
            "models": {"today": _models(today_t, st["versions"]), "week": _models(week_t, st["versions"])},
            "local": {"today": handled_locally(midnight), "week": handled_locally(week)}}


def prune(st, now=None):
    cut = (now or time.time()) - KEEP_S
    st["buckets"] = {b: v for b, v in st["buckets"].items() if int(b) >= cut}
    st["seen"] = {k: t for k, t in st["seen"].items() if t >= cut}


def refresh(st, plan=True):
    scan_code(st)
    scan_jarvis(st)
    if plan:
        refresh_plan(st)
    prune(st)
    s = summary(st)
    save(STATE, st)
    save(OUT, s)
    return s


def main(argv=()):
    ap = argparse.ArgumentParser(prog="jarvis usage", description=__doc__.split("\n\n")[0])
    ap.add_argument("--watch", action="store_true")
    ap.add_argument("--plan", action="store_true")
    a = ap.parse_args(list(argv))
    if a.plan:
        print(json.dumps(fetch_plan(), indent=1))
        return 0
    st = load_state()
    if not a.watch:
        print(json.dumps(refresh(st), indent=1))
        return 0
    last_plan = 0.0
    kick = DIR / "kick"          # touched by the widget (click) → plan report now
    while True:
        now = time.time()
        want_plan = now - last_plan >= PLAN_S or kick.exists()
        kick.unlink(missing_ok=True)
        try:
            refresh(st, plan=want_plan)
        except Exception as e:                  # one bad pass never ends the watcher
            print(f"usage: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        if want_plan:
            last_plan = now
        for _ in range(LOG_S):
            time.sleep(1)
            if kick.exists():
                break


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
