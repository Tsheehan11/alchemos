#!/usr/bin/env python3
"""Google tools without the network: Google's errors → spoken lines (API not enabled, missing scope,
expired), granted-scope checks, time phrasing, and the STARK – Assignments calendar against a fake
Calendar service that fails if anything touches another calendar. Run: python tests/test_google.py"""
import json
import os
import sys
from datetime import datetime, timedelta

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
import academic  # noqa: E402
import google_api as G  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


# ── Google's errors ──
disabled = json.dumps({"error": {"code": 403, "message": "Gmail API has not been used in project 123 before or it is disabled. "
                       "Enable it by visiting https://console.developers.google.com/apis/api/gmail.googleapis.com/overview?project=123 then retry.",
                       "errors": [{"reason": "accessNotConfigured"}], "details": [{"reason": "SERVICE_DISABLED"}]}}).encode()
e = G.translate("gmail", 403, disabled)
check("api disabled: kind", e.kind, "api_disabled")
check("api disabled: names the API", "Gmail API isn't turned on" in e.say, True)
check("api disabled: link for the log", e.detail.endswith("overview?project=123"), True)
e = G.translate("calendar", 403, json.dumps({"error": {"message": "x", "details": [{"reason": "SERVICE_DISABLED"}]}}).encode())
check("SERVICE_DISABLED alone", (e.kind, "Google Calendar API" in e.say), ("api_disabled", True))
e = G.translate("drive", 403, json.dumps({"error": {"message": "Request had insufficient authentication scopes.",
                                                    "details": [{"reason": "ACCESS_TOKEN_SCOPE_INSUFFICIENT"}]}}).encode())
check("missing scope: kind", e.kind, "scope")
check("missing scope: says which box", "tick the Drive box" in e.say, True)
check("401 = expired", G.translate("gmail", 401, b'{"error":{"message":"Invalid Credentials"}}').kind, "expired")
check("other errors", (G.translate("drive", 500, b"oops").kind, G.translate("drive", 500, b"oops").say), ("http", "Google Drive returned an error, sir."))
r = G.GoogleError("api_disabled", "say this", "detail").result()
check("result carries the spoken line", (r["ok"], r["say"], r["connected"]), (False, "say this", True))

# ── granted scopes ──
store = {}
G.secrets.get = lambda s, a: store.get((s, a))
check("no record = nothing flagged", G.missing_scopes(), [])
store[("google", "granted")] = json.dumps([G.NEEDS["calendar"], G.NEEDS["drive"]])
check("unticked Gmail found", G.missing_scopes([G.NEEDS["gmail"], G.NEEDS["calendar"]]), [G.NEEDS["gmail"]])
try:
    G.credentials()
    check("no token → not connected", "no error", "GoogleError")
except G.GoogleError as err:
    check("no token → not connected", err.kind, "not_connected")

# ── time, said the human way ──
z = G.tz()
now = datetime(2026, 10, 30, 14, 2, tzinfo=z)
check("clock", [G.clock(now.replace(hour=h, minute=m)) for h, m in ((16, 30), (12, 0), (0, 0), (9, 0))],
      ["4:30 PM", "noon", "midnight", "9 AM"])
check("day names", [G.day_name(now + timedelta(days=d), now) for d in (0, 1, 2, 9)],
      ["today", "tomorrow", "Sunday the 1st", "Sunday, November 8th"])
ev = {"start": now - timedelta(minutes=50), "end": now + timedelta(minutes=18), "all_day": False, "title": "MATH135",
      "where": "MC 2066", "calendar": ""}
check("happening now", G.describe(ev, now), {"title": "MATH135", "day": "today", "when": "1:12 PM to 2:20 PM",
                                             "status": "happening now", "where": "MC 2066"})
soon = dict(ev, start=now + timedelta(minutes=28), end=now + timedelta(minutes=78), sources=["Google · Classes", "Outlook"])
check("starts soon", (G.describe(soon, now)["starts_in_minutes"], G.describe(soon, now)["source_if_asked"]),
      (28, "Google · Classes and Outlook"))
check("timed event parse", G.parse_when({"dateTime": "2026-10-30T18:30:00Z"})[0].hour, 14)
check("all-day parse", G.parse_when({"date": "2026-10-30"})[1], True)


# ── STARK – Assignments, against a fake Calendar API ──
class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, num_retries=0):
        return self.fn()


class FakeCalendar:
    def __init__(self):
        self.cals, self.evs, self.log = {}, {}, []

    def _guard(self, cid):
        if cid not in self.cals:
            raise AssertionError(f"touched a calendar Orrin didn't create: {cid}")

    def calendars(self):
        fake = self

        class C:
            def get(self, calendarId, fields=None):
                def go():
                    if calendarId not in fake.cals:
                        from googleapiclient.errors import HttpError
                        raise HttpError(type("R", (), {"status": 404, "reason": "nf"})(), b'{"error":{"message":"Not Found"}}')
                    return {"id": calendarId}
                return Req(go)

            def insert(self, body, fields=None):
                def go():
                    cid = f"cal{len(fake.cals) + 1}@group.calendar.google.com"
                    fake.cals[cid] = body
                    fake.log.append(("calendar.insert", body["summary"]))
                    return {"id": cid}
                return Req(go)
        return C()

    def events(self):
        fake = self

        class E:
            def list(self, calendarId, privateExtendedProperty=None, **kw):
                def go():
                    fake._guard(calendarId)
                    k = privateExtendedProperty.split("=", 1)[1]
                    return {"items": [dict(e, id=i) for i, e in fake.evs.items()
                                      if e["cal"] == calendarId and e["extendedProperties"]["private"]["starkKey"] == k]}
                return Req(go)

            def insert(self, calendarId, body, fields=None):
                def go():
                    fake._guard(calendarId)
                    i = f"ev{len(fake.evs) + 1}"
                    fake.evs[i] = dict(body, cal=calendarId)
                    fake.log.append(("insert", body["summary"]))
                    return {"id": i}
                return Req(go)

            def patch(self, calendarId, eventId, body, fields=None):
                def go():
                    fake._guard(calendarId)
                    fake.evs[eventId].update(body)
                    fake.log.append(("patch", fake.evs[eventId]["summary"]))
                    return {"id": eventId}
                return Req(go)
        return E()


fake = FakeCalendar()
G.service = lambda api: fake
G.secrets.store = lambda s, a, v: store.__setitem__((s, a), v)
a = {"course": "CS 137", "title": "Assignment 5", "due": datetime(2026, 11, 6, 23, 59, tzinfo=z),
     "url": "https://learn.uwaterloo.ca/x", "key": "CS137|a5"}
cal = G.AssignmentsCalendar(academic.ASSIGNMENTS_CALENDAR)
check("first add creates the app's calendar + event", cal.upsert(academic.event_for(a))[0], "created")
check("calendar named STARK – Assignments", list(fake.cals.values())[0]["summary"], "STARK – Assignments")
check("calendar id remembered", store[("google", "assignments_calendar")], "cal1@group.calendar.google.com")
ev = next(iter(fake.evs.values()))
check("reminder 2 days before", ev["reminders"], {"useDefault": False, "overrides": [{"method": "popup", "minutes": 2880}]})
check("due time + zone", (ev["end"]["dateTime"][:16], ev["end"]["timeZone"]), ("2026-11-06T23:59", "America/Toronto"))
check("link + course in the event", ("Course: CS 137" in ev["description"], ev["source"]["url"]), (True, "https://learn.uwaterloo.ca/x"))
check("same again = unchanged (no duplicate)", (cal.upsert(academic.event_for(a))[0], len(fake.evs)), ("unchanged", 1))
check("graded tick", cal.mark_graded("CS137|a5", academic.graded_summary), True)
check("tick applied", next(iter(fake.evs.values()))["summary"], "✓ CS 137 Assignment 5")
moved = dict(a, due=datetime(2026, 11, 7, 23, 59, tzinfo=z))
check("new due date = update", cal.upsert(academic.event_for(moved))[0], "updated")
check("…keeps the tick", next(iter(fake.evs.values()))["summary"], "✓ CS 137 Assignment 5")
check("only ever one calendar created", sum(1 for x in fake.log if x[0] == "calendar.insert"), 1)
store[("google", "assignments_calendar")] = "deleted@group.calendar.google.com"
check("calendar deleted by hand → a fresh one", cal.calendar_id(), "cal2@group.calendar.google.com")

# ── academic_tools: finding the assignment he named ──
import academic_tools as AT  # noqa: E402
known = [dict(a), {"course": "MATH 135", "title": "Assignment 7", "due": a["due"], "url": "", "key": "MATH135|a7"},
         {"course": "CS 137", "title": "Midterm review quiz", "due": a["due"], "url": "", "key": "CS137|midterm review quiz"}]
check("course + A5", AT.find_assignment("CS 137", "A5", known)["key"], "CS137|a5")
check("spaced / spoken", AT.find_assignment("cs137", "assignment five".replace("five", "5"), known)["key"], "CS137|a5")
check("part of a title", AT.find_assignment("CS 137", "midterm", known)["key"], "CS137|midterm review quiz")
check("wrong course", AT.find_assignment("CS 136", "A5", known), None)

print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
