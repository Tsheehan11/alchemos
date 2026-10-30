"""
Jarvis memory: one SQLite file shared by the voice loop and the MCP server.

  facts       things Trevor asked Jarvis to remember (FTS5 index for recall)
  action_log  every request: tier used, tools called, result (pruned after 30 days)
  reminders   timers / reminders; the voice loop fires them, so they survive restarts
  router_log  every local-router decision: top-3 intents, slots, latency, path (pruned with action_log)
  tracker_log every write to his SE tracker sheet: cell, old → new, why; `jarvis tracker undo` reverts the last batch

WAL mode + a busy timeout, since two processes write to it.
"""
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("JARVIS_DB") or Path.home() / ".local/share/jarvis/jarvis.db")
LOG_DAYS = 30

SCHEMA = """
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY,
    fact TEXT NOT NULL UNIQUE,
    created REAL NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS facts_fts USING fts5(fact, content='facts', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
    INSERT INTO facts_fts(rowid, fact) VALUES (new.id, new.fact);
END;
CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
    INSERT INTO facts_fts(facts_fts, rowid, fact) VALUES ('delete', old.id, old.fact);
END;
CREATE TABLE IF NOT EXISTS action_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    request TEXT NOT NULL,
    tier TEXT NOT NULL,          -- fast | claude:<model> | error
    tools TEXT NOT NULL,         -- JSON list of "tool(args)"
    result TEXT NOT NULL,
    ms INTEGER
);
CREATE INDEX IF NOT EXISTS action_log_ts ON action_log(ts);
CREATE TABLE IF NOT EXISTS reminders (
    id INTEGER PRIMARY KEY,
    due REAL NOT NULL,
    text TEXT NOT NULL,
    kind TEXT NOT NULL,          -- timer | reminder
    created REAL NOT NULL,
    fired REAL                   -- NULL until it goes off
);
CREATE INDEX IF NOT EXISTS reminders_due ON reminders(fired, due);
CREATE TABLE IF NOT EXISTS router_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    request TEXT NOT NULL,
    path TEXT NOT NULL,          -- local | claude:<why> (below-threshold, small-gap, other, claude-only, slots, …)
    intent TEXT,                 -- the top intent
    top3 TEXT NOT NULL,          -- JSON [[intent, score], …]
    slots TEXT NOT NULL,         -- JSON {name: value}
    ms REAL
);
CREATE INDEX IF NOT EXISTS router_log_ts ON router_log(ts);
CREATE TABLE IF NOT EXISTS tracker_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    batch TEXT NOT NULL,         -- one apply() call: undo reverts a whole batch
    sheet TEXT NOT NULL,         -- spreadsheet id
    tab TEXT NOT NULL,
    kind TEXT NOT NULL,          -- set | insert (a whole row; new = JSON of the row's values)
    cell TEXT NOT NULL,          -- A1 notation: G42, or A42:H42 for an insert
    row_key TEXT NOT NULL,       -- "CS 137 | Assignment A5 - …": the row it was meant for
    old TEXT,
    new TEXT,
    source TEXT NOT NULL,        -- voice | grade-notice | learn-feed | course-email | undo | …
    undone REAL                  -- set when `jarvis tracker undo` reverted it
);
CREATE INDEX IF NOT EXISTS tracker_log_batch ON tracker_log(batch);
"""

STOPWORDS = set("""a an the and or but to of in on at for with by from is are was were be been am i me my
you your it its this that these those what whats which who whom how when where why do does did can could
would should will shall please jarvis hey sir tell show set turn get give let make up down about into""".split())


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript(SCHEMA)
    return db


@contextmanager
def _db():
    db = connect()
    try:
        yield db
    finally:
        db.close()


# ── facts ──────────────────────────────────────
def remember(fact):
    fact = " ".join(fact.split())[:500]
    if not fact:
        raise ValueError("empty fact")
    with _db() as db:
        db.execute("INSERT OR IGNORE INTO facts(fact, created) VALUES (?, ?)", (fact, time.time()))
    return fact


def _terms(text):
    words = re.findall(r"[a-z0-9']+", text.lower())
    return [w.strip("'") for w in words if len(w) > 2 and w not in STOPWORDS][:12]


def recall(query, limit=5):
    """Best-matching facts for some text (empty list if nothing relevant)."""
    terms = _terms(query)
    if not terms:
        return []
    match = " OR ".join(f'"{t}"*' for t in terms)
    with _db() as db:
        rows = db.execute(
            "SELECT f.id, f.fact FROM facts_fts JOIN facts f ON f.id = facts_fts.rowid "
            "WHERE facts_fts MATCH ? ORDER BY bm25(facts_fts) LIMIT ?", (match, limit)).fetchall()
    return [dict(r) for r in rows]


def all_facts():
    with _db() as db:
        return [dict(r) for r in db.execute("SELECT id, fact FROM facts ORDER BY id")]


def forget(fact_id):
    with _db() as db:
        row = db.execute("SELECT fact FROM facts WHERE id = ?", (fact_id,)).fetchone()
        if not row:
            raise ValueError(f"no fact with id {fact_id}")
        db.execute("DELETE FROM facts WHERE id = ?", (fact_id,))
    return row["fact"]


# ── action log ─────────────────────────────────
def log_action(request, tier, tools, result, ms=None):
    with _db() as db:
        db.execute("INSERT INTO action_log(ts, request, tier, tools, result, ms) VALUES (?,?,?,?,?,?)",
                   (time.time(), request[:1000], tier, json.dumps(tools)[:2000], str(result)[:1000], ms))


def prune_log(days=LOG_DAYS):
    with _db() as db:
        db.execute("DELETE FROM router_log WHERE ts < ?", (time.time() - days * 86400,))
        return db.execute("DELETE FROM action_log WHERE ts < ?", (time.time() - days * 86400,)).rowcount


def log_decision(request, path, intent, top3, slots, ms):
    with _db() as db:
        db.execute("INSERT INTO router_log(ts, request, path, intent, top3, slots, ms) VALUES (?,?,?,?,?,?,?)",
                   (time.time(), request[:1000], path, intent, json.dumps(top3), json.dumps(slots, default=str)[:1000], ms))


def recent_decisions(limit=40):
    with _db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM router_log ORDER BY ts DESC LIMIT ?", (limit,))]


def recent_log(limit=30, tier_prefix=None):
    q, args = "SELECT * FROM action_log", []
    if tier_prefix:
        q += " WHERE tier LIKE ?"
        args.append(tier_prefix + "%")
    q += " ORDER BY ts DESC LIMIT ?"
    args.append(limit)
    with _db() as db:
        return [dict(r) for r in db.execute(q, args)]


# ── reminders ──────────────────────────────────
def add_reminder(due, text, kind):
    with _db() as db:
        cur = db.execute("INSERT INTO reminders(due, text, kind, created) VALUES (?,?,?,?)",
                         (due, text[:200], kind, time.time()))
        return cur.lastrowid


def pending_reminders():
    with _db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM reminders WHERE fired IS NULL ORDER BY due")]


def due_reminders(now=None):
    now = now or time.time()
    with _db() as db:
        return [dict(r) for r in db.execute(
            "SELECT * FROM reminders WHERE fired IS NULL AND due <= ? ORDER BY due", (now,))]


def mark_fired(rid):
    with _db() as db:
        db.execute("UPDATE reminders SET fired = ? WHERE id = ?", (time.time(), rid))


def cancel_reminder(rid):
    with _db() as db:
        row = db.execute("SELECT * FROM reminders WHERE id = ? AND fired IS NULL", (rid,)).fetchone()
        if not row:
            raise ValueError(f"no pending timer or reminder with id {rid}")
        db.execute("DELETE FROM reminders WHERE id = ?", (rid,))
    return dict(row)


# ── tracker writes ─────────────────────────────
def log_tracker(batch, sheet, tab, kind, cell, row_key, old, new, source):
    with _db() as db:
        db.execute("INSERT INTO tracker_log(ts, batch, sheet, tab, kind, cell, row_key, old, new, source) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (time.time(), batch, sheet, tab, kind, cell, row_key[:300],
                    None if old is None else json.dumps(old), None if new is None else json.dumps(new), source))


def tracker_writes(limit=30):
    with _db() as db:
        rows = [dict(r) for r in db.execute("SELECT * FROM tracker_log ORDER BY id DESC LIMIT ?", (limit,))]
    for r in rows:
        r["old"] = None if r["old"] is None else json.loads(r["old"])
        r["new"] = None if r["new"] is None else json.loads(r["new"])
    return rows


def last_tracker_batch():
    """Writes of the newest batch that hasn't been undone (newest first), or []."""
    with _db() as db:
        row = db.execute("SELECT batch FROM tracker_log WHERE undone IS NULL AND source != 'undo' "
                         "ORDER BY id DESC LIMIT 1").fetchone()
    if not row:
        return []
    return [r for r in tracker_writes(500) if r["batch"] == row["batch"]]


def mark_tracker_undone(batch):
    with _db() as db:
        db.execute("UPDATE tracker_log SET undone = ? WHERE batch = ?", (time.time(), batch))
