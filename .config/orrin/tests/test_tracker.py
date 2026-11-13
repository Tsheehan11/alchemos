#!/usr/bin/env python3
"""The SE tracker sheet, without the network: an in-memory fake of the Sheets API stands in for
Google. Covers the layout parser, row matching on real-style titles, the write rules (RAW values,
no formula / header cells, re-located rows, sorted inserts that inherit formatting), undo, the
one-spreadsheet guard, event planning (grade notice, LEARN feed, course email), the sync pass with
AUTO-UPDATE TRACKER on and off, the calendar fallback, the gate's prompt and the MCP tools.
Run: python tests/test_tracker.py"""
import json
import os
import re
import sys
import tempfile
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
TMP = Path(tempfile.mkdtemp())
os.environ["ORRIN_DB"] = str(TMP / "orrin.db")
import academic  # noqa: E402
import academic_sync as S  # noqa: E402
import google_api as G  # noqa: E402
import orrin_db as db  # noqa: E402
import tracker as T  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


academic.STATE_FILE = TMP / "academic.json"
store = {("google", "tracker_sheet"): "SHEET", ("google", "token"): "x",
         ("google", "granted"): json.dumps([G.NEEDS["sheets"]])}
G.secrets.get = lambda s, a: store.get((s, a))
G.secrets.has = lambda s, a: (s, a) in store
TODAY = date.today()


from fakes_sheet import HEAD, FakeSheet, Req, serial, sheet  # noqa: E402,F401


REAL_TRACKER = T.Tracker


def tracker_for(fs):
    return REAL_TRACKER(svc=fs, sheet_id="SHEET", db=db)


# ── names and matching ──
for title, want in [("Assignment A5 - Structures and strings", "a5"), ("CS137_a5", "a5"), ("A5", "a5"),
                    ("assignment 5", "a5"), ("Weekly assessment W3 (Crowdmark)", "w3"), ("Complete Assignment W3", "w3"),
                    ("Tutorial assignment 4", "tut4"), ("Tutorial 4 - Reaction rates", "tut4"), ("Python assignment 2", "py2"),
                    ("Bonus Quiz 2 - Forms of Violation", "bq2"), ("Assignment 3: Rates of Reaction", "a3"),
                    ("Lab 4 - Test planning", "lab4"), ("Midterm exam", "midterm"), ("Charter and product backlog", None)]:
    check(f"ident {title!r}", T.ident(title), want)
check("deliverable: CS137_a6", T.is_deliverable("CS137_a6"), True)
check("not deliverable: lecture slides", T.is_deliverable("9_Linked Lists - Available"), False)
check("not deliverable: provided code", T.is_deliverable("a5 provided code - Available"), False)
check("not deliverable: course outline", T.is_deliverable("Read the Course Outline"), False)

fs = sheet()
layout, rows = T.parse(fs.grid)
check("layout header row", layout["header"], 3)
check("layout columns", layout["cols"], {"course": 0, "title": 1, "due": 2, "days": 3, "difficulty": 4, "type": 5, "status": 6, "grade": 7})
check("rows parsed", [r["row"] for r in rows], [4, 5, 6, 7, 8, 9])
check("serial → date", rows[2]["due"], TODAY + timedelta(days=2))
check("find CS137_a5 (feed)", [r["row"] for r in T.find(rows, "CS 137", "CS137_a5")], [6])
check("find 'Complete Assignment W6' (feed)", [r["row"] for r in T.find(rows, "MATH 135", "Complete Assignment W6")], [7])
check("strict: 'A6' isn't W6", T.find(rows, "MATH 135", "A6"), [])
check("loose: spoken 'MATH 135 A6' → W6", [r["row"] for r in T.find(rows, "math135", "A6", strict=False)], [7])
check("other course never matches", T.find(rows, "CS 137", "W6", strict=False), [])
check("insert position keeps due order", T.insert_at(layout, rows, TODAY + timedelta(days=3)), 7)
check("insert position for no date: after the undated", T.insert_at(layout, rows, None), 9)
soon, late = T.pending(rows, 7)
check("pending this week", [r["row"] for r in soon], [6, 7, 8])
check("overdue", [r["row"] for r in late], [5])
check("status words", [T.status_name(x) for x in ("done", "finished", "in progress", "nope")], ["Complete", "Complete", "In Progress", None])
check("score from snippet 18/20", T.score_percent("Your grade for Assignment 5 is 18/20"), 90.0)
check("score from snippet 85%", T.score_percent("Score: 85% on W6"), 85.0)
check("no score without grade words", T.score_percent("Room 18/20 is booked"), None)
check("clean title strips formula chars", T.clean_title("=HYPERLINK(\"x\")"), 'HYPERLINK("x")')

# ── writes ──
fs = sheet()
t = tracker_for(fs)
t.load()
changes, row = T.plan_update(t.rows, "CS 137", "A5", status="Complete", grade=95.0, strict=False, why="voice")
res = t.apply(changes, "voice")
check("set: both ok", [r["ok"] for r in res], [True, True])
check("set: status written RAW to G6", fs.cell(6, 7), "Complete")
check("set: grade written to H6", fs.cell(6, 8), 95.0)
log = db.tracker_writes(5)
check("logged: cell, old → new, source", [(w["cell"], w["old"], w["new"], w["source"]) for w in reversed(log)],
      [("G6", "Not Started", "Complete", "voice"), ("H6", "", 95.0, "voice")])
check("one batch", len({w["batch"] for w in log}), 1)

# formula cell refused
fs = sheet()
t = tracker_for(fs)
t.load()
fs.formulas[(7, 7)] = '=IF(C7<TODAY(),"Late","")'
res = t.apply([T.change_set(t.rows[3], "status", "Complete")], "voice")
check("formula cell refused", (res[0]["ok"], "formula" in res[0]["error"]), (False, True))
check("formula intact", fs.formulas[(7, 7)].startswith("=IF"), True)
# unwritable column, header row, bad values
res = t.apply([T.change_set(t.rows[0], "days", 3)], "voice")
check("Days column refused", res[0]["ok"], False)
bad_hdr = T.change_set({"row": 3, "course": "Course", "title": "Assignment", "status": ""}, "status", "Complete")
check("header row refused", t.apply([bad_hdr], "voice")[0]["ok"], False)
check("bad status refused", t.apply([T.change_set(t.rows[2], "status", "Done!!")], "voice")[0]["ok"], False)
check("formula-like value refused", t.apply([T.change_set(t.rows[2], "title", "=1+1")], "voice")[0]["ok"], False)
check("nothing written by refusals", [c for c in fs.calls if c[0] == "update"], [])

# row moved: found again by course + title
fs = sheet()
t = tracker_for(fs)
t.load()
ch = T.change_set(t.rows[2], "status", "Complete")          # CS 137 A5, row 6
fs.grid.insert(4, ["SE 101", "Lab 5 - Team formation", serial(TODAY), "", "", "Assignment", "Complete"])   # he added a row above
res = t.apply([ch], "voice")
check("moved row relocated", (res[0]["ok"], res[0]["cell"]), (True, "G7"))
check("the row he added is untouched", fs.cell(5, 7), "Complete")
check("A5 marked", fs.cell(7, 7), "Complete")
# row gone
fs = sheet()
t = tracker_for(fs)
t.load()
ch = T.change_set(t.rows[2], "status", "Complete")
fs.grid[5][1] = "Assignment A5 - renamed by Trevor"
res = t.apply([ch], "voice")
check("renamed row left alone", (res[0]["ok"], fs.cell(6, 7)), (False, "Not Started"))

# insert in due order, inheriting the row above's format
fs = sheet()
t = tracker_for(fs)
t.load()
due = TODAY + timedelta(days=3)
res = t.apply([T.change_insert("CS 137", "Assignment A6", due)], "learn-feed")
check("insert ok", (res[0]["ok"], res[0]["cell"]), (True, "A7:H7"))
check("insertDimension at row 7, inherit from before", [c for c in fs.calls if c[0] == "insert"], [("insert", 7, True)])
check("inserted values", fs.grid[6][:3] + fs.grid[6][5:7], ["CS 137", "Assignment A6", serial(due), "Assignment", "Not Started"])
check("Days formula below moved down with its row", fs.formulas.get((9, 4)), "=C8-TODAY()")
check("rows below shifted", fs.cell(8, 2), "Weekly assessment W6 (quiz)")
res = t.apply([T.change_insert("CS 137", "CS137_a6", due)], "learn-feed")
check("no duplicate insert", res[0].get("exists"), True)
check("course must already exist", t.apply([T.change_insert("PHYS 999", "Assignment 1", due)], "voice")[0]["ok"], False)

# undo: the insert, then refuse when he changed a cell
ok, msg = t.undo()
check("undo insert", (ok, fs.cell(7, 2)), (True, "Weekly assessment W6 (quiz)"))
check("undo logged and marked", [w["source"] for w in db.tracker_writes(1)], ["undo"])
t.load()
t.apply(T.plan_update(t.rows, "CHE 102", "Assignment 3", status="In Progress")[0], "voice")
fs.set(8, 7, "Complete")                                     # he changed it himself afterwards
ok, msg = t.undo()
check("undo refused when cell changed", (ok, fs.cell(8, 7)), (False, "Complete"))
fs.set(8, 7, "In Progress")
ok, msg = t.undo()
check("undo set", (ok, fs.cell(8, 7)), (True, "Not Started"))
check("older batch whose cells don't hold Orrin's values any more: refused", t.undo()[0], False)

# ── the one-spreadsheet guard ──
G.SheetGuard.allowed = "SHEET"
for uri, allowed in [("https://sheets.googleapis.com/v4/spreadsheets/SHEET/values/A1?alt=json", True),
                     ("https://sheets.googleapis.com/v4/spreadsheets/SHEET:batchUpdate?alt=json", True),
                     ("https://sheets.googleapis.com/v4/spreadsheets/OTHER/values/A1?alt=json", False),
                     ("https://sheets.googleapis.com/v4/spreadsheets/SHEETX/values/A1", False),
                     ("https://sheets.googleapis.com/v4/spreadsheets?alt=json", False)]:
    try:
        G.SheetGuard(None, None, uri, method="GET")
        got = True
    except G.GoogleError as e:
        got = e.kind == "forbidden" and False
    check(f"guard {uri.split('spreadsheets')[1][:22]}", got, allowed)

# ── events ──
fs = sheet()
layout, rows = T.parse(fs.grid)
ch, sure = T.plan_event(rows, {"type": "grade", "course": "CS 137", "title": "CS137_a5", "score": 88.0})
check("grade notice → status + grade", ([(c["field"], c["new"]) for c in ch], sure), ([("status", "Complete"), ("grade", 88.0)], True))
ch, _ = T.plan_event(rows, {"type": "grade", "course": "MATH 135", "title": "Complete Assignment W5", "score": 50.0})
check("graded row already complete with a grade: nothing", ch, [])
ch, sure = T.plan_event(rows, {"type": "new", "course": "CS 137", "title": "CS137_a6", "due": (TODAY + timedelta(days=9)).isoformat(),
                               "source": "learn-feed"})
check("new feed deliverable → insert, sure", (ch[0]["kind"], ch[0]["values"]["title"], sure), ("insert", "CS137_a6", True))
ch, _ = T.plan_event(rows, {"type": "new", "course": "CS 137", "title": "9_Linked Lists - Available", "due": TODAY.isoformat(),
                            "source": "learn-feed"})
check("lecture release → nothing", ch, [])
ch, _ = T.plan_event(rows, {"type": "new", "course": "CS 137", "title": "CS137_a5", "due": TODAY.isoformat(), "source": "learn-feed"})
check("already in the sheet → nothing", ch, [])
che = rows[4]
ch, sure = T.plan_event(rows, {"type": "due", "course": "CHE 102", "title": "Assignment 3: Rates of Reaction", "source": "learn-feed",
                               "from": (che["due"] + timedelta(days=1)).isoformat(), "due": (che["due"] + timedelta(days=3)).isoformat()})
check("feed moved 2 days → row moved 2 days (his day-before convention kept)", T.from_serial(ch[0]["new"]), che["due"] + timedelta(days=2))

uw = {"from": ["CS 137 Course Staff <cs137@uwaterloo.ca>"], "subject": ["CS 137: Assignment A6 posted, due Nov 13"]}
ev = T.mail_event(uw, "", ["CS 137", "MATH 135"], today=date(2026, 11, 1))
check("course email: new assignment", ev, {"type": "new", "course": "CS 137", "title": "Assignment A6", "due": "2026-11-13"})
ev = T.mail_event({"from": ["prof@uwaterloo.ca"], "subject": ["MATH 135 W7 deadline extended to November 10th"]}, "",
                  ["MATH 135"], today=date(2026, 11, 1))
check("course email: extension", ev, {"type": "due", "course": "MATH 135", "title": "W7", "due": "2026-11-10"})
check("spoofed sender ignored", T.mail_event({"from": ["evil@gmail.com"], "subject": ["CS 137: Assignment A6 posted"]}, "",
                                              ["CS 137"]), None)
check("grade email isn't an announcement", T.mail_event({"from": ["noreply@crowdmark.com"],
                                                          "subject": ["CS 137 A6 grade released"]}, "", ["CS 137"]), None)
check("unknown course ignored", T.mail_event({"from": ["x@uwaterloo.ca"], "subject": ["PHYS 121 Lab 3 posted"]}, "", ["CS 137"]), None)
check("dkim fail ignored", T.mail_event(dict(uw, **{"authentication-results": ["mx; dkim=fail header.d=uwaterloo.ca"]}), "",
                                        ["CS 137"]), None)


# ── the sync pass ──
class Cfg(dict):
    pass


def queue(evs):
    with academic.locked():
        st = academic.load_state()
        st["tracker_events"] = evs
        st["tracker_offers"], st["announce"] = [], []
        academic.save_state(st)


grade_ev = {"type": "grade", "course": "CS 137", "title": "CS137_a5", "score": 88.0, "source": "grade-notice", "ts": time.time()}
new_ev = {"type": "new", "course": "CS 137", "title": "CS137_a6", "due": (TODAY + timedelta(days=9)).isoformat(),
          "source": "learn-feed", "ts": time.time()}
fs = sheet()
queue([grade_ev, new_ev])
r = S.tracker_pass(Cfg(orrinAutoUpdateTracker=False), sheet=tracker_for(fs))
check("auto off: nothing written", [c for c in fs.calls if c[0] in ("update", "insert")], [])
check("auto off: two offers", r.get("offered"), 2)
o = S.pop_tracker_offer()
check("offer prompt", o["prompt"], "Shall I mark CS 137 A5 complete and set CS 137 A5's grade to 88 in your tracker and calendar, sir?")
res = tracker_for(fs).apply(o["changes"], o["source"])
check("accepted offer applied", (fs.cell(6, 7), fs.cell(6, 8)), ("Complete", 88.0))
check("second offer still queued", S.pop_tracker_offer()["changes"][0]["kind"], "insert")
check("queue empty", S.pop_tracker_offer(), None)

fs = sheet()
queue([grade_ev, new_ev])
r = S.tracker_pass(Cfg(orrinAutoUpdateTracker=True), sheet=tracker_for(fs))
check("auto on: both applied", len(r.get("applied", [])), 2)
check("auto on: calendar still asked (offers, no sheet changes)", [(bool(o.get("calendar")), o["changes"]) for o in
                                                                   academic.load_state()["tracker_offers"]], [(True, []), (True, [])])
check("auto on: grade + status written, row inserted", (fs.cell(6, 7), fs.cell(6, 8), fs.cell(9, 2)), ("Complete", 88.0, "CS137_a6"))
lines = academic.pop_announcements()
check("auto on: announced", lines[0].startswith("I've updated your tracker, sir: mark CS 137 A5 complete"), True)

fs = sheet()
unsure = {"type": "new", "course": "CS 137", "title": "Project", "source": "course-email", "ts": time.time()}
queue([unsure])
r = S.tracker_pass(Cfg(orrinAutoUpdateTracker=True), sheet=tracker_for(fs))
check("auto on, unsure (no date) → offered, not written", (r.get("offered"), [c for c in fs.calls if c[0] == "insert"]), (1, []))


class Boom(T.Tracker):
    def apply(self, changes, source):
        raise G.GoogleError("offline", "I can't reach Google right now, sir.")


fs = sheet()
queue([grade_ev])
try:
    S.tracker_pass(Cfg(orrinAutoUpdateTracker=True), sheet=Boom(svc=fs, sheet_id="SHEET", db=db))
except G.GoogleError:
    pass
check("offline: events kept for next pass", len(academic.load_state()["tracker_events"]), 1)

# calendar fallback only without a tracker
check("calendar skipped with tracker", S.write_calendar(Cfg(orrinAutoAddAssignments=True, orrinAssignmentsAccount="google")),
      {"skipped": "the tracker sheet syncs to the calendar"})
check("configured needs the scope", T.configured(), True)
store[("google", "granted")] = json.dumps([G.NEEDS["gmail"]])
check("not configured without the Sheets scope", T.configured(), False)
store[("google", "granted")] = json.dumps([G.NEEDS["sheets"]])

# ── gate prompt + tools ──
from core.brain import integration_prompt  # noqa: E402
check("gate prompt: mark done", integration_prompt("LEARN", "tracker_update", {"course": "CS 137", "assignment": "A5", "status": "Complete"}),
      "Shall I mark CS 137 A5 complete in your tracker and calendar, sir?")
check("gate prompt: grade", integration_prompt("LEARN", "tracker_update", {"course": "MATH 135", "assignment": "W6", "grade": 92}),
      "Shall I set MATH 135 W6's grade to 92 in your tracker, sir?")
check("gate prompt: add", integration_prompt("LEARN", "tracker_add", {"course": "CS 137", "assignment": "A6", "due": "2026-11-13"}),
      "Add CS 137 A6 to your tracker and calendar, due 2026-11-13, sir?")

import academic_tools as AT  # noqa: E402
fs = sheet()
AT_orig = T.Tracker
T.Tracker = lambda: tracker_for(fs)
try:
    r = json.loads(AT.tracker_update("CS 137", "A5", status="done"))
    check("tool: mark A5 done", (r["ok"], fs.cell(6, 7)), (True, "Complete"))
    r = json.loads(AT.tracker_grade("MATH 135", "A6"))
    check("tool: grade lookup fenced", ("UNTRUSTED" in r["content"], r["graded"]), (True, False))
    r = json.loads(AT.tracker_pending(7))
    check("tool: pending counts", (r["count"], r["overdue"]), (2, 1))
    r = json.loads(AT.tracker_add("CS 137", "Assignment A6", (TODAY + timedelta(days=9)).isoformat()))
    check("tool: add", (r["ok"], r["result"]), (True, "added"))
    r = json.loads(AT.tracker_add("BIO 101", "Lab 1", TODAY.isoformat()))
    check("tool: add refuses unknown course", r["ok"], False)
    r = json.loads(AT.calendar_add_assignment("CS 137", "A6"))
    check("calendar tool defers to the tracker", r["ok"], False)
finally:
    T.Tracker = AT_orig

print(f"\n{'FAILED: ' + ', '.join(FAILS) if FAILS else 'all tracker tests passed'}")
sys.exit(1 if FAILS else 0)
