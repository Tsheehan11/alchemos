"""
Academic sync: LEARN (D2L) assignments → a dedicated "STARK – Assignments" calendar,
and grade notices (LEARN / Crowdmark emails) → a ✓ on that assignment + a spoken line.

The pure parts live here (iCal parsing, de-duplication, event shape, grade-notice recognition
from email headers, the state file and announcement queue); academic_sync.py fetches the feed,
scans Gmail and writes the calendar, and academic_tools.py answers Claude.

Rules this module keeps no matter who calls it:
  * Writes only ever target ASSIGNMENTS_CALENDAR, never the main calendar. There is no
    parameter for the calendar, so nothing (the model included) can point it elsewhere.
  * A grade notice only counts if it comes from LEARN / D2L no-reply addresses or Crowdmark
    (also when UW forwarded it: the original sender is taken from the forwarding headers, or
    from Gmail's snippet of an "FW:" sent from his UW address), DKIM didn't fail, the subject
    says a grade or feedback was released, AND it names an assignment already in the LEARN feed.
    Headers and Gmail's snippet only; the body is never fetched. The only possible effects are
    the ✓ prefix on that one event and the announcement.
"""
import json
import re
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ASSIGNMENTS_CALENDAR = "STARK – Assignments"
GRADED = "✓ "
REMIND_BEFORE_MIN = 2 * 24 * 60
STATE_FILE = Path.home() / ".local/share/jarvis/academic.json"

COURSE = re.compile(r"\b([A-Z]{2,5})\s?(\d{3}[A-Z]?)\b")
DUE_NOISE = re.compile(r"\s*[-–:]?\s*\b(?:is )?(?:due|availability ends|ends|deadline)\b.*$", re.I)
# LEARN (D2L) notifications come from no-reply style addresses, never a person's @uwaterloo.ca
GRADE_SENDERS = re.compile(r"(?:^|[<\s])(?:(?:no-?reply|do-?not-?reply|notifications?|d2l)[\w.+-]*@(?:[\w-]+\.)*uwaterloo\.ca"
                           r"|[\w.+-]+@(?:[\w-]+\.)*(?:learn\.uwaterloo\.ca|crowdmark\.com|d2l\.com|desire2learn\.com))>?$", re.I)
AVAILABLE = re.compile(r"\s[-–]\s*available\s*$", re.I)
UW_ADDRESS = re.compile(r"[\w.+-]+@(?:[\w-]+\.)*uwaterloo\.ca>?$", re.I)
FW_PREFIX = re.compile(r"^\s*(?:(?:fw|fwd|tr|wg)\s*:\s*)+", re.I)
GRADE_SUBJECT = re.compile(r"\b(?:grades? (?:has been |have been |is |are )?(?:released|posted|available)|"
                           r"feedback (?:is )?(?:now )?(?:available|released)|new grade|has been graded|"
                           r"graded (?:assessment|work)|(?:has|have) been returned|results? (?:are |is )?available)\b", re.I)


# ── iCal (RFC 5545, just enough for a D2L feed) ──
def _unfold(text):
    return re.sub(r"\r?\n[ \t]", "", text).splitlines()


def _when(value, params):
    v = value.strip()
    if re.fullmatch(r"\d{8}", v) or params.get("VALUE") == "DATE":
        d = datetime.strptime(v[:8], "%Y%m%d")
        return d.replace(hour=23, minute=59)        # an all-day due date: end of that day, local
    utc = v.endswith("Z")
    d = datetime.strptime(v.rstrip("Z")[:15], "%Y%m%dT%H%M%S")
    if utc:
        return d.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)
    if "TZID" in params:
        try:
            return d.replace(tzinfo=ZoneInfo(params["TZID"])).astimezone().replace(tzinfo=None)
        except Exception:
            pass
    return d                                        # floating time = local


def parse_ical(text):
    """→ [{"uid", "course", "title", "due" (naive local datetime), "url"}] for events with a course code."""
    items, ev = [], None
    for line in _unfold(text):
        if line == "BEGIN:VEVENT":
            ev = {}
        elif line == "END:VEVENT" and ev is not None:
            items.append(ev)
            ev = None
        elif ev is not None and ":" in line:
            head, value = line.split(":", 1)
            name, *ps = head.split(";")
            params = dict(p.split("=", 1) for p in ps if "=" in p)
            ev[name.upper()] = (value.replace("\\,", ",").replace("\\;", ";").replace("\\n", " "), params)
    out = []
    for ev in items:
        summary = ev.get("SUMMARY", ("", {}))[0].strip()
        where = " ".join(ev.get(k, ("", {}))[0] for k in ("LOCATION", "CATEGORIES", "DESCRIPTION"))
        m = COURSE.search(summary) or COURSE.search(where)
        stamp = ev.get("DUE") or ev.get("DTEND") or ev.get("DTSTART")
        if not m or not stamp:
            continue
        course = f"{m.group(1)} {m.group(2)}"
        title = DUE_NOISE.sub("", COURSE.sub("", summary, count=1) if COURSE.search(summary) else summary)
        title = title.strip(" -–:") or summary
        out.append({"uid": ev.get("UID", ("", {}))[0], "course": course, "title": title,
                    "due": _when(*stamp), "url": ev.get("URL", ("", {}))[0]})
    return out


# ── de-duplication ──
def short_title(title):
    """'Assignment 5' / 'A5' / 'assignment #5 (programming)' → 'a5'; anything else, normalised words."""
    t = title.lower()
    m = re.search(r"\b(?:assignment|assn|asst|a)\s*#?\s*(\d+)\b", t)
    if m:
        return f"a{int(m.group(1))}"
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def key(course, title):
    return f"{course.replace(' ', '').upper()}|{short_title(title)}"


def is_availability(title):
    """'… Review - Available' / 'a5 provided code - Available': when material opens, not a deadline."""
    return bool(AVAILABLE.search(title or ""))


def dedupe(assignments):
    """Course + title → one assignment; a later copy (feed re-sync, a second source) updates the due date.
    An availability entry never overrides a real one with the same key ("Assignment 3: Rates of Reaction
    Review - Available", the next morning, is not when CHE 102 A3 is due)."""
    seen = {}
    for a in assignments:
        k = key(a["course"], a["title"])
        if k in seen:
            old_avail, new_avail = is_availability(seen[k]["title"]), is_availability(a["title"])
            if new_avail and not old_avail:
                continue
            if old_avail and not new_avail:
                seen[k] = dict(a, key=k)
                continue
            seen[k].update({f: v for f, v in a.items() if v and f != "title"})
        else:
            seen[k] = dict(a, key=k)
    return list(seen.values())


def event_for(a):
    """The event written to ASSIGNMENTS_CALENDAR: due time, course, link, a reminder two days before."""
    due = a["due"]
    lines = [f"Course: {a['course']}", f"Due: {due:%a %d %b %Y, %-I:%M %p}"] + ([f"Link: {a['url']}"] if a.get("url") else [])
    return {"calendar": ASSIGNMENTS_CALENDAR, "key": a.get("key") or key(a["course"], a["title"]),
            "summary": f"{a['course']} {a['title']}", "start": due - timedelta(minutes=30), "end": due,
            "description": "\n".join(lines), "url": a.get("url", ""), "reminder_min": REMIND_BEFORE_MIN}


def graded_summary(summary):
    return summary if summary.startswith(GRADED) else GRADED + summary


# ── grade notices ──
def grade_notice(sender, subject, known, dkim_pass=None):
    """sender, subject: headers of one email (the body is never read). known: assignments
    from the feed. → the matching assignment, or None. dkim_pass=False (the inbox said the
    signature failed) rejects it; None means the inbox didn't say."""
    if dkim_pass is False or not GRADE_SENDERS.search(sender.strip()) or not GRADE_SUBJECT.search(subject):
        return None
    m = COURSE.search(subject.upper())
    if not m:
        return None
    course = f"{m.group(1)} {m.group(2)}"
    rest = COURSE.sub("", subject.upper(), count=1)
    for a in known:
        if a["course"].replace(" ", "") != course.replace(" ", ""):
            continue
        st = short_title(a["title"])
        if (st and re.search(rf"\b{re.escape(st)}\b", short_title(rest))) or a["title"].lower() in rest.lower():
            return a
    return None


def _addr(value):
    """'Crowdmark <noreply@crowdmark.com>' → 'noreply@crowdmark.com' (SRS-rewritten bounce
    addresses are turned back into the original: SRS0=h=tt=crowdmark.com=noreply@… )."""
    m = re.search(r"<([^>]+)>", value or "") or re.search(r"[\w.+=-]+@[\w.-]+", value or "")
    a = (m.group(1) if m and m.lastindex else m.group(0) if m else "").strip().lower()
    srs = re.match(r"srs[01]=[^=]+=[^=]+=([^=]+)=([^@]+)@", a)
    return f"{srs.group(2)}@{srs.group(1)}" if srs else a


def notice_senders(headers, snippet=""):
    """Every address that might be the original sender of a (possibly forwarded) email.
    headers: {lower-case name: [values]}."""
    names = ("from", "sender", "reply-to", "x-original-from", "x-original-sender", "resent-from", "return-path")
    out = [_addr(v) for n in names for v in headers.get(n, []) if _addr(v)]
    subject = (headers.get("subject") or [""])[0]
    frm = _addr((headers.get("from") or [""])[0])
    if FW_PREFIX.match(subject) and UW_ADDRESS.search(frm):
        # an "FW:" from his UW address: Outlook puts the original "From: … <addr>" first in the body,
        # which is where Gmail's snippet starts
        m = re.search(r"From:\s*[^<\n]*<?([\w.+-]+@[\w.-]+)>?", snippet or "")
        if m:
            out.append(m.group(1).lower())
    return out


def dkim_verdict(headers):
    """True: a grade sender's DKIM signature passed (directly or per ARC, i.e. before forwarding).
    False: it explicitly failed and nothing vouches for it. None: the inbox doesn't say."""
    res = " ".join(headers.get("authentication-results", []) + headers.get("arc-authentication-results", []))
    domains = r"(?:[\w-]+\.)*(?:uwaterloo\.ca|crowdmark\.com|d2l\.com|desire2learn\.com)"
    if re.search(rf"dkim=pass[^;]*header\.[di]=@?{domains}\b", res, re.I):
        return True
    if re.search(rf"dkim=fail[^;]*header\.[di]=@?{domains}\b", res, re.I):
        return False
    return None


def notice_from_message(headers, snippet, known):
    """One Gmail message (headers {lower name: [values]} + snippet) → (assignment, source) or None."""
    subject = FW_PREFIX.sub("", (headers.get("subject") or [""])[0])
    dkim = dkim_verdict(headers)
    for sender in notice_senders(headers, snippet):
        a = grade_notice(sender, subject, known, dkim)
        if a:
            return a, ("Crowdmark" if "crowdmark" in sender else "LEARN")
    return None


def spoken_course(a):
    st = short_title(a["title"])
    return f"{a['course']} {st.upper() if re.fullmatch(r'a[0-9]+', st) else a['title']}"


def announcement(a):
    return f"Sir, your {spoken_course(a)} has been graded."


# ── state: known assignments + what's waiting to be said ──
STATE_KEYS = {"assignments": dict, "graded": list, "announce": list, "announced": list, "synced": dict, "seen_msgs": list,
              "tracker_events": list, "tracker_offers": list, "tracker_seen": list}


@contextmanager
def locked():
    """Held while reading-modifying-writing the state: the voice loop's sync and the MCP server both write it."""
    import fcntl
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE.with_suffix(".lock"), "w") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def load_state():
    """graded: [{key, ts, source, reported, ticked, score?}]; announced: assignment keys already said;
    synced: {key: due iso} written to the calendar; seen_msgs: Gmail ids already looked at.
    tracker_events: what happened since the last tracker pass (grade / new / due, academic_sync);
    tracker_offers: tracker writes waiting for his yes; tracker_seen: Gmail ids the course-mail scan has read."""
    try:
        st = json.loads(STATE_FILE.read_text())
    except (OSError, ValueError):
        st = {}
    for k, t in STATE_KEYS.items():
        if not isinstance(st.get(k), t):
            st[k] = t()
    return st


def save_state(st):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, ensure_ascii=False, indent=1, default=str))
    tmp.replace(STATE_FILE)


def known(st=None):
    """Assignments saved by the last feed sync, due times back as datetimes."""
    st = st or load_state()
    return [dict(a, due=datetime.fromisoformat(a["due"])) for a in st.get("assignments", {}).values()]


def queue_announcement(text):
    with locked():
        st = load_state()
        st["announce"].append({"text": text, "ts": time.time()})
        save_state(st)


def pop_announcements():
    """Lines for the voice loop to say (it only runs while docked, so they wait until then)."""
    if not STATE_FILE.exists():
        return []
    with locked():
        st = load_state()
        lines, st["announce"] = [a["text"] for a in st.get("announce", [])], []
        if lines:
            save_state(st)
    return lines


def upcoming(assignments, days=14, now=None):
    now = now or datetime.now()
    return sorted((a for a in assignments if now <= a["due"] <= now + timedelta(days=days)), key=lambda a: a["due"])
