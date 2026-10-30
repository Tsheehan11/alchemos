"""
The academic sync: LEARN feed → known assignments → his SE tracker sheet (or, without one,
"STARK – Assignments"), and LEARN / Crowdmark grade emails in Gmail → the tracker row's status /
grade (or ✓ on that event) + "Sir, your CS 137 A5 has been graded".

Run by the voice loop every ~15 min while docked (jarvis.py VoiceLoop._sync_loop); the academic
MCP tools call the read halves on demand (refresh_learn, scan_grades).

Rules:
  * With the tracker configured (tracker.configured()), the calendar is left alone: his sheet syncs
    to Google Calendar itself. Tracker events (a grade notice, a new LEARN deliverable or course
    email announcing one, a moved deadline) queue in academic.json; tracker_pass turns them into
    changes and, with Settings → JARVIS → AUTO-UPDATE TRACKER on, applies the sure ones and announces
    them; everything else becomes an offer the voice loop asks about. tracker.Tracker.apply is the
    only writer.
  * Calendar writes only with Settings → JARVIS → AUTO-ADD ASSIGNMENTS on, only for assignments
    still to come, and only to the app's own calendar (google_api.AssignmentsCalendar). With it
    off, nothing is written; calendar_add_assignment (with his spoken yes) is the way in.
  * Grades are recognised by academic.notice_from_message (headers + snippet only, known
    assignments only). Each assignment is announced at most once, and only for notices from the
    last ANNOUNCE_WITHIN_S; the very first scan records what's already there without a word.
  * Nothing here involves the model: email content can't steer it.
"""
import time
import urllib.request
from datetime import datetime, timedelta

import academic as A

LEARN_REFRESH_S = 15 * 60
GRADE_LOOKBACK_DAYS = 21
ANNOUNCE_WITHIN_S = 2 * 86400
REPORT_WITHIN_S = 14 * 86400
GRADE_QUERY = (f"newer_than:{GRADE_LOOKBACK_DAYS}d (from:crowdmark.com OR from:learn.uwaterloo.ca OR from:d2l.com "
               "OR from:desire2learn.com OR from:uwaterloo.ca OR from:piazza.com "
               "OR subject:(grade OR graded OR feedback OR returned OR results OR extension OR extended OR deadline))")
TRACKER_EVENT_MAX_AGE_S = 14 * 86400      # a grade notice older than this doesn't touch the tracker
NOTICE_HEADERS = ["From", "Sender", "Reply-To", "Return-Path", "X-Original-From", "X-Original-Sender", "Resent-From",
                  "Subject", "Authentication-Results", "ARC-Authentication-Results"]


def _secrets():
    from integration_common import secrets
    return secrets


def _tracker_on():
    import tracker
    return tracker.configured()


# ── LEARN feed ──
def refresh_learn(force=False):
    """Fetch the feed if it's older than LEARN_REFRESH_S → {"new": [...keys], "changed": [...], "total"}.
    Raises on network / feed errors (callers decide what to say)."""
    st = A.load_state()
    if not force and time.time() - st.get("feed_fetched", 0) < LEARN_REFRESH_S:
        return {"new": [], "changed": [], "total": len(st["assignments"]), "fresh": True}
    link = _secrets().get("learn", "ical_url")
    if not link:
        raise RuntimeError("LEARN isn't connected")
    req = urllib.request.Request(link, headers={"User-Agent": "stark-jarvis/2"})
    with urllib.request.urlopen(req, timeout=20) as r:
        items = A.dedupe(A.parse_ical(r.read(5_000_000).decode("utf-8", "replace")))
    with A.locked():
        st = A.load_state()
        old = st["assignments"]
        new = {a["key"]: dict(a, due=a["due"].isoformat()) for a in items}
        report = {"new": [k for k in new if k not in old],
                  "changed": [k for k in new if k in old and old[k]["due"] != new[k]["due"]], "total": len(new)}
        if old and _tracker_on():          # the first fetch ever is the baseline, not news
            for k in report["new"]:
                a = new[k]
                st["tracker_events"].append({"type": "new", "course": a["course"], "title": a["title"],
                                             "due": a["due"][:10], "source": "learn-feed", "ts": time.time()})
            for k in report["changed"]:
                a = new[k]
                st["tracker_events"].append({"type": "due", "course": a["course"], "title": a["title"],
                                             "due": a["due"][:10], "from": old[k]["due"][:10],
                                             "source": "learn-feed", "ts": time.time()})
        st["assignments"], st["feed_fetched"] = new, time.time()
        A.save_state(st)
    return report


# ── grade notices ──
def gmail_notices():
    """Candidate grade emails from the last GRADE_LOOKBACK_DAYS: [(id, headers {lower: [values]}, snippet, ts)]."""
    import google_api as G
    svc = G.service("gmail")
    ids = G.call("gmail", svc.users().messages().list(userId="me", q=GRADE_QUERY, maxResults=50,
                                                      fields="messages(id)")).get("messages", [])
    got = {}
    batch = svc.new_batch_http_request(callback=lambda rid, resp, exc: got.__setitem__(rid, resp) if exc is None else None)
    for m in ids:
        batch.add(svc.users().messages().get(userId="me", id=m["id"], format="metadata", metadataHeaders=NOTICE_HEADERS,
                                             fields="id,snippet,internalDate,payload/headers"), request_id=m["id"])
    if ids:
        G.call("gmail", batch)
    out = []
    for m in ids:
        r = got.get(m["id"])
        if not r:
            continue
        h = {}
        for x in r.get("payload", {}).get("headers", []):
            h.setdefault(x["name"].lower(), []).append(x["value"])
        out.append((m["id"], h, r.get("snippet", ""), int(r.get("internalDate", "0")) / 1000))
    return out


def scan_grades(messages, now=None, announce=True):
    """Record grade notices among `messages` (see gmail_notices) in the state. Returns the new
    graded entries. Queues one announcement per assignment, for recent notices, except on the
    first scan ever (which only records what's already in the inbox)."""
    now = now or time.time()
    with A.locked():
        st = A.load_state()
        first = "grades_since" not in st
        known = A.known(st)
        seen = set(st["seen_msgs"])
        graded_keys = {g["key"] for g in st["graded"]}
        new = []
        for mid, headers, snippet, ts in messages:
            if mid in seen:
                continue
            seen.add(mid)
            hit = A.notice_from_message(headers, snippet, known)
            if not hit:
                continue
            a, source = hit
            k = A.key(a["course"], a["title"])
            if k in graded_keys:
                continue
            graded_keys.add(k)
            import tracker
            score = tracker.score_percent(snippet)
            entry = {"key": k, "ts": ts, "source": source, "reported": False, "ticked": False,
                     **({"score": score} if score is not None else {})}
            st["graded"].append(entry)
            new.append(entry)
            if not first and _tracker_on() and now - ts <= TRACKER_EVENT_MAX_AGE_S:
                st["tracker_events"].append({"type": "grade", "course": a["course"], "title": a["title"], "score": score,
                                             "source": "grade-notice", "ts": now})
            if announce and not first and k not in st["announced"] and now - ts <= ANNOUNCE_WITHIN_S:
                st["announce"].append({"text": A.announcement(a), "ts": now})
                st["announced"].append(k)
            elif first:
                st["announced"].append(k)                 # old news: never announce it later either
        st["seen_msgs"] = list(seen)[-2000:]
        st.setdefault("grades_since", now)
        A.save_state(st)
    return new


def scan_course_mail(messages, known_courses, now=None):
    """Course emails announcing a new deliverable or a moved deadline → tracker events (subject +
    snippet only). The first scan only records what's already there."""
    import tracker
    now = now or time.time()
    with A.locked():
        st = A.load_state()
        first = "tracker_mail_since" not in st
        seen = set(st["tracker_seen"])
        found = []
        for mid, headers, snippet, ts in messages:
            if mid in seen:
                continue
            seen.add(mid)
            if first or now - ts > TRACKER_EVENT_MAX_AGE_S:
                continue
            ev = tracker.mail_event(headers, snippet, known_courses)
            if ev:
                ev.update(source="course-email", ts=now)
                st["tracker_events"].append(ev)
                found.append(ev)
        st["tracker_seen"] = list(seen)[-2000:]
        st.setdefault("tracker_mail_since", now)
        A.save_state(st)
    return found


# ── the tracker sheet ──
OFFER_TTL_S = 3 * 86400


def tracker_pass(cfg, messages=None, log=print, sheet=None):
    """Drain tracker_events → changes. AUTO-UPDATE on: apply the sure ones now and queue an
    announcement; the rest (or everything, with it off) become offers. Returns a small report."""
    import tracker
    if sheet is None and not tracker.configured():
        return {"skipped": "no tracker"}
    t = sheet or tracker.Tracker()
    rows = t.load()
    if messages:
        scan_course_mail(messages, tracker.courses(rows))
    with A.locked():
        st = A.load_state()
        events, st["tracker_events"] = st["tracker_events"], []
        A.save_state(st)
    if not events:
        return {}
    auto = bool(cfg["jarvisAutoUpdateTracker"])
    applied, offers, said = [], [], []
    try:
        for ev in events:
            changes, sure = tracker.plan_event(t.rows, ev)
            if not changes:
                continue
            what = tracker.summary(changes)
            if auto and sure:
                res = t.apply(changes, ev.get("source", "sync"))
                ok = [r for r in res if r["ok"] and not r.get("unchanged")]
                bad = [r for r in res if not r["ok"]]
                if ok:
                    applied.append(what)
                    said.append(f"I've updated your tracker, sir: {tracker.summary([r['change'] for r in ok])}.")
                for r in bad:
                    log(f"JARVIS: tracker: {r['error']}")
            else:
                offers.append({"changes": changes, "source": ev.get("source", "sync"), "ts": time.time(),
                               "prompt": f"Shall I {what} in your tracker, sir?"})
    except Exception:
        with A.locked():                      # offline mid-way: try these again next pass
            st = A.load_state()
            st["tracker_events"] = events + st["tracker_events"]
            A.save_state(st)
        raise
    with A.locked():
        st = A.load_state()
        st["tracker_offers"] = [o for o in st["tracker_offers"] if time.time() - o["ts"] < OFFER_TTL_S] + offers
        st["announce"] += [{"text": s, "ts": time.time()} for s in said]
        A.save_state(st)
    return {"applied": applied, "offered": len(offers)} if applied or offers else {}


def pop_tracker_offer():
    """The oldest offer still worth asking about, removed from the queue (None if there's none)."""
    if not A.STATE_FILE.exists():
        return None
    with A.locked():
        st = A.load_state()
        live = [o for o in st["tracker_offers"] if time.time() - o["ts"] < OFFER_TTL_S]
        offer = live.pop(0) if live else None
        if offer or len(live) != len(st["tracker_offers"]):
            st["tracker_offers"] = live
            A.save_state(st)
    return offer


# ── calendar ──
def write_calendar(cfg, now=None, calendar=None):
    """AUTO-ADD on → upsert new / changed upcoming assignments, then ✓ graded ones. Returns counts.
    Not with the tracker configured: his sheet syncs to Google Calendar itself."""
    import tracker
    if tracker.configured():
        return {"skipped": "the tracker sheet syncs to the calendar"}
    if not cfg["jarvisAutoAddAssignments"]:
        return {"skipped": "AUTO-ADD is off"}
    if cfg["jarvisAssignmentsAccount"] == "microsoft":
        return {"skipped": "Outlook calendar writes aren't available (no Graph access)"}
    if not _secrets().has("google", "token"):
        return {"skipped": "Google isn't connected"}
    import google_api as G
    cal = calendar or G.AssignmentsCalendar(A.ASSIGNMENTS_CALENDAR)
    now_dt = datetime.fromtimestamp(now or time.time())
    st = A.load_state()
    todo = [a for a in A.known(st) if a["due"] >= now_dt - timedelta(hours=12)
            and st["synced"].get(a["key"]) != a["due"].isoformat()]
    done, ticks = {}, []
    for a in todo:
        what, _ = cal.upsert(A.event_for(a))
        done[a["key"]] = (what, a["due"].isoformat())
    synced_now = set(st["synced"]) | set(done)
    for g in st["graded"]:
        if not g.get("ticked") and g["key"] in synced_now and cal.mark_graded(g["key"], A.graded_summary):
            ticks.append(g["key"])
    with A.locked():
        st = A.load_state()
        for k, (_, due) in done.items():
            st["synced"][k] = due
        for g in st["graded"]:
            if g["key"] in ticks:
                g["ticked"] = True
        A.save_state(st)
    return {"created": sum(1 for w, _ in done.values() if w == "created"),
            "updated": sum(1 for w, _ in done.values() if w == "updated"), "ticked": len(ticks)}


def sync(cfg, log=print, dry_run=False):
    """One pass: feed, grades, calendar. dry_run: read only (no calendar writes, no announcements)."""
    report = {}
    try:
        report["learn"] = refresh_learn()
    except Exception as e:
        report["learn_error"] = f"{type(e).__name__}: {e}"[:200]
    messages = None
    if _secrets().has("google", "token"):
        try:
            messages = gmail_notices()
            report["grades"] = [g["key"] for g in scan_grades(messages, announce=not dry_run)] if not dry_run \
                else len(messages)
        except Exception as e:
            report["grades_error"] = f"{type(e).__name__}: {e}"[:200]
    if not dry_run:
        try:
            report["tracker"] = tracker_pass(cfg, messages, log=log)
        except Exception as e:
            report["tracker_error"] = f"{type(e).__name__}: {e}"[:200]
        try:
            report["calendar"] = write_calendar(cfg)
        except Exception as e:
            report["calendar_error"] = f"{type(e).__name__}: {e}"[:200]
    return report
