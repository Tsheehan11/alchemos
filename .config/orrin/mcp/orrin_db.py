"""
Orrin memory: one SQLite file shared by the voice loop and the MCP server.

  facts       things Trevor asked Orrin to remember (FTS5 index for recall)
  action_log  every request: tier used, tools called, result (pruned after 30 days)
  reminders   timers / reminders; the voice loop fires them, so they survive restarts
  router_log  every local-router decision: top-3 intents, slots, latency, path (pruned with action_log)
  router_outcomes what happened after a local action or a "Did you mean…?": pos (no correction in 30 s) | neg
              (correction, undo, reworded repeat, kill switch, declined) | ask_yes | ask_no. Per-intent
              thresholds and the promotion gate's personal checks come from it (core/router_learn.py)
  tracker_log every write to his SE tracker sheet: cell, old → new, why; `orrin tracker undo` reverts the last batch
  calendar_log every write to his Google calendars (google_api.CalendarWriter): event, before → after;
              `orrin calendar undo` reverts the last batch; link ties a batch to the tracker batch it followed
  threads     conversations for the ORRIN app: voice and typed turns of one conversation share a thread;
              kind quick (a one-off command, hidden by default) | thread (several turns or real work) | task
  messages    each turn of a thread (FTS5 index for the app's search)
  watchers    "tell me when this window changes": what to watch, until when, its state (core/watch.py)
  tasks       background Agent SDK jobs (core/tasks.py): queued → running → done | failed | cancelled | interrupted
  task_log    a task's steps (tool calls) and text, for the app's live log
  claude_turns Claude turns per request (ResultMessage.num_turns), for the app's "turns today"
  llm_log     the local model tier (core/local_llm.py): what it proposed per eligible request, and in shadow
              mode what Claude did instead and whether they agreed (pruned after 90 days)

WAL mode + a busy timeout, since two processes write to it.
"""
import json
import os
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

DB_PATH = Path(os.environ.get("ORRIN_DB") or Path.home() / ".local/share/orrin/orrin.db")
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
CREATE TABLE IF NOT EXISTS router_outcomes (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    request TEXT NOT NULL,       -- normalised utterance
    intent TEXT NOT NULL,        -- the intent the router matched (or asked about)
    score REAL NOT NULL,         -- its similarity
    example TEXT,                -- learned example id that matched ('' = built-in)
    outcome TEXT NOT NULL,       -- pos | neg | ask_yes | ask_no
    why TEXT                     -- weak-positive | correction | undo | reworded | inverse | kill-switch | declined | …
);
CREATE INDEX IF NOT EXISTS router_outcomes_intent ON router_outcomes(intent, ts);
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
    undone REAL                  -- set when `orrin tracker undo` reverted it
);
CREATE INDEX IF NOT EXISTS tracker_log_batch ON tracker_log(batch);
CREATE TABLE IF NOT EXISTS calendar_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    batch TEXT NOT NULL,         -- one CalendarWriter: undo reverts a whole batch
    calendar TEXT NOT NULL,      -- calendar id
    event TEXT NOT NULL,         -- event id
    kind TEXT NOT NULL,          -- create | update | delete
    summary TEXT NOT NULL,       -- the event's title, for the log
    old TEXT,                    -- JSON: the written fields before (the whole event for a delete)
    new TEXT,                    -- JSON: the written fields after (none for a delete)
    source TEXT NOT NULL,        -- voice | typed | task | tracker | cli | undo | …
    link TEXT,                   -- the tracker_log batch this write kept the calendar in step with
    undone REAL
);
CREATE INDEX IF NOT EXISTS calendar_log_batch ON calendar_log(batch);
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'quick',
    created REAL NOT NULL,
    updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS threads_updated ON threads(updated);
CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY,
    thread INTEGER NOT NULL,
    ts REAL NOT NULL,
    role TEXT NOT NULL,          -- user | orrin (the assistant, whichever persona)
    source TEXT NOT NULL,        -- voice | typed | task | cli
    text TEXT NOT NULL,
    tools TEXT NOT NULL DEFAULT '[]',
    tier TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS messages_thread ON messages(thread, id);
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(text, content='messages', content_rowid='id');
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, text) VALUES (new.id, new.text);
END;
CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY,
    thread INTEGER,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    status TEXT NOT NULL,        -- queued | running | done | failed | cancelled | interrupted
    created REAL NOT NULL,
    started REAL,
    finished REAL,
    result TEXT,
    steps INTEGER NOT NULL DEFAULT 0,
    turns INTEGER NOT NULL DEFAULT 0,
    resumed_from INTEGER,
    announce TEXT,               -- the line to say about it (finished / failed / interrupted), until said
    announced REAL               -- when it was said (or given up on); NULL + announce = still owed
);
CREATE TABLE IF NOT EXISTS task_log (
    id INTEGER PRIMARY KEY,
    task INTEGER NOT NULL,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,          -- step | text | note | error
    text TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS task_log_task ON task_log(task, id);
CREATE TABLE IF NOT EXISTS watchers (
    id INTEGER PRIMARY KEY,
    kind TEXT NOT NULL,          -- window | monitor
    target TEXT NOT NULL,        -- window address (0x…) or monitor name, fixed when it was set up
    label TEXT NOT NULL,         -- "kitty: cargo build" / "monitor DP-5", for the console and speech
    condition TEXT NOT NULL,     -- what he asked for, in his words ("the build finishes")
    interval REAL NOT NULL,      -- seconds between captures
    min_area REAL NOT NULL DEFAULT 0.0005,
    repeat INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,        -- active | paused | done | stopped | expired | failed
    created REAL NOT NULL,
    expires REAL NOT NULL,
    checks INTEGER NOT NULL DEFAULT 0,
    calls INTEGER NOT NULL DEFAULT 0,   -- Claude judgements made
    last_check REAL,
    note TEXT NOT NULL DEFAULT '',      -- latest state in plain words
    result TEXT,
    finished REAL
);
CREATE TABLE IF NOT EXISTS claude_turns (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    source TEXT NOT NULL,        -- voice | typed | task | usage
    turns INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS claude_turns_ts ON claude_turns(ts);
CREATE TABLE IF NOT EXISTS claude_usage (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    source TEXT NOT NULL,        -- voice | typed | task | watch | control | usage
    model TEXT NOT NULL,         -- haiku | sonnet | opus | the full id if none of those
    input INTEGER NOT NULL DEFAULT 0,
    output INTEGER NOT NULL DEFAULT 0,
    cache_read INTEGER NOT NULL DEFAULT 0,
    cache_write INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS claude_usage_ts ON claude_usage(ts);
CREATE TABLE IF NOT EXISTS control_approvals (
    token TEXT PRIMARY KEY,      -- random, made by core/brain.py's gate after his yes; the model never sees it
    plan TEXT NOT NULL,          -- core/control.plan_hash of the exact plan he approved (window + steps)
    address TEXT NOT NULL,       -- the window it's for
    source TEXT NOT NULL,        -- voice | typed | task:<id>
    created REAL NOT NULL,
    expires REAL NOT NULL,       -- a couple of minutes: an approval is for running that plan now
    used REAL                    -- set when control_run takes it: one plan, once
);
CREATE TABLE IF NOT EXISTS control_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    address TEXT NOT NULL,
    label TEXT NOT NULL,
    goal TEXT NOT NULL,
    steps INTEGER NOT NULL,      -- steps in the plan
    done INTEGER NOT NULL,       -- steps carried out and verified
    outcome TEXT NOT NULL,       -- done | stopped:<why> | refused:<why>
    detail TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS llm_log (
    id INTEGER PRIMARY KEY,
    ts REAL NOT NULL,
    request TEXT NOT NULL,
    source TEXT NOT NULL,        -- voice | typed
    mode TEXT NOT NULL,          -- shadow (Claude ran it) | live (the local model ran it)
    intent TEXT NOT NULL DEFAULT '',   -- the intent the local model chose ('' = it escalated)
    call TEXT,                   -- JSON [tool, args] it proposed
    claude TEXT,                 -- JSON [tool, args] Claude ran (shadow), [] = no action, null = unknown
    claude_intent TEXT NOT NULL DEFAULT '',
    verdict TEXT NOT NULL,       -- agree | disagree | escalated | unknown | live | live-failed
    why TEXT NOT NULL DEFAULT '',
    ms REAL,
    think INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS llm_log_ts ON llm_log(ts);
"""

STOPWORDS = set("""a an the and or but to of in on at for with by from is are was were be been am i me my
you your it its this that these those what whats which who whom how when where why do does did can could
would should will shall please orrin hey sir tell show set turn get give let make up down about into""".split())


def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH, timeout=5, isolation_level=None)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA busy_timeout=5000")
    db.executescript(SCHEMA)
    _migrate(db)
    return db


_MIGRATED = False


def _migrate(db):
    """Columns added after a table first shipped. Rows that predate a column get the value that keeps them quiet."""
    global _MIGRATED
    if _MIGRATED:
        return
    cols = {r[1] for r in db.execute("PRAGMA table_info(tasks)")}
    if "announce" not in cols:
        db.execute("ALTER TABLE tasks ADD COLUMN announce TEXT")
    if "announced" not in cols:
        db.execute("ALTER TABLE tasks ADD COLUMN announced REAL")
        db.execute("UPDATE tasks SET announced = coalesce(finished, created)")   # old tasks: nothing owed
    if "persona" not in {r[1] for r in db.execute("PRAGMA table_info(messages)")}:
        db.execute("ALTER TABLE messages ADD COLUMN persona TEXT NOT NULL DEFAULT ''")   # '' = ORRIN (core/persona.py)
    # AlchemOS rename: rows from before it say role 'jarvis' and persona 'friday' / 'jarvis'
    db.execute("UPDATE messages SET role = 'orrin' WHERE role = 'jarvis'")
    db.execute("UPDATE messages SET persona = 'selene' WHERE persona = 'friday'")
    db.execute("UPDATE messages SET persona = '' WHERE persona = 'jarvis'")
    _MIGRATED = True


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
        db.execute("DELETE FROM router_outcomes WHERE ts < ?", (time.time() - 3 * days * 86400,))   # calibration wants history
        db.execute("DELETE FROM claude_turns WHERE ts < ?", (time.time() - days * 86400,))
        db.execute("DELETE FROM llm_log WHERE ts < ?", (time.time() - 3 * days * 86400,))
        return db.execute("DELETE FROM action_log WHERE ts < ?", (time.time() - days * 86400,)).rowcount


def log_llm(request, source, mode, intent, call, claude, claude_intent, verdict, why="", ms=None, think=False):
    with _db() as db:
        db.execute("INSERT INTO llm_log(ts, request, source, mode, intent, call, claude, claude_intent, verdict, why, ms, think) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                   (time.time(), request[:500], source, mode, intent or "", None if call is None else json.dumps(call, default=str)[:1000],
                    None if claude is None else json.dumps(claude, default=str)[:1000], claude_intent or "", verdict, why[:300], ms, int(think)))


def llm_log(days=14):
    with _db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM llm_log WHERE ts >= ? ORDER BY ts", (time.time() - days * 86400,))]


def log_decision(request, path, intent, top3, slots, ms):
    with _db() as db:
        db.execute("INSERT INTO router_log(ts, request, path, intent, top3, slots, ms) VALUES (?,?,?,?,?,?,?)",
                   (time.time(), request[:1000], path, intent, json.dumps(top3), json.dumps(slots, default=str)[:1000], ms))


def log_outcome(request, intent, score, example, outcome, why=""):
    with _db() as db:
        db.execute("INSERT INTO router_outcomes(ts, request, intent, score, example, outcome, why) VALUES (?,?,?,?,?,?,?)",
                   (time.time(), request[:500], intent, float(score), example or "", outcome, why))


def router_outcomes(days=90, intent=None):
    q, args = "SELECT * FROM router_outcomes WHERE ts >= ?", [time.time() - days * 86400]
    if intent:
        q += " AND intent = ?"
        args.append(intent)
    with _db() as db:
        return [dict(r) for r in db.execute(q + " ORDER BY ts", args)]


def router_counts(since):
    """→ {"requests", "fast", "local", "ask", "claude", "other"} from action_log tiers, and the router's own paths."""
    with _db() as db:
        tiers = [r[0] for r in db.execute("SELECT tier FROM action_log WHERE ts >= ?", (since,))]
        paths = [r[0] for r in db.execute("SELECT path FROM router_log WHERE ts >= ?", (since,))]
    c = {"requests": len(tiers), "fast": 0, "local": 0, "llm": 0, "ask": 0, "claude": 0, "other": 0}
    for t in tiers:
        k = ("fast" if t == "fast" else "local" if t.startswith("local:") else "llm" if t.startswith("llm:") else "ask" if t.startswith("ask:")
             else "claude" if t.startswith(("claude", "error:")) else "other")
        c[k] += 1
    c["router"] = len(paths)
    c["router_local"] = sum(1 for p in paths if p == "local")
    c["router_ask"] = sum(1 for p in paths if p == "ask")
    return c


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


# ── calendar writes ────────────────────────────
def log_calendar(batch, calendar, event, kind, summary, old, new, source, link=None):
    with _db() as db:
        db.execute("INSERT INTO calendar_log(ts, batch, calendar, event, kind, summary, old, new, source, link) "
                   "VALUES (?,?,?,?,?,?,?,?,?,?)",
                   (time.time(), batch, calendar, event, kind, (summary or "")[:300],
                    None if old is None else json.dumps(old), None if new is None else json.dumps(new), source, link))


def calendar_writes(limit=30, batch=None):
    with _db() as db:
        if batch:
            rows = [dict(r) for r in db.execute("SELECT * FROM calendar_log WHERE batch = ? ORDER BY id DESC", (batch,))]
        else:
            rows = [dict(r) for r in db.execute("SELECT * FROM calendar_log ORDER BY id DESC LIMIT ?", (limit,))]
    for r in rows:
        r["old"] = None if r["old"] is None else json.loads(r["old"])
        r["new"] = None if r["new"] is None else json.loads(r["new"])
    return rows


def last_calendar_batch(link=None):
    """Writes of the newest batch not undone (newest first), or []. link: only the batch that followed
    that tracker batch."""
    with _db() as db:
        if link:
            row = db.execute("SELECT batch FROM calendar_log WHERE undone IS NULL AND link = ? AND source != 'undo' "
                             "ORDER BY id DESC LIMIT 1", (link,)).fetchone()
        else:
            row = db.execute("SELECT batch FROM calendar_log WHERE undone IS NULL AND source != 'undo' "
                             "ORDER BY id DESC LIMIT 1").fetchone()
    return calendar_writes(batch=row["batch"]) if row else []


def mark_calendar_undone(batch):
    with _db() as db:
        db.execute("UPDATE calendar_log SET undone = ? WHERE batch = ?", (time.time(), batch))


# ── threads (the ORRIN app) ───────────────────
def new_thread(title, kind="quick"):
    now = time.time()
    with _db() as db:
        return db.execute("INSERT INTO threads(title, kind, created, updated) VALUES (?,?,?,?)",
                          (title[:120], kind, now, now)).lastrowid


def update_thread(tid, title=None, kind=None):
    with _db() as db:
        if title is not None:
            db.execute("UPDATE threads SET title = ? WHERE id = ?", (title[:120], tid))
        if kind is not None:
            db.execute("UPDATE threads SET kind = ? WHERE id = ?", (kind, tid))


def get_thread(tid):
    with _db() as db:
        r = db.execute("SELECT * FROM threads WHERE id = ?", (tid,)).fetchone()
    return dict(r) if r else None


def add_message(tid, role, source, text, tools=(), tier="", persona=""):
    """persona: who answered (core/persona.py) on an assistant message; '' = ORRIN."""
    now = time.time()
    persona = "" if persona in ("", "orrin", None) else str(persona)
    with _db() as db:
        mid = db.execute("INSERT INTO messages(thread, ts, role, source, text, tools, tier, persona) VALUES (?,?,?,?,?,?,?,?)",
                         (tid, now, role, source, text[:20000], json.dumps(list(tools))[:4000], tier, persona)).lastrowid
        db.execute("UPDATE threads SET updated = ? WHERE id = ?", (now, tid))
    return {"id": mid, "thread": tid, "ts": now, "role": role, "source": source, "text": text[:20000],
            "tools": list(tools), "tier": tier, "persona": persona}


def list_threads(query="", include_quick=False, limit=60):
    """Newest first. query: words matched against titles and message text (FTS)."""
    kinds = ("quick", "thread", "task") if include_quick else ("thread", "task")
    marks = ",".join("?" * len(kinds))
    with _db() as db:
        if query.strip():
            terms = [t for t in re.findall(r"[\w']+", query.lower()) if t]
            match = " AND ".join(f'"{t}"*' for t in terms) or '""'
            rows = db.execute(
                f"SELECT t.*, COUNT(m.id) AS n FROM threads t LEFT JOIN messages m ON m.thread = t.id "
                f"WHERE t.kind IN ({marks}) AND (t.title LIKE ? OR t.id IN (SELECT m2.thread FROM messages_fts "
                f"JOIN messages m2 ON m2.id = messages_fts.rowid WHERE messages_fts MATCH ?)) "
                f"GROUP BY t.id ORDER BY t.updated DESC LIMIT ?", (*kinds, f"%{query.strip()}%", match, limit)).fetchall()
        else:
            rows = db.execute(f"SELECT t.*, COUNT(m.id) AS n FROM threads t LEFT JOIN messages m ON m.thread = t.id "
                              f"WHERE t.kind IN ({marks}) GROUP BY t.id ORDER BY t.updated DESC LIMIT ?",
                              (*kinds, limit)).fetchall()
    return [dict(r) for r in rows]


def thread_messages(tid, limit=200):
    with _db() as db:
        rows = db.execute("SELECT * FROM (SELECT * FROM messages WHERE thread = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
                          (tid, limit)).fetchall()
    out = [dict(r) for r in rows]
    for m in out:
        m["tools"] = json.loads(m["tools"] or "[]")
    return out


# ── tasks ──────────────────────────────────────
def add_task(title, prompt, thread=None, resumed_from=None):
    with _db() as db:
        return db.execute("INSERT INTO tasks(thread, title, prompt, status, created, resumed_from) VALUES (?,?,?,?,?,?)",
                          (thread, title[:120], prompt[:8000], "queued", time.time(), resumed_from)).lastrowid


def update_task(tid, **fields):
    allowed = {"thread", "status", "started", "finished", "result", "steps", "turns", "announce", "announced"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if not sets:
        return
    with _db() as db:
        db.execute(f"UPDATE tasks SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), tid))


def get_task(tid):
    with _db() as db:
        r = db.execute("SELECT * FROM tasks WHERE id = ?", (tid,)).fetchone()
    return dict(r) if r else None


def list_tasks(limit=30, status=None):
    with _db() as db:
        if status:
            rows = db.execute("SELECT * FROM tasks WHERE status = ? ORDER BY id", (status,)).fetchall()
        else:
            rows = db.execute("SELECT * FROM tasks ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


# ── watchers (core/watch.py runs them; mcp/screen_tools.py sets them up) ──
MAX_WATCHERS = 3
WATCH_LIVE = ("active", "paused")


def add_watcher(kind, target, label, condition, interval, hours, repeat=False, min_area=0.0005):
    now = time.time()
    with _db() as db:
        n = db.execute(f"SELECT COUNT(*) FROM watchers WHERE status IN {WATCH_LIVE}").fetchone()[0]
        if n >= MAX_WATCHERS:
            return None
        return db.execute("INSERT INTO watchers(kind, target, label, condition, interval, min_area, repeat, status, created, expires) "
                          "VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (kind, target, label[:120], condition[:300], float(interval), float(min_area), int(bool(repeat)),
                           "active", now, now + hours * 3600)).lastrowid


def update_watcher(wid, **fields):
    allowed = {"status", "checks", "calls", "last_check", "note", "result", "finished", "expires", "label"}
    sets = {k: v for k, v in fields.items() if k in allowed}
    if sets:
        with _db() as db:
            db.execute(f"UPDATE watchers SET {', '.join(f'{k} = ?' for k in sets)} WHERE id = ?", (*sets.values(), wid))


def get_watcher(wid):
    with _db() as db:
        r = db.execute("SELECT * FROM watchers WHERE id = ?", (wid,)).fetchone()
    return dict(r) if r else None


def list_watchers(live_only=False, limit=12):
    with _db() as db:
        if live_only:
            rows = db.execute(f"SELECT * FROM watchers WHERE status IN {WATCH_LIVE} ORDER BY id").fetchall()
        else:
            rows = db.execute(f"SELECT * FROM watchers ORDER BY status IN {WATCH_LIVE} DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(r) for r in rows]


def owed_announcements():
    """Tasks whose finished / failed / interrupted line hasn't been said yet, oldest first."""
    with _db() as db:
        rows = db.execute("SELECT * FROM tasks WHERE announce IS NOT NULL AND announced IS NULL ORDER BY finished, id").fetchall()
    return [dict(r) for r in rows]


def add_task_log(task, kind, text):
    with _db() as db:
        db.execute("INSERT INTO task_log(task, ts, kind, text) VALUES (?,?,?,?)", (task, time.time(), kind, text[:4000]))


def task_log(task, limit=200):
    with _db() as db:
        rows = db.execute("SELECT * FROM (SELECT * FROM task_log WHERE task = ? ORDER BY id DESC LIMIT ?) ORDER BY id",
                          (task, limit)).fetchall()
    return [dict(r) for r in rows]


# ── Claude usage ───────────────────────────────
def add_turns(source, turns):
    if turns:
        with _db() as db:
            db.execute("INSERT INTO claude_turns(ts, source, turns) VALUES (?,?,?)", (time.time(), source, int(turns)))


def _family(model):
    m = str(model or "").lower()
    return next((f for f in ("haiku", "sonnet", "opus") if f in m), m or "unknown")


def add_usage(source, msg):
    """Tokens from an Agent SDK ResultMessage (model_usage per model, else its usage block). Never raises."""
    try:
        rows = []
        mu = getattr(msg, "model_usage", None) or {}
        for model, u in mu.items():
            if isinstance(u, dict):
                rows.append((_family(model), int(u.get("inputTokens") or 0), int(u.get("outputTokens") or 0),
                             int(u.get("cacheReadInputTokens") or 0), int(u.get("cacheCreationInputTokens") or 0)))
        if not rows and isinstance(getattr(msg, "usage", None), dict):
            u = msg.usage
            rows.append((_family(getattr(msg, "model", "") or u.get("model", "")), int(u.get("input_tokens") or 0),
                         int(u.get("output_tokens") or 0), int(u.get("cache_read_input_tokens") or 0),
                         int(u.get("cache_creation_input_tokens") or 0)))
        rows = [r for r in rows if any(r[1:])]
        if rows:
            now = time.time()
            with _db() as db:
                db.executemany("INSERT INTO claude_usage(ts, source, model, input, output, cache_read, cache_write) "
                               "VALUES (?,?,?,?,?,?,?)", [(now, str(source or "?"), *r) for r in rows])
    except Exception:
        pass


def usage_since(ts):
    """Tokens since ts: {"total": {...}, "models": {family: {...}}, "requests": n}. input counts fresh input only;
    cache_read / cache_write are kept apart (the CLI's own system prompt mostly comes from the cache)."""
    with _db() as db:
        rows = db.execute("SELECT model, COUNT(*) AS n, SUM(input) AS i, SUM(output) AS o, SUM(cache_read) AS cr, "
                          "SUM(cache_write) AS cw FROM claude_usage WHERE ts >= ? GROUP BY model", (ts,)).fetchall()
    models, total = {}, {"input": 0, "output": 0, "cache_read": 0, "cache_write": 0, "requests": 0}
    for r in rows:
        d = {"input": r["i"] or 0, "output": r["o"] or 0, "cache_read": r["cr"] or 0, "cache_write": r["cw"] or 0,
             "requests": r["n"]}
        models[r["model"]] = d
        for k in total:
            total[k] += d[k]
    return {"total": total, "models": models}


def turns_today():
    import datetime as _dt
    start = _dt.datetime.combine(_dt.date.today(), _dt.time()).timestamp()
    with _db() as db:
        r = db.execute("SELECT COALESCE(SUM(turns), 0) AS n, COUNT(*) AS req, "
                       "COALESCE(SUM(CASE WHEN source = 'watch' THEN turns ELSE 0 END), 0) AS w, "
                       "COALESCE(SUM(CASE WHEN source = 'control' THEN turns ELSE 0 END), 0) AS c "
                       "FROM claude_turns WHERE ts >= ?", (start,)).fetchone()
    return {"turns": r["n"], "requests": r["req"], "watch": r["w"], "control": r["c"]}


# ── window control approvals (core/brain.py writes, mcp/control_tools.py takes) ──
def add_control_approval(token, plan, address, source, ttl=180):
    now = time.time()
    with _db() as db:
        db.execute("DELETE FROM control_approvals WHERE expires < ?", (now - 3600,))
        db.execute("INSERT INTO control_approvals(token, plan, address, source, created, expires) VALUES (?,?,?,?,?,?)",
                   (token, plan, address, source, now, now + ttl))


def take_control_approval(token, plan, address):
    """The approval for exactly this plan, if unused and fresh; marks it used (one plan, once). None otherwise."""
    now = time.time()
    with _db() as db:
        r = db.execute("UPDATE control_approvals SET used = ? WHERE token = ? AND plan = ? AND address = ? "
                       "AND used IS NULL AND expires >= ? RETURNING *", (now, str(token), plan, address, now)).fetchone()
    return dict(r) if r else None


def log_control(address, label, goal, steps, done, outcome, detail=""):
    with _db() as db:
        db.execute("INSERT INTO control_log(ts, address, label, goal, steps, done, outcome, detail) VALUES (?,?,?,?,?,?,?,?)",
                   (time.time(), address, label[:120], goal[:300], int(steps), int(done), outcome[:80], detail[:500]))


def list_control_log(limit=20):
    with _db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM control_log ORDER BY id DESC LIMIT ?", (limit,)).fetchall()]
