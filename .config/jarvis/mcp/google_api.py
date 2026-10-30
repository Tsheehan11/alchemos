"""
Google APIs for Jarvis (google-api-python-client), shared by google_tools.py and academic_tools.py.

Credentials come from the system keyring ("jarvis:google" / token, written by `jarvis connect
google`); a refreshed access token is written back so the next call doesn't refresh again.
Everything here is read-only except AssignmentsCalendar, which only ever touches the calendar
this app created ("STARK – Assignments"): the calendar.app.created scope can't reach any other.

Failures become GoogleError(kind, say, detail): `say` is a line Jarvis can speak, `detail` is
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
}
NEEDS = {"gmail": "https://www.googleapis.com/auth/gmail.readonly",
         "calendar": "https://www.googleapis.com/auth/calendar.readonly",
         "drive": "https://www.googleapis.com/auth/drive.readonly",
         "assignments": "https://www.googleapis.com/auth/calendar.app.created"}
API_NAMES = {"gmail": "Gmail", "calendar": "Google Calendar", "drive": "Google Drive", "assignments": "Google Calendar"}


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
    """Scopes Google actually granted at the last sign-in (stored by `jarvis connect google`), or None."""
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
            raise GoogleError("expired", "Your Google sign-in has expired, sir. Reconnect it in Settings, under Jarvis.",
                              f"refresh failed: {e}")
        except TransportError as e:
            raise GoogleError("offline", "I can't reach Google right now, sir.", str(e))
        info.update(json.loads(creds.to_json()))
        secrets.store("google", "token", json.dumps(info))
    return creds


_services = {}


def service(api):
    """api: calendar | gmail | drive. Built from the bundled discovery documents (no fetch)."""
    from googleapiclient.discovery import build
    creds = credentials()
    name, version = {"calendar": ("calendar", "v3"), "gmail": ("gmail", "v1"), "drive": ("drive", "v3")}[api]
    key = (api, creds.token)
    if key not in _services:
        if len(_services) > 6:                    # old access tokens
            _services.clear()
        _services[key] = build(name, version, credentials=creds, cache_discovery=False)
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
    if status == 401:
        return GoogleError("expired", "Your Google sign-in has expired, sir. Reconnect it in Settings, under Jarvis.", msg)
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
    """4:30 PM / noon / midnight: how Jarvis says a time."""
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


def events(start, end, per_calendar=50):
    """All events overlapping [start, end) across his calendars, declined ones dropped, sorted."""
    svc, out = service("calendar"), []
    for cid, cname, primary in calendars():
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
                  "description": "LEARN assignment due dates, written by Jarvis (STARK OS). Jarvis never writes to any other calendar."},
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
