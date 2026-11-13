"""
Data for the HUD's calendar / due / weather widgets: `jarvis feed` (started by quickshell
OrrinFeed.qml only while such a widget is up; it exits with the HUD).

Writes, only when the content changed (FileView in the HUD watches them, so the HUD never polls):
  ~/.local/share/jarvis/feed/agenda.json
      {"updated", "ok", "notes": [...], "events": [{"title", "start", "end" (ms epoch), "all_day", "where",
        "source": "google" | "outlook" | "both", "kind": "event", "tracker": true if it's a tracker row's event}],
       "due": [{"title", "course", "label", "due" (ms, end of that day), "days", "status", "kind": "due"}]  (rows with no
               calendar event of their own; link_due), "due_all": every open row (the due widget)}
  ~/.local/share/jarvis/feed/weather.json
      stark_actions.weather() for the home town (jarvisPlace), plus "updated"

Sources: his main Google Calendar (not the other calendars in his list, so the "STARK – Assignments"
copies of tracker rows don't double up), the Outlook ICS link and the SE tracker's open rows.
No Claude anywhere. Timing:
  calendars   every AGENDA_S, and at once when kicked (kick() is called after Jarvis writes to the
              calendar or the tracker: a datagram to $XDG_RUNTIME_DIR/jarvis/feed.sock)
  tracker     every TRACKER_S (a Sheets read), and when kicked
  weather     every WEATHER_S
Each source keeps its last good data when a refresh fails; "notes" says what's stale.
"""
import datetime as _dt
import hashlib
import re
import json
import os
import select
import socket
import sys
import time

from . import config as C

FEED_DIR = C.DATA_DIR / "feed"
SOCK = C.RUNTIME / "jarvis" / "feed.sock"
AGENDA_S = 180
TRACKER_S = 15 * 60
WEATHER_S = 30 * 60
DAYS = 7


def kick():
    """Ask a running feed to refresh now (after a calendar / tracker write). Silent if none runs."""
    try:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        s.sendto(b"kick", str(SOCK))
        s.close()
    except OSError:
        pass


def _ms(d):
    return int(d.timestamp() * 1000)


def _write(name, data):
    """Write if the content (not the timestamp) changed. → True if written."""
    body = {k: v for k, v in data.items() if k != "updated"}
    digest = hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()
    path = FEED_DIR / name
    try:
        old = json.loads(path.read_text())
        if old.get("_digest") == digest:
            return False
    except (OSError, ValueError):
        pass
    FEED_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(dict(data, _digest=digest), ensure_ascii=False, default=str))
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return True


def _words(s):
    return set(re.findall(r"[a-z]+\d*|\d+", (s or "").lower()))


def link_due(events, due):
    """His tracker's own Apps Script puts each row on his main calendar as an all-day event ("[MATH 135]
    Weekly assessment W6"), so the same deliverable would show twice. An all-day event on a row's due day
    that names its course and its assignment becomes that row: marked "tracker" (shown ▲), and the row
    itself is dropped from "due" for the agenda (it stays in "due_all" for the due widget)."""
    out_ev, linked = [], set()
    for e in events:
        e = dict(e)
        if e.get("all_day"):
            day = _dt.datetime.fromtimestamp(e["start"] / 1000).date()
            title = _words(e["title"])
            for i, d in enumerate(due):
                if i in linked or _dt.datetime.fromtimestamp(d["due"] / 1000).date() != day:
                    continue
                course = _words(d.get("course"))
                ident = _words(d.get("label", "")) - course
                if course <= title and (ident <= title or len(_words(d["title"]) & title) >= max(1, len(_words(d["title"])) - 1)):
                    linked.add(i)
                    e.update(tracker=True, status=d.get("status"), days=d.get("days"))
                    break
        out_ev.append(e)
    return out_ev, [d for i, d in enumerate(due) if i not in linked]


class Feed:
    def __init__(self, log=print):
        self.log = log
        self.events, self.due, self.notes = None, None, {}
        self.next_cal = self.next_tracker = self.next_weather = 0.0

    # ── sources ──
    def calendars(self):
        import calendars as CAL
        import google_api as G
        import outlook_ical as O
        from integration_common import secrets
        tz = G.tz()
        now = _dt.datetime.now(tz)
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + _dt.timedelta(days=DAYS + 1)
        evs, notes, tried, failed = [], [], 0, 0
        if secrets.has("google", "token"):
            tried += 1
            try:
                evs += G.events(start, end, per_calendar=40, primary_only=True)
            except G.GoogleError as e:
                failed += 1
                notes.append("google: " + (e.detail or e.kind))
        if O.url():
            tried += 1
            try:
                m = O.fetch()
                evs += O.events(start, end, tz)
                if not m.get("ok"):
                    notes.append("outlook: " + (m.get("error") or "not updating"))
            except Exception as e:
                failed += 1
                notes.append(f"outlook: {e}")
        if not tried:
            self.notes["calendar"] = "calendar not connected"
            self.events = []
            return
        if failed == tried and self.events is not None:
            self.notes["calendar"] = "; ".join(notes)       # keep the last good list
            return
        out = []
        for e in CAL.dedupe(evs):
            srcs = " ".join(e.get("sources") or [e.get("source", "")]).lower()
            src = "both" if "google" in srcs and "outlook" in srcs else "outlook" if "outlook" in srcs else "google"
            if not e["all_day"] and e["end"] <= now:
                continue                                   # over
            out.append({"title": e["title"], "start": _ms(e["start"]), "end": _ms(e["end"]), "all_day": e["all_day"],
                        "where": e.get("where") or "", "source": src, "kind": "event"})
        self.events = out
        self.notes["calendar"] = "; ".join(notes)

    def tracker(self):
        import google_api as G
        import tracker as T
        if not G.tracker_id():
            self.due = []
            self.notes["tracker"] = ""
            return
        try:
            rows = T.Tracker().load()
        except Exception as e:
            self.notes["tracker"] = f"tracker: {getattr(e, 'detail', '') or e}"
            if self.due is None:
                self.due = []
            return
        today = _dt.date.today()
        soon, late = T.pending(rows, days=DAYS * 2, today=today, overdue_days=7)
        out = []
        for r in late + soon:
            end_of_day = _dt.datetime.combine(r["due"], _dt.time(23, 59))
            out.append({"title": r["title"], "course": r["course"], "label": T.label(r), "due": _ms(end_of_day),
                        "days": (r["due"] - today).days, "status": r["status"] or "Not Started", "kind": "due"})
        self.due = out
        self.notes["tracker"] = ""

    def weather(self):
        import stark_actions as A
        r = A.weather("")
        if r.get("ok"):
            _write("weather.json", dict(r, updated=time.time()))
        else:
            self.log(f"feed: weather: {r.get('error')}")

    # ── loop ──
    def refresh(self, force=False):
        now = time.monotonic()
        changed = False
        if force or now >= self.next_cal:
            try:
                self.calendars()
            except Exception as e:
                self.notes["calendar"] = f"{type(e).__name__}: {e}"[:200]
            self.next_cal = now + AGENDA_S
            changed = True
        if force or now >= self.next_tracker:
            try:
                self.tracker()
            except Exception as e:
                self.notes["tracker"] = f"{type(e).__name__}: {e}"[:200]
            self.next_tracker = now + TRACKER_S
            changed = True
        if changed:
            notes = [n for n in self.notes.values() if n]
            events, due = link_due(self.events or [], self.due or [])
            if _write("agenda.json", {"updated": time.time(), "ok": not notes, "notes": notes,
                                      "events": events, "due": due, "due_all": self.due or []}):
                self.log(f"feed: agenda {len(self.events or [])} events, {len(self.due or [])} due")
        if now >= self.next_weather:
            try:
                self.weather()
            except Exception as e:
                self.log(f"feed: weather: {type(e).__name__}: {e}")
            self.next_weather = now + WEATHER_S

    def run(self):
        SOCK.parent.mkdir(parents=True, exist_ok=True)
        s = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            if SOCK.exists():
                probe = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
                try:
                    probe.connect(str(SOCK))       # a live feed answers connect; a stale file refuses
                    self.log("feed: already running")
                    return 0
                except OSError:
                    SOCK.unlink()
                finally:
                    probe.close()
            s.bind(str(SOCK))
        except OSError as e:
            self.log(f"feed: {e}")
            return 1
        os.chmod(SOCK, 0o600)
        import signal
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))       # the HUD stops it: clean up the socket
        try:
            self.refresh(force=True)
            while True:
                wait = max(1.0, min(self.next_cal, self.next_tracker, self.next_weather) - time.monotonic())
                r, _, _ = select.select([s], [], [], wait)
                if r:
                    s.recv(64)
                    time.sleep(1.5)                # let Google settle (a write is read back a moment later)
                    while select.select([s], [], [], 0)[0]:
                        s.recv(64)                 # several kicks → one refresh
                    self.log("feed: kicked")
                    self.refresh(force=True)
                else:
                    self.refresh()
        finally:
            try:
                SOCK.unlink()
            except OSError:
                pass


def main(argv):
    """jarvis feed [--once]"""
    f = Feed(log=lambda m: print(m, file=sys.stderr, flush=True))
    if "--once" in argv:
        f.refresh(force=True)
        f.weather()
        return 0
    if "--kick" in argv:
        kick()
        return 0
    return f.run()
