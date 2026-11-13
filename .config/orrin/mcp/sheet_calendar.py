"""
His SE tracker sheet's own calendar events, kept in step when Orrin edits the sheet.

His sheet's Apps Script (installable "From spreadsheet - On edit" trigger → handleEdit, plus a
"📅 Calendar Sync → Sync All" menu) only restyles events that already exist: on a Status (column G)
edit it looks on the row's due date (getEventsForDay) for "[COURSE] Title" or "✓ [COURSE] Title" and
sets the title, colour and description. It never creates, moves or deletes an event, and edit
triggers don't run for Sheets API writes at all. So Tracker.apply calls SheetCalendar.follow() for
every row it touched, and the event is written in exactly the script's format, on the row's date,
so the script keeps finding it:

  summary      "[COURSE] Title", "✓ " in front when Complete
  description  "Course: …\\nType: …\\nStatus: …", the status as the script shows it ("Not started",
               "In progress", "Complete": lower-cased, first letter capitalised)
  colour       Complete green (10), In progress yellow (5), otherwise mauve (3) for an Assessment, red (11)
  when         all day on the due date; a new event takes the reminders the existing ones use

An event is matched by its summary (with or without the ✓) anywhere in the term, never by date, so a
moved row's event is moved instead of a second one being made. All writes go through
google_api.CalendarWriter (logged, undoable, main calendar only); callers have his yes already.
"""
import json
import re
from collections import Counter
from datetime import date, datetime, timedelta

import google_api as G

TICK = "✓ "
WINDOW_DAYS = 200
SHEET_EVENT = re.compile(r"^(?:✓ )?\[[A-Z]{2,5} \d{3}[A-Z]?\] \S")


def _status(r):
    return (r.get("status") or "").strip().lower()


def summary(r):
    return (TICK if _status(r) == "complete" else "") + f"[{r['course']}] {r['title']}"


def base(s):
    return s[len(TICK):] if (s or "").startswith(TICK) else (s or "")


def display_status(status):
    """The script's displayStatus: lower-cased, first letter capitalised; empty → "Not Started"."""
    s = (status or "").strip().lower()
    return s[0].upper() + s[1:] if s else "Not Started"


def description(r):
    return f"Course: {r['course']}\nType: {(r.get('type') or '').strip()}\nStatus: {display_status(r.get('status'))}"


def color(r):
    """The CalendarApp.EventColor the script picks: GREEN 10, YELLOW 5, MAUVE 3, RED 11."""
    s = _status(r)
    if s == "complete":
        return "10"
    if s == "in progress":
        return "5"
    return "3" if (r.get("type") or "").strip().lower() == "assessment" else "11"


def _day(e):
    s = e.get("start", {})
    if "date" in s:
        return date.fromisoformat(s["date"])
    return datetime.fromisoformat(s["dateTime"].replace("Z", "+00:00")).astimezone(G.tz()).date() if "dateTime" in s else None


def spoken(d):
    return f"{d:%A, %B} {d.day}"


class SheetCalendar:
    def __init__(self, writer=None, today=None):
        self.w = writer if writer is not None else G.CalendarWriter("tracker")
        self.today = today or date.today()
        self._events = None

    def events(self):
        """The sheet's events on his main calendar this term (not deleted)."""
        if self._events is None:
            cid = self.w.main_id()
            lo = datetime.combine(self.today - timedelta(days=WINDOW_DAYS), datetime.min.time(), G.tz())
            hi = datetime.combine(self.today + timedelta(days=WINDOW_DAYS), datetime.min.time(), G.tz())
            items, tok = [], None
            while True:
                r = G.call("calendar", self.w.svc.events().list(
                    calendarId=cid, timeMin=lo.isoformat(), timeMax=hi.isoformat(), singleEvents=True,
                    maxResults=2500, pageToken=tok))
                items += r.get("items", [])
                tok = r.get("nextPageToken")
                if not tok:
                    break
            self._events = [e for e in items if e.get("status") != "cancelled" and SHEET_EVENT.match(e.get("summary", ""))]
        return self._events

    def matches(self, r):
        want = base(summary(r))
        return [e for e in self.events() if base(e.get("summary")) == want]

    def reminders(self):
        """The reminders the sheet's events already carry (for a new one), or None."""
        votes = Counter(json.dumps(e["reminders"], sort_keys=True) for e in self.events() if e.get("reminders"))
        return json.loads(votes.most_common(1)[0][0]) if votes else None

    def body(self, r, new=False):
        b = {"summary": summary(r), "description": description(r), "colorId": color(r),
             "start": {"date": r["due"].isoformat()}, "end": {"date": (r["due"] + timedelta(days=1)).isoformat()}}
        if new and self.reminders():
            b["reminders"] = self.reminders()
        return b

    def follow(self, before, after):
        """Bring the row's event in line. before / after: {"course", "title", "due" (date|None), "type",
        "status"}, None for a row that didn't exist / was removed. → {"did": [...], "notes": [...]}."""
        did, notes = [], []
        found = self.matches(before) if before else []
        if after and not found:
            found = self.matches(after)
        if before and before.get("due"):
            found.sort(key=lambda e: _day(e) != before["due"])      # the one on the row's old date first
        cid = self.w.main_id()
        if after is None:
            for e in found:
                if self.w.delete(cid, e["id"]):
                    did.append(f"deleted its calendar event on {spoken(_day(e))}")
            return {"did": did, "notes": notes}
        if not after.get("due"):
            if found:
                notes.append("the row has no due date now, so I left its calendar event where it was")
            return {"did": did, "notes": notes}
        if not found:
            made = self.w.create(cid, self.body(after, new=True))
            self._events.append(made)
            did.append(f"added it to your calendar on {spoken(after['due'])}")
            return {"did": did, "notes": notes}
        e = found[0]
        old_day = _day(e)
        body = self.body(after)
        new = self.w.update(cid, e["id"], body)
        if new is not None:
            self._events[self._events.index(e)] = new
            if old_day != after["due"]:
                did.append(f"moved its calendar event to {spoken(after['due'])}")
            elif base(e.get("summary")) != base(body["summary"]):
                did.append("renamed its calendar event")
            elif e.get("summary", "").startswith(TICK) != body["summary"].startswith(TICK):
                did.append("ticked its calendar event" if body["summary"].startswith(TICK) else "unticked its calendar event")
            else:
                did.append("updated its calendar event")
        for x in found[1:]:
            notes.append(f"there's a second copy on {spoken(_day(x))}; say so and I'll delete it")
        return {"did": did, "notes": notes}
