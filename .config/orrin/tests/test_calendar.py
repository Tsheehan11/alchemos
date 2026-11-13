#!/usr/bin/env python3
"""Calendar writes, without the network: an in-memory fake of the Calendar API stands in for Google.
Covers CalendarWriter (main calendar only, subscribed / read-only calendars explained, every write
logged, undo of create / update / delete and its refusal once he changed the event), the sheet's own
events (format and style learned from the calendar, a moved row's event moved rather than duplicated,
ticks, new rows, removed rows, duplicate copies only reported), the tracker keeping its events in
step (and undo putting both back), the gate (calendar writes and deletes always ask) and the tools.
Run: python tests/test_calendar.py"""
import json
import os
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp())
os.environ["ORRIN_DB"] = str(TMP / "orrin.db")
import google_api as G  # noqa: E402
import orrin_db as db  # noqa: E402
import sheet_calendar as SC  # noqa: E402
import tracker as T  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


store = {("google", "tracker_sheet"): "SHEET", ("google", "token"): "x", ("google", "assignments_calendar"): "stark",
         ("google", "granted"): json.dumps([G.NEEDS["sheets"], G.NEEDS["calendar_write"]])}
G.secrets.get = lambda s, a: store.get((s, a))
G.secrets.has = lambda s, a: (s, a) in store
TODAY = date(2026, 10, 30)


class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, **kw):
        return self.fn()


def http(status, reason):
    from googleapiclient.errors import HttpError

    class Resp(dict):
        pass
    r = Resp()
    r.status = status
    return HttpError(r, json.dumps({"error": {"message": reason, "errors": [{"reason": reason}]}}).encode())


class FakeCalendar:
    """calendarList + events for a few calendars; deleted events linger as cancelled, as Google's do."""

    def __init__(self):
        self.cals = [{"id": "me@gmail.com", "summary": "me@gmail.com", "primary": True, "accessRole": "owner"},
                     {"id": "flow@import.calendar.google.com", "summary": "UW Flow schedule", "accessRole": "reader"},
                     {"id": "family", "summary": "Family", "accessRole": "owner"},
                     {"id": "stark", "summary": "STARK – Assignments", "accessRole": "owner"}]
        self.ev = {c["id"]: {} for c in self.cals}
        self.n = 0
        self.calls = []

    def add(self, cid, **e):
        self.n += 1
        e = dict(e, id=f"e{self.n}", status="confirmed")
        self.ev[cid][e["id"]] = e
        return e

    def calendarList(self):
        return self

    def events(self):
        return self

    def list(self, calendarId=None, maxResults=None, fields=None, q=None, pageToken=None, **kw):
        if calendarId is None:
            return Req(lambda: {"items": [dict(c) for c in self.cals]})
        items = [dict(e) for e in self.ev[calendarId].values() if e["status"] != "cancelled"]
        if q:
            items = [e for e in items if q.lower() in e.get("summary", "").lower()]
        return Req(lambda: {"items": items})

    def get(self, calendarId, eventId):
        def go():
            if eventId not in self.ev[calendarId]:
                raise http(404, "notFound")
            return json.loads(json.dumps(self.ev[calendarId][eventId]))
        return Req(go)

    def _writable(self, cid):
        if next(c for c in self.cals if c["id"] == cid)["accessRole"] not in ("owner", "writer"):
            raise http(403, "requiredAccessLevel")

    def insert(self, calendarId, body):
        def go():
            self._writable(calendarId)
            self.calls.append(("insert", calendarId, body.get("summary")))
            return dict(self.add(calendarId, **json.loads(json.dumps(body))))
        return Req(go)

    def patch(self, calendarId, eventId, body):
        def go():
            self._writable(calendarId)
            self.calls.append(("patch", calendarId, eventId, sorted(body)))
            self.ev[calendarId][eventId].update(json.loads(json.dumps(body)))
            return dict(self.ev[calendarId][eventId])
        return Req(go)

    def delete(self, calendarId, eventId):
        def go():
            self._writable(calendarId)
            self.calls.append(("delete", calendarId, eventId))
            self.ev[calendarId][eventId]["status"] = "cancelled"
            return ""
        return Req(go)


def sheet_event(cal, course, title, day, status="Not Started", kind="Assignment"):
    done = status == "Complete"
    return cal.add("me@gmail.com", summary=("✓ " if done else "") + f"[{course}] {title}",
                   description=f"Course: {course}\nType: {kind}\nStatus: {status}",
                   start={"date": day.isoformat()}, end={"date": (day + timedelta(days=1)).isoformat()},
                   colorId="10" if done else "11", eventLabelId="LBL-done" if done else "LBL-todo",
                   reminders={"useDefault": False, "overrides": [{"method": "popup", "minutes": 420}]})


REAL_WRITER = G.CalendarWriter


def writer(cal, source="voice", link=None):
    return REAL_WRITER(source, link=link, svc=cal, db=db)


def use(cal):
    """Point code that builds its own CalendarWriter (tracker undo, the tools) at the fake."""
    G.CalendarWriter = lambda source="voice", link=None, **kw: REAL_WRITER(source, link=link, svc=cal, db=db)


# ── CalendarWriter: which calendars ──
cal = FakeCalendar()
w = writer(cal)
check("main calendar resolved", w.check("primary"), ("me@gmail.com", "me@gmail.com"))
for cid, kind, words in [("flow@import.calendar.google.com", "readonly", "subscribed, read-only"),
                         ("family", "forbidden", "only edit your main calendar")]:
    try:
        w.check(cid)
        check(f"refused {cid}", "allowed", kind)
    except G.GoogleError as e:
        check(f"refused {cid}", (e.kind, words in e.say), (kind, True))
check("STARK – Assignments allowed (cleanup)", w.check("stark")[0], "stark")
check("google 403 on a calendar write → readonly", G.translate("calendar_write", 403, json.dumps(
    {"error": {"message": "x", "errors": [{"reason": "requiredAccessLevel"}]}}).encode()).kind, "readonly")

# ── create / update / delete, logged, undone ──
made = w.create("primary", {"summary": "Dentist", "start": {"dateTime": "2026-11-03T15:00:00-05:00"},
                            "end": {"dateTime": "2026-11-03T16:00:00-05:00"}})
w2 = writer(cal)
w2.update("primary", made["id"], {"summary": "Dentist (moved)", "start": {"dateTime": "2026-11-04T15:00:00-05:00"},
                                  "end": {"dateTime": "2026-11-04T16:00:00-05:00"}})
check("update logged before → after", [(x["kind"], x["old"]["summary"], x["new"]["summary"]) for x in db.calendar_writes(1)],
      [("update", "Dentist", "Dentist (moved)")])
check("no-op update writes nothing", writer(cal).update("primary", made["id"], {"summary": "Dentist (moved)"}), None)
ok, msg = writer(cal, "undo").undo()
check("undo the move", (ok, cal.ev["me@gmail.com"][made["id"]]["summary"]), (True, "Dentist"))
ok, msg = writer(cal, "undo").undo()
check("undo the create deletes it", (ok, cal.ev["me@gmail.com"][made["id"]]["status"]), (True, "cancelled"))

keep = cal.add("me@gmail.com", summary="Lunch", start={"date": "2026-11-05"}, end={"date": "2026-11-06"})
w3 = writer(cal)
check("delete", w3.delete("primary", keep["id"]), True)
ok, msg = writer(cal, "undo").undo()
check("undo the delete restores it (same event)", (ok, cal.ev["me@gmail.com"][keep["id"]]["status"]), (True, "confirmed"))

w4 = writer(cal)
w4.update("primary", keep["id"], {"summary": "Lunch with Sam"})
cal.ev["me@gmail.com"][keep["id"]]["summary"] = "Lunch with Sam and Alex"       # he edited it afterwards
ok, msg = writer(cal, "undo").undo()
check("undo refused once he changed it", (ok, "changed since" in msg), (False, True))
try:
    writer(cal).create("flow@import.calendar.google.com", {"summary": "x"})
    check("no write to a subscribed calendar", "written", "refused")
except G.GoogleError as e:
    check("no write to a subscribed calendar", (e.kind, cal.calls[-1][0] if cal.calls else None) != ("readonly", "insert"), True)

# ── the sheet's own events ──
cal = FakeCalendar()
a4 = sheet_event(cal, "CS 137", "Assignment A4 - Arrays and pointers", date(2026, 10, 30))
sheet_event(cal, "MATH 135", "Weekly assessment W5 (quiz)", date(2026, 10, 28), "Complete", "Assessment")
t5 = sheet_event(cal, "MATH 117", "Tutorial assignment 5", date(2026, 10, 29))
sc = SC.SheetCalendar(writer(cal, "tracker"), today=TODAY)
row = {"course": "CS 137", "title": "Assignment A4 - Arrays and pointers", "due": date(2026, 10, 30), "type": "Assignment",
       "status": "Not Started"}
done = dict(row, due=date(2026, 10, 20), status="Complete")
check("script colours", [SC.color(dict(row, status=st, type=ty)) for st, ty in
                         [("Complete", "Assessment"), ("In Progress", "Assignment"), ("Not Started", "Assessment"), ("Not Started", "Assignment")]],
      ["10", "5", "3", "11"])
check("script status text", [SC.display_status(x) for x in ("Not Started", "In Progress", "Complete", "")],
      ["Not started", "In progress", "Complete", "Not Started"])
r = sc.follow(row, done)
e = cal.ev["me@gmail.com"][a4["id"]]
check("A4: moved + ticked in the script's format", (e["summary"], e["start"], e["end"], e["description"], e["colorId"]),
      ("✓ [CS 137] Assignment A4 - Arrays and pointers", {"date": "2026-10-20"}, {"date": "2026-10-21"},
       "Course: CS 137\nType: Assignment\nStatus: Complete", "10"))
check("A4: one event, not two", sum(1 for x in cal.ev["me@gmail.com"].values() if "A4" in x["summary"]), 1)
check("A4: said", r["did"], ["moved its calendar event to Tuesday, October 20"])

py = {"course": "MATH 115", "title": "Python assignment 2", "due": date(2026, 10, 30), "type": "Assignment", "status": "Complete"}
r = sc.follow(None, py)
made = [x for x in cal.ev["me@gmail.com"].values() if "Python" in x["summary"]]
check("new row → one event, ticked, all day, the usual reminder", [(x["summary"], x["start"], x["colorId"], x["reminders"]) for x in made],
      [("✓ [MATH 115] Python assignment 2", {"date": "2026-10-30"}, "10",
        {"useDefault": False, "overrides": [{"method": "popup", "minutes": 420}]})])
check("following the same row again changes nothing", (sc.follow(py, py)["did"], len(made)), ([], 1))

t5row = {"course": "MATH 117", "title": "Tutorial assignment 5", "due": date(2026, 11, 5), "type": "Assignment", "status": "Not Started"}
r = sc.follow(t5row, None)
check("removed row → its event deleted", (cal.ev["me@gmail.com"][t5["id"]]["status"], r["did"]),
      ("cancelled", ["deleted its calendar event on Thursday, October 29"]))

dup = sheet_event(cal, "CS 137", "Assignment A4 - Arrays and pointers", date(2026, 10, 30))
sc = SC.SheetCalendar(writer(cal, "tracker"), today=TODAY)
r = sc.follow(done, dict(done, status="In Progress"))
check("a second copy is reported, never deleted unasked", (cal.ev["me@gmail.com"][dup["id"]]["status"], len(r["notes"])), ("confirmed", 1))
check("the copy on the row's own date was the one updated (yellow, script's status text)",
      (cal.ev["me@gmail.com"][a4["id"]]["summary"], cal.ev["me@gmail.com"][a4["id"]]["colorId"],
       cal.ev["me@gmail.com"][a4["id"]]["description"].split("Status: ")[1]),
      ("[CS 137] Assignment A4 - Arrays and pointers", "5", "In progress"))

# ── the tracker keeps them in step ──
import fakes_sheet as F  # noqa: E402

cal = FakeCalendar()
a5 = sheet_event(cal, "CS 137", "Assignment A5 - Structures and strings", F.TODAY + timedelta(days=2))
fs = F.sheet()
t = T.Tracker(svc=fs, sheet_id="SHEET", db=db)
rows = t.load()
changes, _ = T.plan_update(rows, "CS 137", "A5", due=F.TODAY + timedelta(days=5), strict=False)
t.apply(changes, "voice", calendar=SC.SheetCalendar(writer(cal, "tracker"), today=F.TODAY))
check("tracker due change moved its event", cal.ev["me@gmail.com"][a5["id"]]["start"], {"date": (F.TODAY + timedelta(days=5)).isoformat()})
check("the calendar batch is linked to the tracker batch", db.calendar_writes(1)[0]["link"], t.batch)
use(cal)
ok, msg = T.Tracker(svc=fs, sheet_id="SHEET", db=db).undo()
check("tracker undo puts the event back too", (ok, cal.ev["me@gmail.com"][a5["id"]]["start"]),
      (True, {"date": (F.TODAY + timedelta(days=2)).isoformat()}))

t = T.Tracker(svc=fs, sheet_id="SHEET", db=db)
r6 = T.find(t.load(), "CS 137", "A5")[0]
res = t.apply([T.change_remove(r6)], "voice", calendar=SC.SheetCalendar(writer(cal, "tracker"), today=F.TODAY))
check("remove: row gone, event deleted", (res[0]["ok"], [x["title"] for x in t.rows if x["course"] == "CS 137"],
                                          cal.ev["me@gmail.com"][a5["id"]]["status"]),
      (True, ["Assignment A4 - Arrays and pointers"], "cancelled"))
ok, msg = T.Tracker(svc=fs, sheet_id="SHEET", db=db).undo()
t = T.Tracker(svc=fs, sheet_id="SHEET", db=db)
back = T.find(t.load(), "CS 137", "A5")
check("undo remove: row back in date order with its cells, event restored",
      (ok, [x["row"] for x in back], fs.grid[back[0]["row"] - 1][:7] if back else None, cal.ev["me@gmail.com"][a5["id"]]["status"]),
      (True, [6], ["CS 137", "Assignment A5 - Structures and strings", F.serial(F.TODAY + timedelta(days=2)), "", "",
                   "Assignment", "Not Started"], "confirmed"))
che = T.find(t.rows, "CHE 102", "Assignment 3")[0]
res = t.apply([T.change_remove(che)], "voice")
check("remove refuses a row holding a formula", (res[0]["ok"], "formula" in res[0]["error"]), (False, True))
store[("google", "granted")] = json.dumps([G.NEEDS["sheets"]])
t = T.Tracker(svc=fs, sheet_id="SHEET", db=db)
changes, _ = T.plan_update(t.load(), "CS 137", "A5", status="In Progress", strict=False)
t.apply(changes, "voice", calendar=True)
check("no calendar scope: sheet written, told to reconnect", (fs.cell(6, 7), "orrin connect google" in t.calendar_report["notes"][0]),
      ("In Progress", True))
store[("google", "granted")] = json.dumps([G.NEEDS["sheets"], G.NEEDS["calendar_write"]])
G.CalendarWriter = REAL_WRITER

# ── the gate ──
from core.brain import ALWAYS_ASK, integration_prompt  # noqa: E402
check("calendar writes always ask", {"calendar_create_event", "calendar_update_event", "calendar_delete_event", "tracker_remove"} <= ALWAYS_ASK, True)
check("prompt: delete", integration_prompt("Google", "calendar_delete_event", {"ref": "x|y", "current_title": "Dentist"}),
      "Delete Dentist from your calendar, sir?")
check("prompt: move", integration_prompt("Google", "calendar_update_event", {"ref": "x|y", "current_title": "Dentist",
                                                                            "start": "2026-11-04T15:00"}),
      "Change Dentist on your calendar: move it to Wednesday, November 4 at 3 PM, sir?")
check("prompt: create all day", integration_prompt("Google", "calendar_create_event", {"title": "Hackathon", "start": "2026-11-07"}),
      "Add Hackathon to your calendar on Saturday, November 7, sir?")
check("prompt: remove row", integration_prompt("LEARN", "tracker_remove", {"course": "MATH 117", "assignment": "Tutorial 5"}),
      "Remove MATH 117 Tutorial 5 from your tracker and delete its calendar event, sir?")

# ── the tools ──
import google_tools as GT  # noqa: E402

cal = FakeCalendar()
den = cal.add("me@gmail.com", summary="Dentist", start={"dateTime": "2026-11-03T15:00:00-05:00"}, end={"dateTime": "2026-11-03T16:00:00-05:00"})
lec = cal.add("flow@import.calendar.google.com", summary="CS137 - LEC 001", start={"dateTime": "2026-11-03T10:30:00-05:00"},
              end={"dateTime": "2026-11-03T11:20:00-05:00"})
use(cal)
r = json.loads(GT.calendar_update_event(f"me@gmail.com|{den['id']}", "Dentist", start="2026-11-04T15:00"))
check("tool: move keeps the length", (r["ok"], cal.ev["me@gmail.com"][den["id"]]["end"]["dateTime"][:16]), (True, "2026-11-04T16:00"))
r = json.loads(GT.calendar_delete_event(f"me@gmail.com|{den['id']}", "Lunch"))
check("tool: wrong title refused", (r["ok"], cal.ev["me@gmail.com"][den["id"]]["status"]), (False, "confirmed"))
r = json.loads(GT.calendar_update_event(f"flow@import.calendar.google.com|{lec['id']}", "CS137 - LEC 001", start="2026-11-04T10:30"))
check("tool: subscribed calendar explained", (r["ok"], r.get("kind"), "subscribed" in r["say"]), (False, "readonly", True))
r = json.loads(GT.calendar_create_event("Hackathon", "2026-11-07"))
check("tool: create all-day", (r["ok"], [x["start"] for x in cal.ev["me@gmail.com"].values() if x["summary"] == "Hackathon"]),
      (True, [{"date": "2026-11-07"}]))
r = json.loads(GT.calendar_create_event("Bad", "next tuesday"))
check("tool: bad time", (r["ok"], r["say"]), (False, "I didn't understand that time, sir."))
G.CalendarWriter = REAL_WRITER

print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all calendar tests passed'}")
sys.exit(1 if FAILS else 0)
