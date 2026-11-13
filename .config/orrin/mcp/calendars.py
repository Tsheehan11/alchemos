"""
His calendars merged: Google (every calendar in his list, google_api) + Outlook (the published
ICS link, outlook_ical), in local time. An event that exists in both (an Outlook invite he also
accepted in Google, or the Outlook feed subscribed in Google) is kept once: same iCal UID, or
the same title at the same start and end. Each event keeps "sources" so Orrin can say where
it came from, but only when asked.
"""
import re

import google_api as G
import outlook_ical as O
from integration_common import secrets


def _norm(title):
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def dedupe(events):
    out, by_uid, by_slot = [], {}, {}
    for e in sorted(events, key=lambda e: e.get("source", "").startswith("Outlook")):   # Google copy wins
        uid = e.get("uid") or ""
        slot = (_norm(e["title"]), e["all_day"], e["start"].replace(second=0, microsecond=0),
                e["end"].replace(second=0, microsecond=0))
        twin = by_uid.get(uid) if uid else None
        twin = twin or by_slot.get(slot)
        if twin is not None:
            src = e.get("source", "")
            if src and src not in twin["sources"]:
                twin["sources"].append(src)
            continue
        e = dict(e, sources=[e["source"]] if e.get("source") else [])
        out.append(e)
        if uid:
            by_uid[uid] = e
        by_slot[slot] = e
    return sorted(out, key=lambda e: (not e["all_day"], e["start"]))


def merged(start, end, per_calendar=50):
    """→ (events, notes). notes: spoken-ready lines about a source that failed while another worked.
    Raises GoogleError / FeedError only when no source gave anything."""
    evs, notes, errors = [], [], []
    have_google, have_outlook = secrets.has("google", "token"), bool(O.url())
    if not have_google and not have_outlook:
        raise G.GoogleError("not_connected", "Your calendar isn't connected yet, sir. You can connect it in Settings, under Orrin.")
    if have_google:
        try:
            evs += G.events(start, end, per_calendar)
        except G.GoogleError as e:
            errors.append(e)
            notes.append(e.say)
    if have_outlook:
        try:
            m = O.fetch()
            evs += O.events(start, end, start.tzinfo)
            if not m.get("ok"):
                notes.append("Your Outlook calendar link isn't updating, sir, so Outlook events may be out of date.")
        except O.FeedError as e:
            errors.append(G.GoogleError("http", "I couldn't read your Outlook calendar link, sir.", f"outlook feed: {e}"))
            notes.append("I couldn't read your Outlook calendar link, sir.")
    if errors and len(errors) == int(have_google) + int(have_outlook):
        raise errors[0]
    return dedupe(evs), notes
