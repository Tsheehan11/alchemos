#!/usr/bin/env python3
"""Outlook calendar link + academic sync, without the network: ICS recurrence and Windows time zones,
the fetch cache, Google + Outlook merging, the connect flow refusing a URL argument, grade notices
(direct, redirected, "FW:" from the UW address, spoofs), announce-once, AUTO-ADD gating and the two
academic tools. All state goes to a temp dir. Run: python tests/test_outlook_academic.py"""
import io
import json
import os
import stat
import sys
import tempfile
import time
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp"), ROOT]
import academic  # noqa: E402
import academic_sync as S  # noqa: E402
import calendars  # noqa: E402
import google_api as G  # noqa: E402
import outlook_ical as O  # noqa: E402

FAILS = []


def check(name, got, want):
    if got != want:
        FAILS.append(name)
        print(f"FAIL {name}: got {got!r}, want {want!r}")


TMP = Path(tempfile.mkdtemp())
O.DATA, O.CACHE, O.META = TMP, TMP / "outlook.ics", TMP / "outlook.json"
academic.STATE_FILE = TMP / "academic.json"
store = {}
for mod in (O, G):
    mod.secrets.get = lambda s, a: store.get((s, a))
    mod.secrets.has = lambda s, a: bool(store.get((s, a)))
    mod.secrets.store = lambda s, a, v: store.__setitem__((s, a), v)
TZ = ZoneInfo("America/Toronto")

# ── an Outlook-published feed: Windows zone name, weekly class with an EXDATE and a moved instance,
#    a cancelled event, an all-day event, a UTC event ──
ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:Microsoft Exchange Server 2010
BEGIN:VTIMEZONE
TZID:Eastern Standard Time
BEGIN:STANDARD
DTSTART:16010101T020000
TZOFFSETFROM:-0400
TZOFFSETTO:-0500
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=1SU;BYMONTH=11
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:16010101T020000
TZOFFSETFROM:-0500
TZOFFSETTO:-0400
RRULE:FREQ=YEARLY;INTERVAL=1;BYDAY=2SU;BYMONTH=3
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:class-cs137
SUMMARY:CS 137 LEC
LOCATION:MC 4020
DTSTART;TZID=Eastern Standard Time:20261005T103000
DTEND;TZID=Eastern Standard Time:20261005T112000
RRULE:FREQ=WEEKLY;BYDAY=MO,WE,FR;UNTIL=20261205T000000Z
EXDATE;TZID=Eastern Standard Time:20261102T103000
END:VEVENT
BEGIN:VEVENT
UID:class-cs137
RECURRENCE-ID;TZID=Eastern Standard Time:20261104T103000
SUMMARY:CS 137 LEC (moved)
LOCATION:MC 2065
DTSTART;TZID=Eastern Standard Time:20261104T130000
DTEND;TZID=Eastern Standard Time:20261104T135000
END:VEVENT
BEGIN:VEVENT
UID:cancelled-1
SUMMARY:Office hours
STATUS:CANCELLED
DTSTART;TZID=Eastern Standard Time:20261104T150000
DTEND;TZID=Eastern Standard Time:20261104T160000
END:VEVENT
BEGIN:VEVENT
UID:allday-1
SUMMARY:Reading day
DTSTART;VALUE=DATE:20261104
DTEND;VALUE=DATE:20261105
END:VEVENT
BEGIN:VEVENT
UID:utc-1
SUMMARY:Club meeting
DTSTART:20261104T230000Z
DTEND:20261105T000000Z
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").encode()

O.CACHE.write_bytes(ICS)
day = lambda y, m, d: datetime(y, m, d, tzinfo=TZ)
nov4 = O.events(day(2026, 11, 4), day(2026, 11, 5), TZ)
check("Nov 4: moved class, all-day, UTC event; cancelled dropped",
      [(e["title"], e["start"].strftime("%H:%M"), e["all_day"]) for e in nov4],
      [("Reading day", "00:00", True), ("CS 137 LEC (moved)", "13:00", False), ("Club meeting", "18:00", False)])
check("moved class keeps its UID", nov4[1]["uid"], "class-cs137")
check("EXDATE skipped (Nov 2)", O.events(day(2026, 11, 2), day(2026, 11, 3), TZ), [])
fri = O.events(day(2026, 11, 6), day(2026, 11, 7), TZ)
check("weekly recurrence after the DST change (EST)", [(e["title"], e["start"].isoformat()) for e in fri],
      [("CS 137 LEC", "2026-11-06T10:30:00-05:00")])
oct9 = O.events(day(2026, 10, 9), day(2026, 10, 10), TZ)
check("…and before it (EDT)", oct9[0]["start"].isoformat(), "2026-10-09T10:30:00-04:00")
check("source", fri[0]["source"], "Outlook")

# ── urls + fetch cache ──
check("webcal → https", O.normalize_url("webcal://outlook.office365.com/owa/calendar/x/reachcalendar.ics"),
      "https://outlook.office365.com/owa/calendar/x/reachcalendar.ics")
try:
    O.normalize_url("http://example.com/cal.ics")
    check("http refused", "accepted", "refused")
except O.FeedError:
    pass


class Resp(io.BytesIO):
    def __init__(self, body, headers=None):
        super().__init__(body)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


O.CACHE.unlink()
calls = []
O.urllib.request.urlopen = lambda req, timeout=0: calls.append(dict(req.headers)) or Resp(ICS, {"ETag": '"v1"'})
m = O.fetch("https://x/cal.ics", force=True)
check("fetch ok", (m["ok"], m["events"]), (True, 5))
check("cache is private (600)", stat.S_IMODE(O.CACHE.stat().st_mode), 0o600)
check("fresh cache: no refetch", (O.fetch("https://x/cal.ics")["ok"], len(calls)), (True, 1))
meta = json.loads(O.META.read_text()); meta["fetched"] -= O.REFRESH_S + 1; O.META.write_text(json.dumps(meta))


def not_modified(req, timeout=0):
    calls.append(dict(req.headers))
    raise urllib.error.HTTPError(req.full_url, 304, "Not Modified", {}, None)


O.urllib.request.urlopen = not_modified
check("stale → conditional GET → 304 keeps cache", (O.fetch("https://x/cal.ics")["ok"], calls[-1].get("If-none-match")), (True, '"v1"'))
O.urllib.request.urlopen = lambda req, timeout=0: Resp(b"<html>sign in</html>")
m = O.fetch("https://x/cal.ics", force=True)
check("junk doesn't replace a good cache", (m["ok"], O.CACHE.read_bytes() == ICS), (False, True))

# ── merging Google + Outlook ──
g = lambda title, h, uid="", src="Google": {"title": title, "start": day(2026, 11, 4).replace(hour=h), "all_day": False,
                                            "end": day(2026, 11, 4).replace(hour=h + 1), "where": "", "calendar": "",
                                            "uid": uid, "source": src}
merged = calendars.dedupe([g("CS 137 LEC (moved)", 13, "class-cs137", "Outlook"), g("cs 137 lec (MOVED)", 13, "x", "Google"),
                           g("Club meeting", 18, "", "Outlook"), g("Gym", 7), g("Lab", 15, "class-cs137-lab", "Google · Classes"),
                           g("Lab (copy)", 15, "class-cs137-lab", "Outlook")])
check("deduped: same title+time, same UID", [(e["title"], e["sources"]) for e in merged],
      [("Gym", ["Google"]), ("cs 137 lec (MOVED)", ["Google", "Outlook"]),
       ("Lab", ["Google · Classes", "Outlook"]), ("Club meeting", ["Outlook"])])
check("source only as source_if_asked", G.describe(merged[1], day(2026, 11, 4).replace(hour=9)).get("source_if_asked"), "Google and Outlook")

O.CACHE.write_bytes(ICS)
store[("google", "token")] = "x"
store[("outlook", "ical_url")] = "https://x/cal.ics"
O.fetch = lambda *a, **k: {"ok": True}
G.events = lambda s, e, n=50: [g("Gym", 7)]
evs, notes = calendars.merged(day(2026, 11, 4), day(2026, 11, 5))
check("both sources merged", [e["title"] for e in evs], ["Reading day", "Gym", "CS 137 LEC (moved)", "Club meeting"])


def google_down(*a, **k):
    raise G.GoogleError("expired", "Your Google sign-in has expired, sir.")


G.events = google_down
evs, notes = calendars.merged(day(2026, 11, 4), day(2026, 11, 5))
check("Google down: Outlook still answers, with a note", (len(evs), notes), (3, ["Your Google sign-in has expired, sir."]))
O.fetch = lambda *a, **k: (_ for _ in ()).throw(O.FeedError("HTTP 404"))
try:
    calendars.merged(day(2026, 11, 4), day(2026, 11, 5))
    check("everything down raises", "no error", "GoogleError")
except G.GoogleError as e:
    check("everything down raises", e.kind, "expired")
store.clear()
try:
    calendars.merged(day(2026, 11, 4), day(2026, 11, 5))
except G.GoogleError as e:
    check("nothing connected", e.kind, "not_connected")

# ── orrin connect outlook-ical never takes the URL as an argument ──
from core import integrations  # noqa: E402
before = dict(store)
check("URL argument refused", integrations.connect_outlook(["https://outlook.office365.com/x/calendar.ics"]), 2)
check("…and nothing stored", store, before)

# ── grade notices ──
known = [{"course": "CS 137", "title": "Assignment 5", "due": datetime(2026, 11, 6, 23, 59), "url": "", "key": "CS137|a5"},
         {"course": "MATH 135", "title": "Assignment 7", "due": datetime(2026, 11, 9, 23, 59), "url": "", "key": "MATH135|a7"}]
H = lambda **kw: {k.rstrip("_").replace("_", "-"): ([v] if isinstance(v, str) else v) for k, v in kw.items()}
N = lambda h, snip="": (lambda r: (r[0]["key"], r[1]) if r else None)(academic.notice_from_message(h, snip, known))
check("LEARN direct", N(H(from_="LEARN <noreply@learn.uwaterloo.ca>", subject="CS 137: Grade released for Assignment 5")),
      ("CS137|a5", "LEARN"))
check("Crowdmark redirected by UW (From kept, SRS Return-Path, ARC pass)",
      N(H(from_="Crowdmark <notifications@crowdmark.com>", subject="CS137 A5 has been graded",
          return_path="<SRS0=Ab12=TT=crowdmark.com=notifications@uwaterloo.ca>",
          arc_authentication_results="i=1; mx.microsoft.com 1; dkim=pass header.d=crowdmark.com; spf=pass")),
      ("CS137|a5", "Crowdmark"))
check("mailbox forwarding: original only in Return-Path (SRS)",
      N(H(from_="Student <student@uwaterloo.ca>", subject="MATH 135 Assignment 7: feedback is now available",
          return_path="<SRS0=x=yy=crowdmark.com=noreply@uwaterloo.ca>")), ("MATH135|a7", "Crowdmark"))
check("FW: from his UW address, sender in the snippet",
      N(H(from_="Sam Student <student@uwaterloo.ca>", subject="FW: CS 137 Assignment 5 has been graded"),
        "From: Crowdmark <noreply@crowdmark.com> Sent: Thursday, October 29, 2026 4:02 PM To: Student"), ("CS137|a5", "Crowdmark"))
check("classmate at uwaterloo.ca", N(H(from_="Sam <s123@uwaterloo.ca>", subject="CS 137: Grade released for Assignment 5")), None)
check("FW from outside UW doesn't vouch", N(H(from_="x@gmail.com", subject="FW: CS 137 Assignment 5 has been graded"),
                                            "From: Crowdmark <noreply@crowdmark.com>"), None)
check("DKIM failed for the grade sender", N(H(from_="noreply@crowdmark.com", subject="CS137 A5 has been graded",
                                               authentication_results="mx.google.com; dkim=fail header.i=@crowdmark.com")), None)
check("not in the feed", N(H(from_="noreply@crowdmark.com", subject="CS137 A9 has been graded")), None)
check("not a grade subject", N(H(from_="noreply@learn.uwaterloo.ca", subject="CS 137: Assignment 5 is due tomorrow")), None)

# ── scan_grades: first scan quiet, then once per assignment, recent only ──
academic.save_state({"assignments": {a["key"]: dict(a, due=a["due"].isoformat()) for a in known}})
now = time.time()
msg = lambda mid, subj, age_s=600, frm="noreply@crowdmark.com": (mid, H(from_=frm, subject=subj), "", now - age_s)
first = S.scan_grades([msg("m1", "MATH135 A7 has been graded", age_s=86400 * 5)], now=now)
st = academic.load_state()
check("first scan records old grades without a word", ([g["key"] for g in first], st["announce"], st["announced"]),
      (["MATH135|a7"], [], ["MATH135|a7"]))
S.scan_grades([msg("m2", "CS137 A5 has been graded")], now=now)
S.scan_grades([msg("m3", "CS 137: Grade released for Assignment 5", frm="noreply@learn.uwaterloo.ca")], now=now)
S.scan_grades([msg("m2", "CS137 A5 has been graded")], now=now)
st = academic.load_state()
check("announced once per grade", [a["text"] for a in st["announce"]], ["Sir, your CS 137 A5 has been graded."])
check("graded recorded once", sorted(g["key"] for g in st["graded"]), ["CS137|a5", "MATH135|a7"])
check("announcements popped once", (academic.pop_announcements(), academic.pop_announcements()),
      (["Sir, your CS 137 A5 has been graded."], []))
academic.save_state(dict(academic.load_state(), graded=[], announced=[], seen_msgs=[]))
S.scan_grades([msg("m9", "CS137 A5 has been graded", age_s=3 * 86400)], now=now)
check("a grade from days ago isn't announced", academic.load_state()["announce"], [])


# ── calendar writes: AUTO-ADD gating, upcoming only, ✓ once synced ──
class Cal:
    def __init__(self):
        self.up, self.ticked = [], []

    def upsert(self, ev):
        self.up.append(ev["key"])
        return "created", "id"

    def mark_graded(self, key, fn):
        self.ticked.append(key)
        return True


past = {"course": "CS 137", "title": "Assignment 1", "due": datetime(2026, 9, 20, 23, 59), "url": "", "key": "CS137|a1"}
academic.save_state({"assignments": {a["key"]: dict(a, due=a["due"].isoformat()) for a in known + [past]},
                     "graded": [{"key": "CS137|a5", "ts": now, "source": "LEARN", "reported": False, "ticked": False}]})
store[("google", "token")] = "x"
cfg = {"orrinAutoAddAssignments": False, "orrinAssignmentsAccount": "google"}
cal = Cal()
check("AUTO-ADD off: nothing written", (S.write_calendar(cfg, now=datetime(2026, 11, 1).timestamp(), calendar=cal), cal.up),
      ({"skipped": "AUTO-ADD is off"}, []))
cfg["orrinAutoAddAssignments"] = True
r = S.write_calendar(cfg, now=datetime(2026, 11, 1).timestamp(), calendar=cal)
check("AUTO-ADD on: upcoming only, then ✓", (sorted(cal.up), cal.ticked, r), (["CS137|a5", "MATH135|a7"], ["CS137|a5"],
                                                                                 {"created": 2, "updated": 0, "ticked": 1}))
cal2 = Cal()
check("next pass: nothing to redo", (S.write_calendar(cfg, now=datetime(2026, 11, 1).timestamp(), calendar=cal2), cal2.up, cal2.ticked),
      ({"created": 0, "updated": 0, "ticked": 0}, [], []))
cfg["orrinAssignmentsAccount"] = "microsoft"
check("Outlook account: skipped, not faked", "skipped" in S.write_calendar(cfg, calendar=Cal()), True)

# ── the two academic tools ──
import academic_tools as AT  # noqa: E402
AT.secrets.has = lambda s, a: (s, a) in {("learn", "ical_url"), ("google", "token")}
S.refresh_learn = lambda force=False: {"new": [], "changed": [], "total": 3}
G.messages = lambda q, n: []
soon = datetime.now() + timedelta(days=2)
later = datetime.now() + timedelta(days=5)
academic.save_state({"assignments": {
    "CS137|a6": {"course": "CS 137", "title": "Assignment 6", "due": later.isoformat(), "url": "", "key": "CS137|a6"},
    "MATH135|a8": {"course": "MATH 135", "title": "Assignment 8", "due": soon.isoformat(), "url": "", "key": "MATH135|a8"},
    "SE101|lab9": {"course": "SE 101", "title": "Lab 9", "due": (datetime.now() + timedelta(days=20)).isoformat(), "url": "", "key": "SE101|lab 9"}},
    "graded": [{"key": "MATH135|a8", "ts": time.time(), "source": "Crowdmark", "reported": False, "ticked": False}]})
r = json.loads(AT.assignments_upcoming(7))
inner = json.loads(r["content"].split("\n", 1)[1].rsplit("\n", 1)[0])
check("this week, soonest first, fenced", ([a["title"] for a in inner["assignments"]], r["content"].startswith("<<UNTRUSTED-")),
      (["Assignment 8", "Assignment 6"], True))
check("graded flag", inner["assignments"][0].get("graded"), True)
check("nothing due", json.loads(AT.assignments_upcoming(1)).get("say"), "Nothing due on LEARN in the next 1 days, sir.")
S.gmail_notices = lambda: []
r = json.loads(AT.grades_new())
check("grades_new reports once", (r["count"], json.loads(AT.grades_new()).get("say")), (1, "No new grades, sir."))
check("…and won't be announced again", "MATH135|a8" in academic.load_state()["announced"], True)

print(f"{'FAILED ' + str(len(FAILS)) if FAILS else 'all passed'}")
sys.exit(1 if FAILS else 0)
