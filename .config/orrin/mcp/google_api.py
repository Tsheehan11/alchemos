"""
Google APIs for Orrin (google-api-python-client), shared by google_tools.py and academic_tools.py.

Credentials come from the system keyring ("orrin:google" / token, written by `orrin connect
google`); a refreshed access token is written back so the next call doesn't refresh again.
Everything here is read-only except AssignmentsCalendar, which only ever touches the calendar
this app created ("STARK – Assignments"): the calendar.app.created scope can't reach any other;
CalendarWriter, the one path for writes to his main calendar (calendar.events scope; every write
logged in orrin_db.calendar_log, `orrin calendar undo`; subscribed / read-only calendars are
refused with a reason; callers only reach it after his yes); and service("sheets"), which can only reach his SE tracker spreadsheet: the spreadsheets scope
covers every sheet he owns, so the client refuses any request that names another (SheetGuard).

Failures become GoogleError(kind, say, detail): `say` is a line Orrin can speak, `detail` is
for the log / the model. Kinds: not_connected, expired (refresh token revoked or, in Testing
mode, 7 days old), api_disabled (with the console link to enable it), scope (a permission
box left unticked at sign-in), offline, http.
"""
import json
import os
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from integration_common import CONNECT_HINT, secrets

SCOPES = {   # scope → what to re-tick on Google's consent screen
    "https://www.googleapis.com/auth/gmail.readonly": "Gmail (read your email)",
    "https://www.googleapis.com/auth/calendar.readonly": "Calendar (see your calendars)",
    "https://www.googleapis.com/auth/drive.readonly": "Drive (see your files)",
    "https://www.googleapis.com/auth/calendar.app.created": "Calendar (make secondary calendars)",
    "https://www.googleapis.com/auth/spreadsheets": "Sheets (edit your SE tracker)",
    "https://www.googleapis.com/auth/calendar.events": "Calendar (view and edit events on all your calendars)",
}
NEEDS = {"gmail": "https://www.googleapis.com/auth/gmail.readonly",
         "calendar": "https://www.googleapis.com/auth/calendar.readonly",
         "drive": "https://www.googleapis.com/auth/drive.readonly",
         "assignments": "https://www.googleapis.com/auth/calendar.app.created",
         "sheets": "https://www.googleapis.com/auth/spreadsheets",
         "calendar_write": "https://www.googleapis.com/auth/calendar.events"}
API_NAMES = {"gmail": "Gmail", "calendar": "Google Calendar", "drive": "Google Drive", "assignments": "Google Calendar",
             "sheets": "Google Sheets", "calendar_write": "Google Calendar"}


class GoogleError(Exception):
    def __init__(self, kind, say, detail=""):
        super().__init__(detail or say)
        self.kind, self.say, self.detail = kind, say, detail

    def result(self):
        return {"ok": False, "connected": self.kind != "not_connected", "error": self.detail or self.kind,
                "kind": self.kind, "say": self.say}


def local_tz():
    """IANA name of the system zone (/etc/localtime → America/Toronto)."""
    try:
        path = os.path.realpath("/etc/localtime")
        return path.split("zoneinfo/", 1)[1] if "zoneinfo/" in path else "UTC"
    except OSError:
        return "UTC"


def granted():
    """Scopes Google actually granted at the last sign-in (stored by `orrin connect google`), or None."""
    g = secrets.get("google", "granted")
    return set(json.loads(g)) if g else None


def missing_scopes(want=None):
    g = granted()
    want = set(want or SCOPES)
    return sorted(want - g) if g is not None else []


def credentials():
    from google.auth.exceptions import RefreshError, TransportError
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    raw = secrets.get("google", "token")
    if not raw:
        raise GoogleError("not_connected", f"Your Google account isn't connected yet, sir. {CONNECT_HINT}")
    info = json.loads(raw)
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        try:
            creds.refresh(Request())
        except RefreshError as e:
            raise GoogleError("expired", "Your Google sign-in has expired, sir. Reconnect it in Settings, under Orrin.",
                              f"refresh failed: {e}")
        except TransportError as e:
            raise GoogleError("offline", "I can't reach Google right now, sir.", str(e))
        info.update(json.loads(creds.to_json()))
        secrets.store("google", "token", json.dumps(info))
    return creds


_services = {}


def tracker_id():
    """The one spreadsheet Orrin may open (his SE academic tracker, set by `orrin tracker find`), or None."""
    return secrets.get("google", "tracker_sheet")


class SheetGuard:
    """Request builder for the Sheets client: every request must name the tracker spreadsheet.
    Anything else (another sheet, spreadsheets.create, a URL without an ID) is refused before it is
    built, so neither a bug nor a model argument can reach a different file."""
    allowed = None                                # set by service("sheets")

    def __new__(cls, http, postproc, uri, *args, **kwargs):
        from googleapiclient.http import HttpRequest
        m = re.match(r"https://sheets\.googleapis\.com/v4/spreadsheets/([A-Za-z0-9_-]+)(?=[/?:]|$)", uri)
        if not cls.allowed or not m or m.group(1) != cls.allowed:
            raise GoogleError("forbidden", "I'm only allowed to open your SE tracker sheet, sir.",
                              f"blocked a Sheets request outside the tracker: {uri.split('?')[0][:120]}")
        return HttpRequest(http, postproc, uri, *args, **kwargs)


def service(api):
    """api: calendar | gmail | drive | sheets. Built from the bundled discovery documents (no fetch)."""
    from googleapiclient.discovery import build
    creds = credentials()
    name, version = {"calendar": ("calendar", "v3"), "gmail": ("gmail", "v1"), "drive": ("drive", "v3"),
                     "sheets": ("sheets", "v4")}[api]
    extra = {}
    if api == "sheets":
        sid = tracker_id()
        if not sid:
            raise GoogleError("not_configured", "Your SE tracker sheet isn't set up yet, sir. Run orrin tracker find.",
                              "no tracker spreadsheet id in the keyring")
        SheetGuard.allowed = sid
        extra["requestBuilder"] = SheetGuard
    key = (api, creds.token, SheetGuard.allowed if extra else None)
    if key not in _services:
        if len(_services) > 6:                    # old access tokens
            _services.clear()
        _services[key] = build(name, version, credentials=creds, cache_discovery=False, **extra)
    return _services[key]


def call(what, req):
    """Execute a request, turning Google's errors into GoogleError. what: calendar | gmail | drive | assignments."""
    import httplib2
    from googleapiclient.errors import HttpError
    try:
        from googleapiclient.http import BatchHttpRequest
        return req.execute() if isinstance(req, BatchHttpRequest) else req.execute(num_retries=1)
    except HttpError as e:
        raise translate(what, e.resp.status, e.content) from None
    except (httplib2.HttpLib2Error, OSError, TimeoutError) as e:
        raise GoogleError("offline", "I can't reach Google right now, sir.", f"{type(e).__name__}: {e}") from None


def translate(what, status, content):
    """Google's JSON error → GoogleError with a line worth saying."""
    try:
        err = json.loads(content or b"{}").get("error", {})
    except ValueError:
        err = {}
    msg = str(err.get("message", ""))
    reasons = {str(x.get("reason", "")) for x in err.get("errors", [])} | {str(x.get("reason", "")) for x in err.get("details", [])}
    api = API_NAMES.get(what, "Google")
    if status == 403 and ({"accessNotConfigured", "SERVICE_DISABLED"} & reasons or "has not been used in project" in msg
                          or "is disabled" in msg):
        link = re.search(r"https://console\.developers\.google\.com/\S+|https://console\.cloud\.google\.com/\S+", msg)
        return GoogleError("api_disabled",
                           f"The {api} API isn't turned on in your Google Cloud project, sir. The link to enable it is in the log.",
                           f"{api} API not enabled: {link.group(0).rstrip('.') if link else msg}")
    if status in (401, 403) and ({"insufficientPermissions", "ACCESS_TOKEN_SCOPE_INSUFFICIENT"} & reasons
                                 or "insufficient authentication scopes" in msg.lower()):
        box = SCOPES.get(NEEDS.get(what, ""), api)
        return GoogleError("scope", f"I don't have permission for {api}, sir. Reconnect Google and tick the {box.split(' (')[0]} box.",
                           f"missing scope for {what}: {NEEDS.get(what)} ({box})")
    if what == "calendar_write" and status == 403 and ({"requiredAccessLevel", "forbidden"} & reasons):
        return GoogleError("readonly", "That calendar is read-only for me, sir, so I can't change it there.",
                           f"calendar write refused: {msg[:200]}")
    if status == 401:
        return GoogleError("expired", "Your Google sign-in has expired, sir. Reconnect it in Settings, under Orrin.", msg)
    return GoogleError("http", f"{api} returned an error, sir.", f"HTTP {status}: {msg[:300]}")


# ── time ──
def tz():
    return ZoneInfo(local_tz())


def parse_when(t):
    """An event's start / end dict → (aware datetime in local time, all_day)."""
    z = tz()
    if "dateTime" in t:
        return datetime.fromisoformat(t["dateTime"].replace("Z", "+00:00")).astimezone(z), False
    return datetime.fromisoformat(t["date"]).replace(tzinfo=z), True


def clock(d):
    """4:30 PM / noon / midnight: how Orrin says a time."""
    if d.hour == 12 and d.minute == 0:
        return "noon"
    if d.hour == 0 and d.minute == 0:
        return "midnight"
    return d.strftime("%-I:%M %p").replace(":00 ", " ")


def day_name(d, now):
    if d.date() == now.date():
        return "today"
    if d.date() == (now + timedelta(days=1)).date():
        return "tomorrow"
    n = d.day
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return d.strftime(f"%A the {n}{suffix}" if (d - now).days < 6 else f"%A, %B {n}{suffix}")


# ── calendar (read) ──
def calendars():
    """Every calendar in his list that isn't hidden: [(id, name, primary)]."""
    items = call("calendar", service("calendar").calendarList().list(
        maxResults=250, fields="items(id,summary,summaryOverride,primary,hidden,selected)")).get("items", [])
    return [(c["id"], c.get("summaryOverride") or c.get("summary") or c["id"], bool(c.get("primary")))
            for c in items if not c.get("hidden")]


def events(start, end, per_calendar=50, primary_only=False):
    """All events overlapping [start, end) across his calendars (or just his main one), declined ones dropped, sorted."""
    svc, out = service("calendar"), []
    cals = [("primary", "", True)] if primary_only else calendars()
    for cid, cname, primary in cals:
        items = call("calendar", svc.events().list(
            calendarId=cid, timeMin=start.isoformat(), timeMax=end.isoformat(), singleEvents=True,
            orderBy="startTime", maxResults=per_calendar, timeZone=local_tz(),
            fields="items(id,iCalUID,summary,location,start,end,status,attendees(self,responseStatus),hangoutLink)")).get("items", [])
        for e in items:
            if e.get("status") == "cancelled":
                continue
            if any(a.get("self") and a.get("responseStatus") == "declined" for a in e.get("attendees", [])):
                continue
            s, all_day = parse_when(e["start"])
            en, _ = parse_when(e.get("end") or e["start"])
            out.append({"start": s, "end": en, "all_day": all_day, "title": e.get("summary") or "(no title)",
                        "where": e.get("location") or ("video call" if e.get("hangoutLink") else ""),
                        "calendar": "" if primary else cname, "uid": e.get("iCalUID", ""),
                        "source": "Google" if primary else f"Google · {cname}"})
    return sorted(out, key=lambda e: (not e["all_day"], e["start"]))


def describe(e, now):
    """Event → plain fields for the model (it phrases them; times already said the human way)."""
    d = {"title": e["title"], "day": day_name(e["start"], now)}
    if e["all_day"]:
        d["when"] = "all day"
    else:
        d["when"] = f"{clock(e['start'])} to {clock(e['end'])}"
        if e["start"] <= now < e["end"]:
            d["status"] = "happening now"
        elif e["end"] <= now:
            d["status"] = "already over"
        else:
            mins = int((e["start"] - now).total_seconds() // 60)
            if mins < 180:
                d["starts_in_minutes"] = mins
    if e["where"]:
        d["where"] = e["where"]
    if e.get("sources") or e.get("source"):
        d["source_if_asked"] = " and ".join(e.get("sources") or [e["source"]])
    return d


# ── gmail (read: metadata + snippets) ──
def messages(query, limit):
    """Gmail messages matching query → [{from, subject, date, snippet, unread}], newest first."""
    svc = service("gmail")
    ids = call("gmail", svc.users().messages().list(userId="me", q=query, maxResults=max(1, min(limit, 25)),
                                                    fields="messages(id)")).get("messages", [])
    got = {}

    def keep(rid, resp, exc):
        if exc is None:
            got[rid] = resp
    batch = svc.new_batch_http_request(callback=keep)
    for m in ids:
        batch.add(svc.users().messages().get(userId="me", id=m["id"], format="metadata",
                                             metadataHeaders=["From", "Subject", "Date"],
                                             fields="id,snippet,labelIds,internalDate,payload/headers"),
                  request_id=m["id"])
    if ids:
        call("gmail", batch)
    z, now, out = tz(), datetime.now(tz()), []
    for m in ids:
        r = got.get(m["id"])
        if not r:
            continue
        h = {x["name"].lower(): x["value"] for x in r.get("payload", {}).get("headers", [])}
        when = datetime.fromtimestamp(int(r.get("internalDate", "0")) / 1000, z)
        sender = re.sub(r'\s*<[^>]+>$', "", h.get("from", "")).strip('" ') or h.get("from", "")
        out.append({"from": sender, "subject": h.get("subject", "(no subject)"),
                    "when": f"{day_name(when, now)} at {clock(when)}", "snippet": r.get("snippet", "")[:220],
                    "unread": "UNREAD" in r.get("labelIds", [])})
    return out


def unread_count():
    return call("gmail", service("gmail").users().labels().get(userId="me", id="INBOX", fields="messagesUnread")).get("messagesUnread", 0)


# ── drive (read: metadata only) ──
def drive_search(query, limit):
    q = query.replace("\\", "\\\\").replace("'", "\\'")
    resp = call("drive", service("drive").files().list(
        q=f"(name contains '{q}' or fullText contains '{q}') and trashed = false", pageSize=max(1, min(limit, 20)),
        fields="files(name,mimeType,modifiedTime,owners(displayName,me),webViewLink)",
        includeItemsFromAllDrives=True, supportsAllDrives=True, corpora="allDrives"))
    kinds = {"document": "doc", "spreadsheet": "sheet", "presentation": "slides", "folder": "folder", "pdf": "PDF"}
    now, out = datetime.now(tz()), []
    for f in resp.get("files", []):
        mt = f.get("mimeType", "")
        kind = next((v for k, v in kinds.items() if k in mt), mt.rsplit("/", 1)[-1])
        mod = datetime.fromisoformat(f["modifiedTime"].replace("Z", "+00:00")).astimezone(tz()) if f.get("modifiedTime") else None
        owner = next((o.get("displayName") for o in f.get("owners", []) if not o.get("me")), "")
        out.append({"name": f.get("name", ""), "kind": kind,
                    **({"modified": day_name(mod, now) if (now - mod).days < 6 else mod.strftime("%B %-d, %Y")} if mod else {}),
                    **({"owner": owner} if owner else {}), "link": f.get("webViewLink", "")})
    return out


# ── the one write: the app's own "STARK – Assignments" calendar ──
class AssignmentsCalendar:
    """Events for LEARN assignments, in a calendar this app created (calendar.app.created can't
    touch any other). Each event carries extendedProperties.private.starkKey = academic.key(), so
    a re-sync updates instead of duplicating."""

    def __init__(self, name):
        self.name = name
        self.svc = service("calendar")

    def calendar_id(self, create=True):
        cid = secrets.get("google", "assignments_calendar")
        if cid:
            try:
                call("assignments", self.svc.calendars().get(calendarId=cid, fields="id"))
                return cid
            except GoogleError as e:
                if e.kind not in ("http", "scope"):
                    raise                                   # 404 (deleted) or 403 (not ours) → make a fresh one
        if not create:
            return None
        cal = call("assignments", self.svc.calendars().insert(
            body={"summary": self.name, "timeZone": local_tz(),
                  "description": "LEARN assignment due dates, written by Orrin (AlchemOS). Orrin never writes to any other calendar."},
            fields="id"))
        secrets.store("google", "assignments_calendar", cal["id"])
        return cal["id"]

    def find(self, cid, key):
        items = call("assignments", self.svc.events().list(
            calendarId=cid, privateExtendedProperty=f"starkKey={key}", maxResults=5, singleEvents=True,
            fields="items(id,summary,start,end,description)")).get("items", [])
        return items[0] if items else None

    def upsert(self, ev):
        """ev: academic.event_for(...). → ("created" | "updated" | "unchanged", event id)."""
        cid = self.calendar_id()
        body = {"summary": ev["summary"], "description": ev["description"],
                "start": {"dateTime": ev["start"].isoformat(), "timeZone": local_tz()},
                "end": {"dateTime": ev["end"].isoformat(), "timeZone": local_tz()},
                "reminders": {"useDefault": False, "overrides": [{"method": "popup", "minutes": ev["reminder_min"]}]},
                "extendedProperties": {"private": {"starkKey": ev["key"]}},
                **({"source": {"title": "LEARN", "url": ev["url"]}} if ev.get("url") else {})}
        old = self.find(cid, ev["key"])
        if old is None:
            made = call("assignments", self.svc.events().insert(calendarId=cid, body=body, fields="id"))
            return "created", made["id"]
        same_time = parse_when(old["start"])[0] == ev["start"].astimezone(tz()) and parse_when(old["end"])[0] == ev["end"].astimezone(tz())
        if same_time and old.get("description") == body["description"] and old.get("summary", "").removeprefix("✓ ") == body["summary"]:
            return "unchanged", old["id"]
        if old.get("summary", "").startswith("✓ "):
            body["summary"] = old["summary"]                # already graded: keep the tick
        call("assignments", self.svc.events().patch(calendarId=cid, eventId=old["id"], body=body, fields="id"))
        return "updated", old["id"]

    def mark_graded(self, key, graded_summary):
        cid = self.calendar_id(create=False)
        old = self.find(cid, key) if cid else None
        if not old:
            return False
        new = graded_summary(old.get("summary", ""))
        if new != old.get("summary"):
            call("assignments", self.svc.events().patch(calendarId=cid, eventId=old["id"], body={"summary": new}, fields="id"))
        return True


# ── writes to his main calendar ──
WRITABLE_ROLES = ("owner", "writer")
EVENT_FIELDS = ("summary", "description", "location", "start", "end", "colorId", "reminders", "transparency")


def event_fields(ev, fields=EVENT_FIELDS):
    """The parts of an event Orrin writes (and compares for undo)."""
    return {f: ev[f] for f in fields if f in ev}


class CalendarWriter:
    """The only code that writes to his own calendars (besides AssignmentsCalendar's own one).
    One instance = one batch in orrin_db.calendar_log, so `orrin calendar undo` reverts it whole.
    Targets: his main calendar, and the STARK – Assignments calendar (cleanup). A subscribed or
    read-only calendar (UW Flow schedule…) raises GoogleError("readonly") with a reason worth
    saying; any other calendar of his is refused too. Callers ask him first: nothing here asks."""

    def __init__(self, source="voice", link=None, svc=None, db=None):
        self.svc = svc or service("calendar")
        if db is None:
            import orrin_db as db
        self.db = db
        self.source, self.link = source, link
        self.batch = __import__("uuid").uuid4().hex[:12]
        self._cals = None
        self.wrote = 0

    def _call(self, req):
        return call("calendar_write", req)

    def calendars(self):
        if self._cals is None:
            items = call("calendar", self.svc.calendarList().list(
                maxResults=250, fields="items(id,summary,summaryOverride,primary,accessRole)")).get("items", [])
            self._cals = [{"id": c["id"], "name": c.get("summaryOverride") or c.get("summary") or c["id"],
                           "primary": bool(c.get("primary")), "role": c.get("accessRole", "")} for c in items]
        return self._cals

    def main_id(self):
        return next((c["id"] for c in self.calendars() if c["primary"]), "primary")

    def check(self, cid):
        """→ the calendar's name if Orrin may write to it, else GoogleError("readonly" | "forbidden")."""
        cid = self.main_id() if cid in (None, "", "primary", "main") else cid
        cal = next((c for c in self.calendars() if c["id"] == cid), None)
        if cal is None:
            raise GoogleError("forbidden", "I can't find that calendar in your list, sir.", f"calendar {cid[:60]} not in calendarList")
        if cal["role"] not in WRITABLE_ROLES:
            raise GoogleError("readonly", f"{cal['name']} is a subscribed, read-only calendar, sir, so I can't change it there. "
                              "It has to change at its source." if "import.calendar.google.com" in cid or cal["role"] == "reader"
                              else f"You only have view access to {cal['name']}, sir, so I can't change it.",
                              f"calendar {cal['name']!r} access role {cal['role']!r}")
        assignments = secrets.get("google", "assignments_calendar")
        if not cal["primary"] and cid != assignments:
            raise GoogleError("forbidden", f"I only edit your main calendar, sir, not {cal['name']}.",
                              f"calendar {cal['name']!r} is not the main calendar")
        return cid, cal["name"]

    def get(self, cid, eid):
        cid, _ = self.check(cid)
        return self._call(self.svc.events().get(calendarId=cid, eventId=eid))

    def create(self, cid, body):
        cid, _ = self.check(cid)
        made = self._call(self.svc.events().insert(calendarId=cid, body=body))
        self.db.log_calendar(self.batch, cid, made["id"], "create", made.get("summary", ""), None,
                             event_fields(made), self.source, self.link)
        self.wrote += 1
        return made

    def update(self, cid, eid, changes, extra=None):
        """Patch only `changes` (EVENT_FIELDS). extra: fields sent but not undone (eventLabelId).
        → the event after, or None if nothing differed."""
        cid, _ = self.check(cid)
        cur = self._call(self.svc.events().get(calendarId=cid, eventId=eid))
        if cur.get("status") == "cancelled":
            raise GoogleError("http", "That event has been deleted, sir.", f"event {eid} is cancelled")
        diff = {f: v for f, v in changes.items() if cur.get(f) != v}
        if not diff:
            return None
        body = dict(diff, **{k: v for k, v in (extra or {}).items() if cur.get(k) != v})
        try:
            after = self._call(self.svc.events().patch(calendarId=cid, eventId=eid, body=body))
        except GoogleError as e:
            if not extra or e.kind != "http":
                raise
            after = self._call(self.svc.events().patch(calendarId=cid, eventId=eid, body=diff))
        before = {f: cur.get(f) for f in diff}
        self.db.log_calendar(self.batch, cid, eid, "update", after.get("summary", ""), before,
                             {f: after.get(f) for f in diff}, self.source, self.link)
        self.wrote += 1
        return after

    def delete(self, cid, eid):
        cid, _ = self.check(cid)
        cur = self._call(self.svc.events().get(calendarId=cid, eventId=eid))
        if cur.get("status") == "cancelled":
            return False
        self._call(self.svc.events().delete(calendarId=cid, eventId=eid))
        self.db.log_calendar(self.batch, cid, eid, "delete", cur.get("summary", ""), cur, None, self.source, self.link)
        self.wrote += 1
        return True

    def undo(self, link=None):
        """Revert the newest batch not undone (or the one that followed tracker batch `link`) if every
        event still looks the way Orrin left it. → (ok, message)."""
        writes = self.db.last_calendar_batch(link)
        if not writes:
            return (True, "") if link else (False, "Nothing to undo on the calendar.")
        plan = []
        for w in writes:                                    # newest first
            cur = None
            try:
                cur = self._call(self.svc.events().get(calendarId=w["calendar"], eventId=w["event"]))
            except GoogleError as e:
                if w["kind"] != "delete" or e.kind != "http":
                    raise
            gone = cur is None or cur.get("status") == "cancelled"
            if w["kind"] == "delete":
                if not gone:
                    return False, f"{w['summary']} is back on the calendar already; not undoing."
            elif gone:
                return False, f"{w['summary']} has been deleted since Orrin wrote it; not undoing."
            elif any(cur.get(f) != v for f, v in (w["new"] or {}).items()):
                return False, f"{w['summary']} has changed since Orrin wrote it; not undoing."
            plan.append((w, cur))
        undo_batch = __import__("uuid").uuid4().hex[:12]
        done = []
        for w, cur in plan:
            if w["kind"] == "create":
                self._call(self.svc.events().delete(calendarId=w["calendar"], eventId=w["event"]))
                self.db.log_calendar(undo_batch, w["calendar"], w["event"], "delete", w["summary"], w["new"], None, "undo")
                done.append(f"removed {w['summary']}")
            elif w["kind"] == "update":
                self._call(self.svc.events().patch(calendarId=w["calendar"], eventId=w["event"], body=w["old"]))
                self.db.log_calendar(undo_batch, w["calendar"], w["event"], "update", w["summary"], w["new"], w["old"], "undo")
                done.append(f"put back {w['summary']}")
            else:
                try:                                        # a deleted event lingers as cancelled: un-cancel it
                    self._call(self.svc.events().patch(calendarId=w["calendar"], eventId=w["event"],
                                                       body={"status": "confirmed"}))
                    eid = w["event"]
                except GoogleError:
                    body = {k: v for k, v in w["old"].items() if k not in ("id", "etag", "iCalUID", "htmlLink", "created",
                                                                           "updated", "creator", "organizer", "sequence", "status")}
                    eid = self._call(self.svc.events().insert(calendarId=w["calendar"], body=body))["id"]
                self.db.log_calendar(undo_batch, w["calendar"], eid, "create", w["summary"], None,
                                     event_fields(w["old"]), "undo")
                done.append(f"restored {w['summary']}")
        self.db.mark_calendar_undone(writes[0]["batch"])
        return True, "Undid on the calendar: " + "; ".join(done)


def _kick_feed():
    """A calendar write: the HUD's calendar widget refreshes now (core/feed.py), not at its next sync."""
    import socket
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)      # same as core/feed.kick (MCP servers may lack core/)
        s.sendto(b"kick", os.path.join(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}", "orrin", "feed.sock"))
        s.close()
    except OSError:
        pass


for _name in ("create", "update", "delete", "undo"):
    def _wrap(fn):
        def w(self, *a, **k):
            try:
                return fn(self, *a, **k)
            finally:
                _kick_feed()
        w.__name__, w.__doc__ = fn.__name__, fn.__doc__
        return w
    setattr(CalendarWriter, _name, _wrap(getattr(CalendarWriter, _name)))
for _name in ("upsert", "mark_graded"):
    setattr(AssignmentsCalendar, _name, (lambda fn: (lambda self, *a, **k: (fn(self, *a, **k), _kick_feed())[0]))(getattr(AssignmentsCalendar, _name)))


def calendar_cli(argv):
    """orrin calendar log [N] | undo"""
    from datetime import datetime as _dt
    import orrin_db as db
    cmd, rest = (argv[0] if argv else "log"), argv[1:]
    if cmd == "log":
        for w in reversed(db.calendar_writes(int(rest[0]) if rest else 20)):
            ts = _dt.fromtimestamp(w["ts"]).strftime("%m-%d %H:%M")
            when = lambda f: (f or {}).get("start", {}).get("date") or (f or {}).get("start", {}).get("dateTime", "")[:16]
            moved = f"  {when(w['old'])} → {when(w['new'])}" if w["kind"] == "update" and "start" in (w["new"] or {}) else ""
            flag = " (undone)" if w["undone"] else ""
            print(f"{ts}  {w['batch']}  {w['source']:<8} {w['kind']:<6} {w['summary'][:60]:<60}{moved}{flag}"
                  + (f"  [tracker {w['link']}]" if w["link"] else ""))
        return 0
    if cmd == "undo":
        try:
            ok, msg = CalendarWriter("undo").undo()
        except GoogleError as e:
            print(f"{e.say}\n  ({e.kind}: {e.detail})")
            return 1
        print(msg)
        return 0 if ok else 1
    print("usage: orrin calendar log [N] | undo")
    return 2
