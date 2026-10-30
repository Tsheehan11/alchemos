"""
Outlook calendar through its published ICS link (Outlook on the web → Settings → Calendar →
Shared calendars → Publish), because UWaterloo blocks the Microsoft Graph app route.

The URL is a secret (anyone with it can read the calendar): keyring "jarvis:outlook" / ical_url,
stored by `jarvis connect outlook-ical`, which prompts for it so it never lands in shell history.
The feed is cached in ~/.local/share/jarvis/outlook.ics (mode 600) and refreshed when older than
REFRESH_S: by the voice loop every ~15 min while docked, or on demand by the calendar tools.
Recurring events (weekly classes, exceptions, cancellations) and Outlook's Windows time-zone
names are handled by icalendar + recurring-ical-events.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from integration_common import secrets

DATA = Path.home() / ".local/share/jarvis"
CACHE = DATA / "outlook.ics"
META = DATA / "outlook.json"          # {"fetched", "ok", "error", "etag", "modified", "events"}
REFRESH_S = 15 * 60
MAX_BYTES = 20_000_000


class FeedError(Exception):
    pass


def url():
    return secrets.get("outlook", "ical_url")


def normalize_url(raw):
    """'webcal://…' → 'https://…'; anything not https is refused."""
    u = (raw or "").strip().strip("<>\"'")
    if u.startswith("webcal://"):
        u = "https://" + u[len("webcal://"):]
    p = urllib.parse.urlparse(u)
    if p.scheme != "https" or not p.netloc:
        raise FeedError("expected an https:// (or webcal://) calendar link")
    return u


def meta():
    try:
        return json.loads(META.read_text())
    except (OSError, ValueError):
        return {}


def _save(path, data, mode=0o600):
    DATA.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    os.chmod(tmp, mode)
    tmp.replace(path)


def fetch(link=None, force=False, timeout=20):
    """Refresh the cache if it's older than REFRESH_S (or force). Conditional GET, so an unchanged
    feed costs one 304. Returns the meta dict; raises FeedError only when there's nothing usable."""
    link = link or url()
    if not link:
        raise FeedError("not connected")
    m = meta()
    if not force and CACHE.exists() and time.time() - m.get("fetched", 0) < REFRESH_S:
        return m
    headers = {"User-Agent": "stark-jarvis/2"}
    if CACHE.exists() and not force:
        if m.get("etag"):
            headers["If-None-Match"] = m["etag"]
        if m.get("modified"):
            headers["If-Modified-Since"] = m["modified"]
    try:
        with urllib.request.urlopen(urllib.request.Request(link, headers=headers), timeout=timeout) as r:
            body = r.read(MAX_BYTES + 1)
            if len(body) > MAX_BYTES:
                raise FeedError("the calendar feed is too large")
            cal = parse(body)                       # don't replace a good cache with junk
            _save(CACHE, body)
            m = {"fetched": time.time(), "ok": True, "error": "", "etag": r.headers.get("ETag", ""),
                 "modified": r.headers.get("Last-Modified", ""), "events": sum(1 for _ in cal.walk("VEVENT"))}
    except urllib.error.HTTPError as e:
        if e.code == 304:
            m.update(fetched=time.time(), ok=True, error="")
        else:
            m.update(fetched=time.time(), ok=False, error=f"HTTP {e.code}")
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        m.update(ok=False, error=f"unreachable: {getattr(e, 'reason', e)}")   # keep `fetched`: retry next time
    except FeedError as e:
        m.update(fetched=time.time(), ok=False, error=str(e))
    except ValueError as e:
        m.update(fetched=time.time(), ok=False, error=f"not a calendar: {e}"[:200])
    _save(META, json.dumps(m).encode())
    if not CACHE.exists():
        raise FeedError(m.get("error") or "no calendar data")
    return m


def parse(data):
    import icalendar
    try:
        import x_wr_timezone                      # feeds that name their zone only in X-WR-TIMEZONE
        cal = x_wr_timezone.to_standard(icalendar.Calendar.from_ical(data))
    except ImportError:
        cal = icalendar.Calendar.from_ical(data)
    if cal.name != "VCALENDAR":
        raise ValueError("no VCALENDAR")
    return cal


def _local(v, tz):
    if isinstance(v, datetime):
        return v.astimezone(tz) if v.tzinfo else v.replace(tzinfo=tz)   # floating = local
    return datetime(v.year, v.month, v.day, tzinfo=tz)


def events(start, end, tz=None):
    """Events overlapping [start, end) from the cached feed, recurrences expanded, in local time.
    Same shape as google_api.events(), plus "uid" and "source"."""
    import recurring_ical_events
    tz = tz or start.tzinfo or ZoneInfo("America/Toronto")
    if not CACHE.exists():
        return []
    cal = parse(CACHE.read_bytes())
    out = []
    for ev in recurring_ical_events.of(cal).between(start, end):
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        s = ev.decoded("DTSTART")
        all_day = isinstance(s, date) and not isinstance(s, datetime)
        e = ev.decoded("DTEND") if ev.get("DTEND") else (s + ev.decoded("DURATION") if ev.get("DURATION")
                                                         else s + (timedelta(days=1) if all_day else timedelta(0)))
        out.append({"start": _local(s, tz), "end": _local(e, tz), "all_day": all_day,
                    "title": str(ev.get("SUMMARY") or "Busy"), "where": str(ev.get("LOCATION") or ""),
                    "calendar": "Outlook", "uid": str(ev.get("UID") or ""), "source": "Outlook"})
    return sorted(out, key=lambda e: (not e["all_day"], e["start"]))
