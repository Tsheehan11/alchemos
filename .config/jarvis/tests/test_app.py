#!/usr/bin/env python3
"""The JARVIS app's back end without Claude: conversations (quick → thread, idle split, resume),
confirmations, the Unix socket server (real socket, same-user check, ops, broadcast), the task
runner with a fake brain (two at once, cancel, restart → interrupted, resume, confirmations,
announcements), start_task, and a typed dry-run request through Jarvis.handle.
Run: python tests/test_app.py"""
import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp())
os.environ["JARVIS_DB"] = str(TMP / "jarvis.db")
import jarvis_db as db  # noqa: E402
from core import conversations as CV  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


def wait_for(cond, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


# ── conversations ──
events = []
conv = CV.Conversations(events.append, idle_s=0.5)
t1 = conv.record("hey jarvis, dim the lights", "voice", "Done, sir.", ["lights(action=dim)"], "fast")
check("one-off command → quick thread", db.get_thread(t1)["kind"], "quick")
check("title cleaned", db.get_thread(t1)["title"], "Dim the lights")
check("quick threads hidden by default", [t["id"] for t in db.list_threads()], [])
t1b = conv.record("and the desk lamp too", "typed", "Done.", [], "fast")
check("typed turn joins the voice thread", t1b, t1)
check("second turn → real thread", db.get_thread(t1)["kind"], "thread")
time.sleep(0.6)
t2 = conv.record("what's on my calendar", "voice", "x" * 300, ["calendar_today()"], "claude:haiku")
check("idle → new thread", t2 != t1, True)
check("long Claude answer → thread at once", db.get_thread(t2)["kind"], "thread")
check("search finds message text", [t["id"] for t in db.list_threads("lamp")], [t1])
hist = conv.resume(t1)
check("resume: transcript for the brain", hist.splitlines()[0], "Trevor: hey jarvis, dim the lights")
check("resume makes it current", conv.record("thanks", "voice", "You're welcome, sir.", [], "fast"), t1)
check("messages pushed live", sum(1 for e in events if e["ev"] == "message"), 8)
check("new thread announced as current", any(e == {"ev": "state", "current": t2} for e in events), True)
check("threads last 30 min by default", CV.Conversations().idle_s, 1800)
for said, want in [("new topic", True), ("Jarvis, new chat", True), ("let's start a new conversation", True),
                   ("new topic about rust", False), ("what's new", False)]:
    check(f"new-topic phrase {said!r}", bool(CV.NEW_TOPIC.match(said)), want)
c2 = CV.Conversations(idle_s=10)
check("restart: the live thread is current again", c2.current, t1)
c2.last = time.time() - 5
check("carry on after Claude's context dropped → last turns", c2.carry_on(context_idle_s=2).splitlines()[0],
      "Trevor: hey jarvis, dim the lights")
c2.last = time.time() - 1
check("still in Claude's context → nothing to replay", c2.carry_on(context_idle_s=2), "")
c2.new()
check("NEW → no current thread", c2.current, None)
check("title_from trims", CV.title_from("Could you go through all of my unread course emails and update the tracker for me please"),
      "Go through all of my unread course emails and update the…")

# ── the task-finished line ──
import core.tasks as TK  # noqa: E402
check("done line split off the summary", TK.split_done("You have nine items due.\nDONE: your tracker review for the next two weeks"),
      ("You have nine items due.", "your tracker review for the next two weeks"))
check("no done line", TK.split_done("All clear."), ("All clear.", ""))
check("natural opener", TK.finished_line("Your tracker review for the next two weeks."),
      "Sir, your tracker review for the next two weeks is done.")
check("failed opener", TK.finished_line("your inbox sweep", failed=True), "Sir, your inbox sweep didn't finish.")
for bad in ("", "tracker review", "your task of checking things", "your really very long description of the whole entire job here",
            "your <b>sweep</b>"):
    check(f"unclear → generic: {bad!r}", TK.finished_line(bad), "Sir, your background task is done.")
check("opener stays short", max(len(TK.finished_line(p).split()) for p in ("your a b c d e f g h", "your inbox sweep")) <= 12, True)

# ── confirmations ──
cf = CV.Confirmations(events.append)
p = cf.open("Shall I mark CS 137 A5 complete in your tracker, sir?", "task:1", "Tracker sweep")
check("pending listed", [x["id"] for x in cf.pending()], [p.id])
threading.Timer(0.1, lambda: cf.answer(p.id, True)).start()
check("answer wakes the waiter", p.wait(2), True)
check("answered twice is ignored", cf.answer(p.id, False), False)
q = cf.open("Shall I?", "typed")
cf.expire(q)
check("expired = no", (q.answered, q.result), (True, False))

# ── socket server ──
from core.appserver import AppServer  # noqa: E402

loop = asyncio.new_event_loop()
threading.Thread(target=loop.run_forever, daemon=True).start()
got_ops = []
srv = AppServer(loop, {"hello": lambda m: {"ev": "state", "ok": True},
                       "echo": lambda m: (got_ops.append(m), {"ev": "echo", "text": m.get("text")})[1]},
                path=TMP / "run" / "app.sock")
asyncio.run_coroutine_threadsafe(srv.start(), loop).result(5)
check("socket mode 0600", oct(os.stat(srv.path).st_mode & 0o777), "0o600")
check("dir mode 0700", oct(os.stat(srv.path.parent).st_mode & 0o777), "0o700")
c = socket.socket(socket.AF_UNIX)
c.connect(str(srv.path))
f = c.makefile("rw")
check("hello on connect", json.loads(f.readline()), {"ev": "state", "ok": True})
f.write(json.dumps({"op": "echo", "text": "hi"}) + "\n")
f.flush()
check("op dispatched", json.loads(f.readline()), {"ev": "echo", "text": "hi"})
f.write("not json\n{\"op\": \"nope\"}\n")
f.flush()
srv.broadcast({"ev": "message", "n": 1})
check("broadcast reaches client (bad lines ignored)", json.loads(f.readline()), {"ev": "message", "n": 1})
c.close()

# ── task runner with a fake brain ──
import core.tasks as TK  # noqa: E402
from core.brain import Reply  # noqa: E402


class FakeBrain:
    made = []

    def __init__(self, cfg, confirm, on_tool, **kw):
        self.confirm, self.on_tool, self.kw = confirm, on_tool, kw
        self.stop = asyncio.Event()
        FakeBrain.made.append(self)

    async def ask(self, text, on_sentence=None, source=None, model=None):
        if text == TK.NAME_ASK:                       # the follow-up naming the finished job
            return Reply(text="Your inbox sweep.", tier="claude:haiku")
        self.on_tool("GOOGLE → EMAIL UNREAD SUMMARY")
        if "approve" in text:
            ok = await self.confirm("Shall I mark CS 137 A5 complete in your tracker, sir?")
            self.on_tool("LEARN → TRACKER UPDATE" + ("" if ok else " [declined]"))
        if "slow" in text:
            try:
                await asyncio.wait_for(self.stop.wait(), 10)
            except asyncio.TimeoutError:
                pass
            r = Reply(text="", interrupted=True)
            return r
        on_sentence and on_sentence("Three course emails, one tracker update.")
        return Reply(text="Three course emails, one tracker update.", tier="claude:sonnet", tools=["email_search()"], turns=4)

    async def interrupt(self):
        self.stop.set()

    async def disconnect(self):
        pass


class Cfg(dict):
    def model_for(self, strong):
        return "sonnet"


TK.Brain = FakeBrain
pushed, said, asked = [], [], []
cf = CV.Confirmations(pushed.append)
paused = {"on": False}
tm = TK.TaskManager(Cfg(), loop, pushed.append, cf, ask_aloud=asked.append,
                    announce=lambda title, line, thread: said.append((title, line)), paused=lambda: paused["on"])
# a task left "running" by a previous Jarvis
old = db.add_task("Old job", "do something")
db.update_task(old, status="running", started=time.time())
asyncio.run_coroutine_threadsafe(tm.run_forever(), loop)
check("restart → interrupted", wait_for(lambda: db.get_task(old)["status"] == "interrupted"), True)

a = tm.start("Summarize week", "summarize my week")
check("task done", wait_for(lambda: db.get_task(a)["status"] == "done"), True)
ta = db.get_task(a)
check("result + turns + steps stored", (ta["result"], ta["turns"], ta["steps"]), ("Three course emails, one tracker update.", 4, 1))
check("task thread has prompt + result", [m["role"] for m in db.thread_messages(ta["thread"])], ["user", "jarvis"])
check("task thread kind", db.get_thread(ta["thread"])["kind"], "task")
check("announced", said[0][0], "TASK DONE")
check("announced in plain words, not the raw title", said[0][1], "Sir, your inbox sweep is done. Three course emails, one tracker update.")
check("live log lines pushed", any(e["ev"] == "task_line" and e["kind"] == "step" for e in pushed), True)
check("no start_task inside a task (brain source)", FakeBrain.made[-1].kw.get("source"), "task")

paused["on"] = True
b1, b2, b3 = tm.start("Slow one", "slow"), tm.start("Slow two", "slow"), tm.start("Slow three", "slow")
time.sleep(2.5)
check("combat mode: nothing starts", db.get_task(b1)["status"], "queued")
paused["on"] = False
check("two run at once", wait_for(lambda: len(tm.running) == 2), True)
time.sleep(2.2)
check("third waits", db.get_task(b3)["status"], "queued")
tm.cancel(b1)
check("cancel", wait_for(lambda: db.get_task(b1)["status"] == "cancelled"), True)
check("third starts when a slot frees", wait_for(lambda: db.get_task(b3)["status"] == "running"), True)
tm.cancel(b2)
check("cancel just as it starts is honoured", tm.cancel(b3), True)    # it used to be dropped: ran on, announced done
wait_for(lambda: not tm.running)
check("…and it ends cancelled", wait_for(lambda: db.get_task(b3)["status"] == "cancelled"), True)

c1 = tm.start("Tracker sweep", "approve something")
check("confirmation reaches app + voice", wait_for(lambda: bool(asked)), True)
check("pending in the app", [x["origin"] for x in cf.pending()], [f"task:{c1}"])
cf.answer(asked[0].id, True)
check("task finishes after yes", wait_for(lambda: db.get_task(c1)["status"] == "done"), True)
check("approval logged", any(x["text"] == "Approved." for x in db.task_log(c1)), True)

r = tm.resume(old)
check("resume queues a new run in the same thread", (db.get_task(r)["resumed_from"], db.get_task(r)["title"]), (old, "Old job"))
check("resume can't restart a finished task", tm.resume(a), None)
wait_for(lambda: db.get_task(r)["status"] == "done")

# ── announcements: always said, deferred not lost ──
class Toasts(list):
    def __call__(self, title, text):
        self.append((title, text))


spoken, toasts = [], Toasts()
ann = TK.Announcer(spoken.append, toasts)
for x in db.owed_announcements():                     # what the runs above left owed
    db.update_task(x["id"], announced=time.time())


class NamelessBrain(FakeBrain):                       # the naming turn hangs, then errors
    async def ask(self, text, on_sentence=None, source=None, model=None):
        if text == TK.NAME_ASK:
            raise RuntimeError("naming turn broke")
        return Reply(text="All five rows checked.", tier="claude:sonnet", turns=2)


TK.Brain = NamelessBrain
said.clear()
n1 = tm.start("Check rows", "check rows")
check("nameless task done", wait_for(lambda: db.get_task(n1)["status"] == "done"), True)
check("naming failed → generic line stored as owed", db.get_task(n1)["announce"],
      "Sir, your background task is done. All five rows checked.")
wait_for(lambda: said)        # status "done" is stored before the runner's last bookkeeping and its announce call
check("runner nudged the voice loop", [x[0] for x in said], ["TASK DONE"])
check("combat mode: deferred, still owed", (ann.deliver(paused=True), spoken), (0, []))
# Jarvis restarts during combat mode: a new announcer (fresh process) still finds it
ann2 = TK.Announcer(spoken.append, toasts)
check("after a restart it's spoken", ann2.deliver(), 1)
check("spoken line", spoken, ["Sir, your background task is done. All five rows checked."])
check("toast too", toasts[-1][0], "TASK DONE")
check("said once only", (ann2.deliver(), len(spoken)), (0, 1))

# speaking fails: retried, not dropped
db.update_task(n1, announced=None)
calls = {"n": 0}


def flaky(text):
    calls["n"] += 1
    if calls["n"] == 1:
        raise OSError("pw-play died")
    spoken.append(text)


clock = {"t": time.time()}
ann3 = TK.Announcer(flaky, toasts, log=lambda *a: None, clock=lambda: clock["t"])
check("speech failed → not marked said", (ann3.deliver(), db.get_task(n1)["announced"]), (0, None))
check("not retried before the back-off", ann3.deliver(), 0)
clock["t"] += max(TK.RETRY_S, TK.AWAY_S) + 1
check("retried later", ann3.deliver(), 1)
check("retry says it, from away", spoken[-1], "While I was away, sir: your background task is done. All five rows checked.")
db.update_task(n1, announced=None, finished=time.time() - TK.STALE_S - 10)
check("too old: not read out, but settled", (TK.Announcer(spoken.append, toasts).deliver(), db.get_task(n1)["announced"] is not None), (0, True))


class BrokenWrapUp(FakeBrain):                        # bookkeeping after the reply blows up
    async def ask(self, text, on_sentence=None, source=None, model=None):
        if text == TK.NAME_ASK:
            return Reply(text="Your grade check.")
        return Reply(text="Done looking.", tools=object(), turns=1)   # tools can't be stored → add_message raises


TK.Brain = BrokenWrapUp
n2 = tm.start("Grades", "grades")
check("wrap-up error still finishes", wait_for(lambda: db.get_task(n2)["status"] == "done"), True)
check("wrap-up error still owes a line", bool(db.get_task(n2)["announce"]), True)
check("…and it's said", (TK.Announcer(spoken.append, toasts).deliver(), spoken[-1].startswith("Sir, your grade check is done")), (1, True))

# queued during combat mode: the task says why it waits
TK.Brain = FakeBrain
paused["on"] = True
q1 = tm.start("Later", "summarize my week")
check("queued in combat mode is told why", wait_for(lambda: any("combat mode" in x["text"] for x in db.task_log(q1))), True)
paused["on"] = False
check("…and runs after", wait_for(lambda: db.get_task(q1)["status"] == "done"), True)
check("…and announces", wait_for(lambda: TK.Announcer(spoken.append, toasts).deliver() == 1 or
                                 db.get_task(q1)["announced"] is not None), True)

# restart mid-task → interrupted is announced too; resuming settles it
it = db.add_task("Mid job", "x")
db.update_task(it, status="running", started=time.time())
tm.recover()
check("interrupted owes a line", db.get_task(it)["announce"], TK.INTERRUPTED_LINE)
tm.resume(it)
check("resume settles it", db.get_task(it)["announced"] is not None, True)

# an old db without the columns: migrated, old rows not read out
import sqlite3  # noqa: E402
legacy = TMP / "legacy.db"
con = sqlite3.connect(legacy)
con.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY, thread INTEGER, title TEXT NOT NULL, prompt TEXT NOT NULL, "
            "status TEXT NOT NULL, created REAL NOT NULL, started REAL, finished REAL, result TEXT, "
            "steps INTEGER NOT NULL DEFAULT 0, turns INTEGER NOT NULL DEFAULT 0, resumed_from INTEGER)")
con.execute("INSERT INTO tasks(title, prompt, status, created, finished) VALUES ('old','p','done',1,2)")
con.commit()
con.close()
_path, db.DB_PATH, db._MIGRATED = db.DB_PATH, legacy, False
check("legacy db migrated, nothing owed", db.owed_announcements(), [])
db.DB_PATH = _path

# ── start_task tool ──
import stark_actions as A  # noqa: E402
res = A.start_task("Inbox sweep", "Go through my unread course emails and update the tracker.")
check("start_task queues", (res["ok"], db.get_task(res["task"])["status"] in ("queued", "running", "done")), (True, True))
check("start_task needs instructions", A.start_task("x", "")["ok"], False)
check("start_task label", A.tool_label("start_task", {"title": "inbox sweep"}), "TASK → INBOX SWEEP")
wait_for(lambda: db.get_task(res["task"])["status"] == "done")

# ── a typed request through Jarvis.handle (dry run, fast path) ──
import jarvis as JV  # noqa: E402
from core import config as C  # noqa: E402

JV.hud.ENABLED = False
j = JV.Jarvis(C.Config(), dry_run=True, confirm_sync=lambda p: (_ for _ in ()).throw(AssertionError("voice confirm used")))
seen = []
j.notify = seen.append
reply = j.handle("pause the music", source="typed", confirm=lambda p: True)
check("typed fast-path reply", bool(reply), True)
check("typed request recorded with source", db.thread_messages(j.conv.current)[-2]["source"], "typed")
check("busy on/off pushed", [e["on"] for e in seen if e["ev"] == "busy"], [True, False])
check("tool label went to the app, not the HUD surface", any(e["ev"] == "tool" for e in seen), True)
for th in j.learning:
    th.join(10)

check("turns today counts", db.turns_today()["turns"] >= 0, True)

# ── "stop" while Jarvis works a window (stage 4): lets go, never "stop the music" ──
from core import control as K  # noqa: E402
for said, want in (("stop", True), ("Jarvis, stop", True), ("stop it!", True), ("hands off", True), ("stop clicking", True),
                   ("stop the music", False), ("stop the vpn", False), ("stop watching discord", False)):
    check(f"stop phrase: {said}", bool(JV.STOP_CONTROL.match(said)), want)
K.STOP_FLAG = TMP / "control-stop"
K.STATE_FILE = TMP / "control.json"
K.STATE_FILE.write_text(json.dumps({"pid": os.getpid(), "address": "0x1"}))
_popen, K.subprocess.Popen = K.subprocess.Popen, lambda *a, **k: None
t0 = time.time() - 0.01
reply = j.handle("stop", source="typed", confirm=lambda p: True)
K.subprocess.Popen = _popen
check("'stop' lets go of the window", reply, "Stopped, sir. I've let go of the window.")
check("…and sets the kill flag", K.stopped_since(t0), True)
K.STATE_FILE.unlink()
check("spoken prompt is the plan's first line", JV.spoken_prompt("Take control?\nPLAN · x\n1. Click"), "Take control?")
check("allow this task heard", bool(JV.ALLOW_TASK.search("allow this task")), True)
print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all app tests passed'}")
sys.stdout.flush()
os._exit(1 if FAILS else 0)
