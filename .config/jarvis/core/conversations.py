"""
Conversations for the JARVIS app (jarvis_db threads + messages).

One conversation = one thread. Voice and typed turns land in whichever thread is current; a new
one starts only after THREAD_IDLE_S (30 min) of quiet, when he presses NEW THREAD or says "new
topic" / "new chat", or when he reopens an old thread (resume). Claude's own context drops sooner
(CONTEXT_IDLE_S); carrying on in the thread after that replays its last turns (transcript()).
Background tasks have threads of their own and never change which thread is current. A thread starts as kind "quick" (hidden
from the app's list by default: "dim the lights") and becomes a real "thread" once it is a
conversation (a second turn) or real work (Claude used two or more tools, or answered at length).

Pending confirmations live here too: a typed request or a background task asking "Shall I …?"
is shown in the app with YES / NO, and the voice loop may also ask it out loud; the first answer wins.
"""
import itertools
import re
import threading
import time

import jarvis_db as db  # noqa: E402  (mcp/ is on sys.path; see jarvis.py)

from . import config as C

LONG_REPLY = 240
NEW_TOPIC = re.compile(r"^\s*(?:(?:hey|ok|okay)\s+)?(?:jarvis[,.!]?\s*)?(?:let'?s\s+)?(?:start\s+(?:a\s+)?)?"
                       r"(?:new|fresh)\s+(?:topic|chat|conversation|thread)(?:\s+please)?[.!]?\s*$", re.I)


def title_from(text, limit=60):
    t = re.sub(r"^\s*(?:(?:hey|ok|okay)\s+)?jarvis[,.!]?\s*", "", text.strip(), flags=re.I)
    t = re.sub(r"^(?:please|can you|could you|would you)\s+", "", t, flags=re.I).strip(" ?.!")
    t = " ".join(t.split())
    if len(t) > limit:
        t = t[:limit].rsplit(" ", 1)[0] + "…"
    return (t[:1].upper() + t[1:]) or "Conversation"


class Conversations:
    def __init__(self, notify=lambda ev: None, idle_s=C.THREAD_IDLE_S):
        self.notify = notify
        self.idle_s = idle_s
        self.lock = threading.Lock()
        self.current = None
        self.kind = None
        self.turns = 0
        self.last = 0.0
        self._restore()

    def _restore(self):
        """After a restart (dock, crash, update) carry on in the conversation that was going on, if it
        was active within idle_s; Claude gets its last turns with the next request (carry_on)."""
        try:
            latest = next((t for t in db.list_threads(include_quick=True, limit=10) if t["kind"] != "task"), None)
        except Exception:
            return
        if latest and time.time() - latest["updated"] < self.idle_s:
            self.current, self.kind, self.last = latest["id"], latest["kind"], latest["updated"]
            self.turns = sum(1 for m in db.thread_messages(latest["id"], limit=200) if m["role"] == "user")

    def new(self):
        with self.lock:
            self.current = None
        self.notify({"ev": "state", "current": None})

    def carry_on(self, context_idle_s=C.CONTEXT_IDLE_S):
        """The current thread's last turns, if the next turn continues it after Claude's context has
        dropped (quiet longer than context_idle_s, but the thread is still live); else ""."""
        with self.lock:
            tid, gap = self.current, time.time() - self.last
        if tid is None or gap <= context_idle_s or gap > self.idle_s:
            return ""
        return self.transcript(tid)

    @staticmethod
    def transcript(tid, limit=12):
        msgs = db.thread_messages(tid, limit=limit)
        lines = [f"{'Trevor' if m['role'] == 'user' else 'Jarvis'}: {m['text'][:400]}" for m in msgs]
        return "\n".join(lines)[-3000:]

    def resume(self, tid):
        """Make an old thread current. Returns a short transcript for the brain (data only)."""
        t = db.get_thread(tid)
        if not t:
            raise ValueError(f"no thread {tid}")
        msgs = db.thread_messages(tid, limit=12)
        with self.lock:
            self.current, self.kind, self.last = tid, t["kind"], time.time()
            self.turns = sum(1 for m in msgs if m["role"] == "user")
        self.notify({"ev": "state", "current": tid})
        return self.transcript(tid)

    def record(self, text, source, reply, tools=(), tier=""):
        """One exchange → messages in the current thread (a new one if it went idle)."""
        now = time.time()
        with self.lock:
            if self.current is None or now - self.last > self.idle_s:
                self.current, self.kind, self.turns = db.new_thread(title_from(text), "quick"), "quick", 0
                created = True
            else:
                created = False
            tid = self.current
            self.turns += 1
            self.last = now
            promote = self.kind == "quick" and (
                self.turns >= 2 or (tier.startswith("claude") and (len(tools) >= 2 or len(reply or "") > LONG_REPLY)))
            if promote:
                self.kind = "thread"
        if promote:
            db.update_thread(tid, kind="thread")
        u = db.add_message(tid, "user", source, text)
        msgs = [u]
        if reply is not None:
            msgs.append(db.add_message(tid, "jarvis", source, reply or "", tools, tier))
        thread = db.get_thread(tid)
        if created or promote:
            self.notify({"ev": "thread", "item": thread})
        if created:
            self.notify({"ev": "state", "current": tid})
        for m in msgs:
            self.notify({"ev": "message", "item": m, "thread": thread})
        return tid


class Pending:
    _ids = itertools.count(1)

    def __init__(self, prompt, origin, title=""):
        self.id = next(self._ids)
        self.prompt, self.origin, self.title = prompt, origin, title
        self.result = None
        self.event = threading.Event()
        self.voice_asked = False
        # a window-control plan in a background task can be answered "allow this task" (core/brain.py)
        self.allow_task = origin.startswith("task:") and "\nPLAN · " in prompt

    def wait(self, timeout):
        """True / False, or "task" ("allow this task", which is also a yes)."""
        self.event.wait(timeout)
        return self.result if self.result == "task" else bool(self.result)

    @property
    def answered(self):
        return self.event.is_set()

    def item(self):
        return {"id": self.id, "prompt": self.prompt, "origin": self.origin, "title": self.title, "allow_task": self.allow_task}


class Confirmations:
    def __init__(self, notify=lambda ev: None):
        self.notify = notify
        self.open_ = {}
        self.lock = threading.Lock()

    def open(self, prompt, origin, title=""):
        p = Pending(prompt, origin, title)
        with self.lock:
            self.open_[p.id] = p
        self.notify({"ev": "confirm", "item": p.item()})
        return p

    def answer(self, pid, yes):
        with self.lock:
            p = self.open_.pop(pid, None)
        if p and not p.answered:
            p.result = "task" if yes == "task" and p.allow_task else bool(yes)
            p.event.set()
            self.notify({"ev": "confirm_done", "id": pid, "yes": bool(yes)})
        return p is not None

    def expire(self, p):
        self.answer(p.id, False)

    def pending(self):
        with self.lock:
            return [p.item() for p in self.open_.values()]


def app_data(argv):
    """jarvis app-data threads [QUERY] [--quick] | thread ID | tasks | task ID: JSON for the app while
    the voice process isn't running (undocked): history stays readable."""
    import json
    cmd, rest = (argv[0] if argv else ""), argv[1:]
    quick = "--quick" in rest
    rest = [a for a in rest if a != "--quick"]
    if cmd == "threads":
        out = {"ev": "threads", "q": " ".join(rest), "quick": quick, "items": db.list_threads(" ".join(rest), quick)}
    elif cmd == "thread" and rest:
        out = {"ev": "messages", "thread": db.get_thread(int(rest[0])), "items": db.thread_messages(int(rest[0]))}
    elif cmd == "tasks":
        out = {"ev": "tasks", "items": db.list_tasks(30)}
    elif cmd == "task" and rest:
        out = {"ev": "task_log", "id": int(rest[0]), "items": db.task_log(int(rest[0]))}
    elif cmd == "watchers":
        out = {"ev": "watchers", "items": [dict(w, offline=True) for w in db.list_watchers()]}
    elif cmd == "usage":
        out = {"ev": "usage", **db.turns_today()}
    else:
        print("usage: jarvis app-data threads [QUERY] [--quick] | thread ID | tasks | task ID | watchers | usage")
        return 2
    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0
