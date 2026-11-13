"""
His SE academic tracker (a Google Sheet) as Orrin's live record of assignments.

The sheet ("SE Academic Tracker - Trevor"; id in the keyring, orrin:google / tracker_sheet, set by
`orrin tracker find`) has three tabs. Only "Assignment Tracker" is ever written:

  row 3     Course | Assignment | Due Date | Days | Difficulty | Type | Status | Grade
  row 4…    one row per deliverable, sorted by due date (undated rows last)

Grades Tracker and Weights are formulas over that tab, so a grade goes in its Grade column and
nowhere else. Rules every write keeps (Tracker.apply is the only code that writes):

  * plain values only (valueInputOption RAW, so text is never parsed as a formula; dates as serial
    numbers so the cell keeps its own format), only into data rows, only WRITABLE columns;
  * the target cell is read first with formulas shown, and a formula is never overwritten;
  * the row is re-read just before the write and must still be the same course + assignment;
  * a new row is inserted at its due-date position with inheritFromBefore (formatting, validation
    and conditional formats come with it); a row is removed only when he asked for that row (and
    never one holding a formula); nothing else structural, never Apps Script;
  * every write is logged in orrin_db.tracker_log; `orrin tracker undo` reverts the last batch;
  * with calendar=True (callers that have his yes) the row's own calendar event follows the change
    (sheet_calendar.py): his sheet's Apps Script only syncs on edits made in the Sheets UI.

The Sheets client itself can only reach this one spreadsheet (google_api.SheetGuard).

CLI (orrin tracker …): find [ID] | show | pending [DAYS] | diff | log [N] | undo (also reverts the calendar
writes that followed that batch)
"""
import re
import uuid
from datetime import date, datetime, timedelta

TAB = "Assignment Tracker"
FIELDS = {"course": "course", "title": "assignment", "due": "due date", "days": "days",
          "difficulty": "difficulty", "type": "type", "status": "status", "grade": "grade"}
WRITABLE = ("course", "title", "due", "type", "status", "grade")
STATUSES = ("Not Started", "In Progress", "Complete", "-")
TYPES = ("Assignment", "Assessment", "Bonus")
DONE = ("Complete", "-")
EPOCH = date(1899, 12, 30)              # Sheets' day 0
NAME_HINT = "academic tracker"

COURSE = re.compile(r"\b([A-Za-z]{2,5})\s?(\d{3}[A-Za-z]?)\b")
# LEARN feed items worth a row: deliverables, not "8_Structures - Available" / "Read the Course Outline"
DELIVERABLE = re.compile(r"\b(?:assignment|assignments|assessment|quiz|lab|tutorial|project|report|deliverable|"
                         r"submission|homework|hw|problem set|midterm|exam|test|presentation|essay|milestone)\b"
                         r"|(?:^|[\s_])a\d+\b|\bw\d+\b", re.I)
NOT_DELIVERABLE = re.compile(r"\b(?:available|provided code|read the|download|log in|holiday|lectures?|examinations|"
                             r"grades begin|official grades|course drop|schedule|open hours|solutions?)\b", re.I)


class TrackerError(Exception):
    def __init__(self, say, detail=""):
        super().__init__(detail or say)
        self.say, self.detail = say, detail or say


# ── names ──────────────────────────────────────
def course_name(text):
    """'cs137' / 'CS 137' / 'Cs137_a5' → 'CS 137' (or '' if there's no course code)."""
    m = COURSE.search(text or "")
    return f"{m.group(1).upper()} {m.group(2).upper()}" if m else ""


IDENT_RULES = [
    ("bq", r"\bbonus quiz\s*#?(\d+)"),
    ("tut", r"\btutorial(?: assignment)?\s*#?(\d+)"),
    ("py", r"\bpython assignment\s*#?(\d+)"),
    ("w", r"\b(?:weekly assessment|assignment|assessment)?\s*w(\d+)\b"),
    ("lab", r"\blab\s*#?(\d+)"),
    ("quiz", r"\bquiz\s*#?(\d+)"),
    ("rs", r"\breview session\s*#?(\d+)"),
    ("a", r"\b(?:assignment|assn|asst)\s*#?\s*a?(\d+)\b"),
    ("a", r"\ba(\d+)\b"),
]


def ident(title):
    """The kind + number an assignment is known by: 'Assignment A5 - Structures' / 'CS137_a5' / 'A5' → 'a5';
    'Weekly assessment W3 (Crowdmark)' / 'Complete Assignment W3' → 'w3'; 'Tutorial 4 - …' → 'tut4';
    'Midterm' → 'midterm'. None if it has neither."""
    t = COURSE.sub(" ", (title or "").lower(), count=1)
    t = re.sub(r"[_\-–:()#,]+", " ", t)
    for kind, rx in IDENT_RULES:
        m = re.search(rx, t)
        if m:
            return f"{kind}{int(m.group(1))}"
    if re.search(r"\bmidterm\b", t):
        return "midterm"
    if re.search(r"\bfinal(?: exam)?\b", t):
        return "final"
    return None


def words(title):
    t = COURSE.sub(" ", (title or "").lower(), count=1)
    return {w for w in re.findall(r"[a-z0-9]+", t) if len(w) > 2 and w not in ("the", "and", "for", "complete", "available")}


def number_of(i):
    m = re.search(r"\d+$", i or "")
    return int(m.group(0)) if m else None


def is_deliverable(title):
    return bool(DELIVERABLE.search(title or "")) and not NOT_DELIVERABLE.search(title or "")


def clean_title(title):
    """A title from the feed / an email / the model, safe as a plain cell value."""
    t = re.sub(r"[\x00-\x1f\x7f]+", " ", str(title or "")).strip()
    t = COURSE.sub("", t, count=1).strip(" -–:_") if course_name(t) and len(t) > 8 else t
    t = re.sub(r"\s+", " ", t).lstrip("=+-@ ")
    return t[:100]


def status_name(s):
    t = (s or "").strip().lower()
    if t in ("done", "complete", "completed", "finished", "submitted", "handed in"):
        return "Complete"
    if t in ("in progress", "started", "working", "working on it", "doing"):
        return "In Progress"
    if t in ("not started", "todo", "to do", "not done", "undone", "incomplete"):
        return "Not Started"
    if t in ("-", "n/a", "na", "skip", "skipped", "not applicable"):
        return "-"
    for st in STATUSES:
        if t == st.lower():
            return st
    return None


# ── dates ──────────────────────────────────────
def to_serial(d):
    return (d - EPOCH).days


def from_serial(v):
    if isinstance(v, (int, float)) and not isinstance(v, bool) and v > 0:
        return EPOCH + timedelta(days=int(v))
    if isinstance(v, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", v.strip()):
        return date.fromisoformat(v.strip())
    return None


def spoken_date(d, today=None):
    today = today or date.today()
    if d == today:
        return "today"
    if d == today + timedelta(days=1):
        return "tomorrow"
    if d == today - timedelta(days=1):
        return "yesterday"
    n = d.day
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return d.strftime(f"%A the {n}{suffix}" if abs((d - today).days) < 7 else f"%A, %B {n}{suffix}")


def col_letter(i):
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


# ── parsing the tab ────────────────────────────
def parse(values):
    """values: the tab's rows (UNFORMATTED / FORMULA render, row 1 first) → (layout, rows).
    layout: {"header": row number, "cols": {field: column index}, "width": n};
    rows: [{"row", "course", "title", "due" (date|None), "status", "grade", "type", "ident"}]."""
    header = cols = None
    for i, r in enumerate(values[:12]):
        names = [str(c).strip().lower() for c in r]
        if "course" in names and "assignment" in names and "status" in names:
            header = i + 1
            cols = {f: names.index(h) for f, h in FIELDS.items() if h in names}
            break
    if not header:
        raise TrackerError("Your tracker's layout has changed, sir: I can't find the Course and Assignment headings.",
                           "no header row with Course / Assignment / Status in the first 12 rows")
    missing = [f for f in WRITABLE if f not in cols]
    if missing:
        raise TrackerError("Your tracker's layout has changed, sir.", f"missing columns: {missing}")
    layout = {"header": header, "cols": cols, "width": max(cols.values()) + 1}
    rows = []
    for i, r in enumerate(values[header:], start=header + 1):
        get = (lambda f: r[cols[f]] if f in cols and cols[f] < len(r) else "")
        course, title = str(get("course")).strip(), str(get("title")).strip()
        if not course and not title:
            continue
        rows.append({"row": i, "course": course, "title": title, "due": from_serial(get("due")),
                     "status": str(get("status")).strip(), "grade": get("grade"), "type": str(get("type")).strip(),
                     "ident": ident(title)})
    return layout, rows


def courses(rows):
    return sorted({r["course"] for r in rows if course_name(r["course"]) == r["course"]})


def find(rows, course, title, strict=True):
    """Rows for course + title. strict: the same ident ("a5", "w3", "tut4") or the same title only.
    Not strict (spoken requests): also a unique row in the course with the same number ("MATH 135 A6"
    → "Weekly assessment W6"), or clearly overlapping words."""
    c = course_name(course) or (course or "").strip().upper()
    same = [r for r in rows if r["course"].upper() == c]
    t = (title or "").strip().lower()
    exact = [r for r in same if r["title"].lower() == t]
    if exact:
        return exact
    i = ident(title)
    if i:
        hits = [r for r in same if r["ident"] == i]
        if hits or strict:
            return hits
        n = number_of(i)
        if n is not None and i not in ("midterm", "final"):
            hits = [r for r in same if number_of(r["ident"]) == n and r["ident"] not in ("midterm", "final")]
            if len(hits) == 1:
                return hits
    if strict:
        return []
    w = words(title)
    scored = sorted(((len(w & words(r["title"])) / max(1, len(w | words(r["title"]))), r) for r in same),
                    key=lambda x: -x[0])
    if scored and scored[0][0] >= 0.5 and (len(scored) == 1 or scored[1][0] < scored[0][0]):
        return [scored[0][1]]
    return []


def insert_at(layout, rows, due):
    """Row number a new row goes in so the tab stays sorted by due date (undated rows stay last)."""
    for r in rows:
        if r["due"] is None or (due is not None and r["due"] > due):
            return r["row"]
    return (rows[-1]["row"] + 1) if rows else layout["header"] + 1


def label(r):
    i = r.get("ident")
    short = i.upper() if i and re.fullmatch(r"[aw]\d+", i) else r["title"]
    return f"{r['course']} {short}"


def describe(r, today=None):
    today = today or date.today()
    d = {"course": r["course"], "assignment": r["title"], "status": r["status"] or "Not Started"}
    if r["due"]:
        d["due"] = spoken_date(r["due"], today)
        d["days_left"] = (r["due"] - today).days
    if r["grade"] not in ("", None):
        d["grade"] = r["grade"]
    return d


def pending(rows, days=7, today=None, overdue_days=14):
    """(due within `days` and not finished, overdue within `overdue_days` and not finished)."""
    today = today or date.today()
    open_ = [r for r in rows if r["status"] not in DONE and r["due"]]
    soon = [r for r in open_ if today <= r["due"] <= today + timedelta(days=days)]
    late = [r for r in open_ if today - timedelta(days=overdue_days) <= r["due"] < today]
    return sorted(soon, key=lambda r: r["due"]), sorted(late, key=lambda r: r["due"])


# ── planned changes (plain dicts, so offers can wait in academic.json) ──
def change_set(r, field, new, why=""):
    return {"kind": "set", "row": r["row"], "field": field, "old": r.get(field), "new": new,
            "expect": {"course": r["course"], "title": r["title"]}, "why": why}


def change_insert(course, title, due, kind="Assignment", status="Not Started", why=""):
    return {"kind": "insert", "values": {"course": course, "title": title, "due": to_serial(due) if due else "",
                                         "type": kind, "status": status}, "why": why}


def row_json(r):
    """A before / after row snapshot that can wait in academic.json (offers)."""
    return None if r is None else dict(r, due=r["due"].isoformat() if r.get("due") else None)


def row_from_json(r):
    return None if r is None else dict(r, due=date.fromisoformat(r["due"]) if r.get("due") else None)


def change_remove(r, why=""):
    return {"kind": "remove", "row": r["row"], "expect": {"course": r["course"], "title": r["title"]}, "why": why}


def plan_update(rows, course, title, status=None, grade=None, due=None, strict=True, why=""):
    """→ (changes, row). Raises TrackerError if the row isn't there (or isn't unique)."""
    hits = find(rows, course, title, strict=strict)
    if not hits:
        raise TrackerError(f"I can't find {course} {title} in your tracker, sir.", "no matching row")
    if len(hits) > 1:
        raise TrackerError(f"{course} {title} matches more than one row in your tracker, sir.",
                           "ambiguous: " + "; ".join(h["title"] for h in hits))
    r = hits[0]
    out = []
    if status and r["status"] != status:
        out.append(change_set(r, "status", status, why))
    if grade is not None and r["grade"] != grade:
        out.append(change_set(r, "grade", grade, why))
    if due is not None and r["due"] != due:
        out.append(change_set(r, "due", to_serial(due), why))
    return out, r


def score_percent(text):
    """A score stated in a grade notice's snippet → percent (one decimal), or None.
    '18/20', '18 / 20', 'scored 18 out of 20', '85%' (only near grade / score / mark words)."""
    t = (text or "").lower()
    if not re.search(r"\b(?:grade|graded|score|scored|mark|marks|result|points?)\b", t):
        return None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:/|out of)\s*(\d+(?:\.\d+)?)", t)
    if m and float(m.group(2)) > 0:
        p = 100 * float(m.group(1)) / float(m.group(2))
    else:
        m = re.search(r"(\d+(?:\.\d+)?)\s*%", t)
        if not m:
            return None
        p = float(m.group(1))
    return round(p, 1) if 0 <= p <= 120 else None


def summary(changes):
    """A short spoken description of planned changes ("mark CS 137 A5 complete and set its grade to 90")."""
    parts = []
    for c in changes:
        if c["kind"] == "remove":
            parts.append(f"remove {c['expect']['course']} {c['expect']['title']}")
            continue
        if c["kind"] == "insert":
            v = c["values"]
            d = from_serial(v["due"]) if v.get("due") != "" else None
            parts.append(f"add {v['course']} {v['title']}" + (f", due {spoken_date(d)}" if d else ""))
            continue
        what = label({"course": c["expect"]["course"], "title": c["expect"]["title"], "ident": ident(c["expect"]["title"])})
        if c["field"] == "status":
            parts.append(f"mark {what} {'complete' if c['new'] == 'Complete' else c['new'].lower()}")
        elif c["field"] == "grade":
            parts.append(f"set {what}'s grade to {c['new']:g}" if isinstance(c["new"], (int, float)) else f"set {what}'s grade")
        elif c["field"] == "due":
            parts.append(f"move {what} to {spoken_date(from_serial(c['new']))}")
        else:
            parts.append(f"change {what}'s {c['field']}")
    return " and ".join(parts)


# ── the sheet ──────────────────────────────────
def configured():
    """Tracker id stored and the Sheets permission granted."""
    import google_api as G
    if not G.tracker_id():
        return False
    g = G.granted()
    return g is None or G.NEEDS["sheets"] in g


class Tracker:
    """One open view of the tracker. load() reads it; apply() is the only write."""

    def __init__(self, svc=None, sheet_id=None, db=None):
        import google_api as G
        self.G = G
        self.sid = sheet_id or G.tracker_id()
        self.svc = svc or G.service("sheets")
        if db is None:
            import orrin_db as db
        self.db = db
        self.layout = self.rows = None
        self.gid = None

    def _call(self, req):
        return self.G.call("sheets", req)

    def _values(self):
        return self.svc.spreadsheets().values()

    def load(self):
        r = self._call(self._values().get(spreadsheetId=self.sid, range=f"'{TAB}'!A1:Z2000",
                                          valueRenderOption="UNFORMATTED_VALUE", dateTimeRenderOption="SERIAL_NUMBER"))
        self.layout, self.rows = parse(r.get("values", []))
        return self.rows

    def _sheet_gid(self):
        if self.gid is None:
            meta = self._call(self.svc.spreadsheets().get(spreadsheetId=self.sid, fields="sheets(properties(sheetId,title))"))
            gids = [s["properties"]["sheetId"] for s in meta.get("sheets", []) if s["properties"]["title"] == TAB]
            if not gids:
                raise TrackerError("Your tracker's Assignment Tracker tab is missing, sir.", f"no tab named {TAB}")
            self.gid = gids[0]
        return self.gid

    def _row_cells(self, row):
        """The row as stored: formulas as formulas, values unformatted."""
        last = col_letter(self.layout["width"] - 1)
        r = self._call(self._values().get(spreadsheetId=self.sid, range=f"'{TAB}'!A{row}:{last}{row}",
                                          valueRenderOption="FORMULA", dateTimeRenderOption="SERIAL_NUMBER"))
        cells = (r.get("values") or [[]])[0]
        return cells + [""] * (self.layout["width"] - len(cells))

    def _check_value(self, field, v):
        if field == "status" and v not in STATUSES:
            raise TrackerError("That isn't one of your tracker's statuses, sir.", f"bad status {v!r}")
        if field == "type" and v not in TYPES:
            raise TrackerError("That isn't one of your tracker's types, sir.", f"bad type {v!r}")
        if field == "grade" and not (isinstance(v, (int, float)) and not isinstance(v, bool) and 0 <= v <= 150):
            raise TrackerError("That doesn't look like a grade, sir.", f"bad grade {v!r}")
        if field == "due" and not (isinstance(v, int) and 40000 < v < 60000):
            raise TrackerError("That doesn't look like a date, sir.", f"bad due {v!r}")
        if field == "course" and v not in courses(self.rows):
            raise TrackerError(f"{v} isn't one of the courses in your tracker, sir.", f"unknown course {v!r}")
        if field == "title" and (not isinstance(v, str) or not v.strip() or v != clean_title(v)):
            raise TrackerError("That assignment name won't do, sir.", f"bad title {v!r}")
        if isinstance(v, str) and v.startswith(("=", "+", "@")):
            raise TrackerError("I won't write a formula into your tracker, sir.", f"formula-like value {v!r}")

    def apply(self, changes, source, calendar=False):
        """See _apply. The HUD's due widget refreshes right after (core/feed.py kick)."""
        try:
            return self._apply(changes, source, calendar)
        finally:
            self.G._kick_feed()

    def _apply(self, changes, source, calendar=False):
        """Make the changes, each re-checked against the sheet as it is now. → [{"ok", "change", ...}].
        A change that doesn't fit any more (row moved and not found again, formula in the cell, value
        not allowed) is skipped with its reason; the others still go through.
        calendar: also bring each touched row's calendar event in line (True: a SheetCalendar of its
        own, logged with this batch as its link; or a SheetCalendar to use). What happened there is
        in self.calendar_report {"did", "notes"}; a calendar failure never undoes the sheet write."""
        if self.rows is None:
            self.load()
        batch = uuid.uuid4().hex[:12]
        self.batch, self.calendar_report = batch, {"did": [], "notes": []}
        touched = {}                                    # (course, title) at the start → [before, after]
        results = []
        for c in changes:
            key = (c["expect"]["course"], c["expect"]["title"]) if "expect" in c else None
            before = self._snapshot(*key) if key else None
            try:
                if c["kind"] == "set":
                    res = self._apply_set(c, batch, source)
                elif c["kind"] == "insert":
                    res = self._apply_insert(c, batch, source)
                elif c["kind"] == "remove":
                    res = self._apply_remove(c, batch, source)
                else:
                    raise TrackerError("Something went wrong on my end, sir.", f"unknown change kind {c['kind']!r}")
                results.append(res)
            except TrackerError as e:
                results.append({"ok": False, "change": c, "error": e.detail, "say": e.say})
                continue
            except self.G.GoogleError as e:
                results.append({"ok": False, "change": c, "error": e.detail, "say": e.say})
                break                                   # offline / permission: the rest would fail the same way
            if res.get("unchanged"):
                continue
            if c["kind"] == "insert":
                v = c["values"]
                key = ("+", v["course"], v["title"])
                touched[key] = [None, self._snapshot(v["course"], v["title"])]
            elif c["kind"] == "remove":
                touched.setdefault(key, [before, None])[1] = None
            elif key in touched or before:
                ex = touched.setdefault(key, [before, None])
                cur = dict(ex[1] or before)
                cur[c["field"]] = from_serial(c["new"]) if c["field"] == "due" else c["new"]
                ex[1] = cur
        self.touched = list(touched.values())
        if calendar and touched:
            self._follow_calendar(calendar, touched, batch)
        return results

    def _snapshot(self, course, title):
        for r in self.rows or []:
            if r["course"] == course and r["title"] == title:
                return {f: r.get(f) for f in ("course", "title", "due", "type", "status")}
        return None

    def _follow_calendar(self, calendar, touched, batch):
        import sheet_calendar
        rep = self.calendar_report
        if self.G.NEEDS["calendar_write"] not in (self.G.granted() or {self.G.NEEDS["calendar_write"]}):
            rep["notes"].append("I couldn't touch its calendar event: Orrin needs calendar access. Run orrin connect google")
            return
        try:
            cal = calendar if not isinstance(calendar, bool) else sheet_calendar.SheetCalendar(self.G.CalendarWriter("tracker", link=batch))
            if getattr(cal.w, "link", None) is None:
                cal.w.link = batch
            for before, after in touched.values():
                r = cal.follow(before, after)
                rep["did"] += r["did"]
                rep["notes"] += r["notes"]
        except self.G.GoogleError as e:
            rep["notes"].append(f"I couldn't update its calendar event: {e.say.rstrip('.')}")
            rep["error"] = e.detail

    def _locate(self, c):
        """The row number holding c["expect"] now (re-read; it may have moved)."""
        row = c["row"]
        cells = self._row_cells(row)
        cols = self.layout["cols"]
        if (str(cells[cols["course"]]).strip() == c["expect"]["course"]
                and str(cells[cols["title"]]).strip() == c["expect"]["title"]):
            return row, cells
        self.load()
        hits = [r for r in self.rows if r["course"] == c["expect"]["course"] and r["title"] == c["expect"]["title"]]
        if len(hits) != 1:
            raise TrackerError(f"{c['expect']['course']} {c['expect']['title']} moved in your tracker, sir, so I left it alone.",
                               f"row {row} no longer holds the expected assignment ({len(hits)} matches now)")
        return hits[0]["row"], self._row_cells(hits[0]["row"])

    def _apply_set(self, c, batch, source):
        field, new = c["field"], c["new"]
        if field not in WRITABLE:
            raise TrackerError("I'm not allowed to change that column, sir.", f"{field} is not writable")
        self._check_value(field, new)
        row, cells = self._locate(c)
        if row <= self.layout["header"]:
            raise TrackerError("I won't touch the tracker's header rows, sir.", f"row {row} is a header row")
        col = self.layout["cols"][field]
        old = cells[col]
        if isinstance(old, str) and old.startswith("="):
            raise TrackerError("That cell has a formula in it, sir, so I left it alone.", f"{col_letter(col)}{row} holds a formula")
        if old == new:
            return {"ok": True, "change": c, "unchanged": True}
        a1 = f"{col_letter(col)}{row}"
        self._call(self._values().update(spreadsheetId=self.sid, range=f"'{TAB}'!{a1}", valueInputOption="RAW",
                                         body={"values": [[new]]}))
        self.db.log_tracker(batch, self.sid, TAB, "set", a1, f"{c['expect']['course']} | {c['expect']['title']}",
                            old, new, source)
        for r in self.rows or []:
            if r["row"] == row:
                r[field] = from_serial(new) if field == "due" else new
        return {"ok": True, "change": c, "cell": a1, "old": old}

    def _apply_insert(self, c, batch, source):
        v = dict(c["values"])
        for f in ("course", "title", "type", "status"):
            if v.get(f) not in ("", None):
                self._check_value(f, v[f])
        if v.get("due") not in ("", None):
            self._check_value("due", v["due"])
        self.load()
        if find(self.rows, v["course"], v["title"], strict=True):
            return {"ok": True, "change": c, "unchanged": True, "exists": True}
        L = self.layout
        due = from_serial(v["due"]) if v.get("due") not in ("", None) else None
        row = insert_at(L, self.rows, due)
        first_data = L["header"] + 1
        self._call(self.svc.spreadsheets().batchUpdate(spreadsheetId=self.sid, body={"requests": [{"insertDimension": {
            "range": {"sheetId": self._sheet_gid(), "dimension": "ROWS", "startIndex": row - 1, "endIndex": row},
            "inheritFromBefore": row > first_data}}]}))
        # only the writable cells; Days / Difficulty and anything else are left to the sheet
        data = [{"range": f"'{TAB}'!{col_letter(L['cols'][f])}{row}", "values": [[v[f]]]}
                for f in WRITABLE if f in v and v[f] not in ("", None)]
        self._call(self._values().batchUpdate(spreadsheetId=self.sid, body={"valueInputOption": "RAW", "data": data}))
        a1 = f"A{row}:{col_letter(L['width'] - 1)}{row}"
        self.db.log_tracker(batch, self.sid, TAB, "insert", a1, f"{v['course']} | {v['title']}", None, v, source)
        self.load()
        return {"ok": True, "change": c, "cell": a1}

    def _apply_remove(self, c, batch, source):
        row, cells = self._locate(c)
        if row <= self.layout["header"]:
            raise TrackerError("I won't touch the tracker's header rows, sir.", f"row {row} is a header row")
        if any(isinstance(v, str) and v.startswith("=") for v in cells):
            raise TrackerError("That row has a formula in it, sir, so I left it alone.", f"row {row} holds a formula")
        self._call(self.svc.spreadsheets().batchUpdate(spreadsheetId=self.sid, body={"requests": [{"deleteDimension": {
            "range": {"sheetId": self._sheet_gid(), "dimension": "ROWS", "startIndex": row - 1, "endIndex": row}}}]}))
        a1 = f"A{row}:{col_letter(self.layout['width'] - 1)}{row}"
        self.db.log_tracker(batch, self.sid, TAB, "remove", a1, f"{c['expect']['course']} | {c['expect']['title']}",
                            cells, None, source)
        self.load()
        return {"ok": True, "change": c, "cell": a1}

    # ── undo ──
    def undo(self):
        """Revert the newest batch that hasn't been undone, if every cell still holds what Orrin wrote.
        → (ok, message)."""
        writes = self.db.last_tracker_batch()
        if not writes:
            return False, "Nothing to undo."
        if writes[0]["sheet"] != self.sid:
            return False, "The last write was to a different spreadsheet; not undoing it."
        self.load()
        plan = []
        for w in writes:                                   # newest first
            if w["kind"] == "set":
                col = re.match(r"[A-Z]+", w["cell"]).group(0)
                row = int(w["cell"][len(col):])
                cells = self._row_cells(row)
                idx = next(i for i in range(self.layout["width"]) if col_letter(i) == col)
                if cells[idx] != w["new"]:
                    return False, f"{w['cell']} has changed since Orrin wrote it ({w['new']!r} → {cells[idx]!r}); not undoing."
                plan.append(("set", w, f"{col}{row}"))
            elif w["kind"] == "remove":
                course, _, title = w["row_key"].partition(" | ")
                if any(r["course"] == course and r["title"] == title for r in self.rows):
                    return False, f"{course} {title} is back in the tracker already; not undoing."
                plan.append(("remove", w, None))
            else:
                v = w["new"]
                hits = [r for r in self.rows if r["course"] == v["course"] and r["title"] == v["title"]]
                if len(hits) != 1:
                    return False, f"The row Orrin added ({v['course']} {v['title']}) isn't where it was; not undoing."
                plan.append(("insert", w, hits[0]["row"]))
        batch = uuid.uuid4().hex[:12]
        done = []
        for kind, w, where in plan:
            if kind == "set":
                old = "" if w["old"] is None else w["old"]
                self._call(self._values().update(spreadsheetId=self.sid, range=f"'{TAB}'!{where}", valueInputOption="RAW",
                                                 body={"values": [[old]]}))
                self.db.log_tracker(batch, self.sid, TAB, "set", where, w["row_key"], w["new"], old, "undo")
                done.append(f"{where}: {w['new']!r} → {old!r}")
            elif kind == "remove":
                self.load()
                L, cells = self.layout, w["old"]
                due = from_serial(cells[L["cols"]["due"]]) if L["cols"]["due"] < len(cells) else None
                row = insert_at(L, self.rows, due)
                self._call(self.svc.spreadsheets().batchUpdate(spreadsheetId=self.sid, body={"requests": [{"insertDimension": {
                    "range": {"sheetId": self._sheet_gid(), "dimension": "ROWS", "startIndex": row - 1, "endIndex": row},
                    "inheritFromBefore": row > L["header"] + 1}}]}))
                last = col_letter(len(cells) - 1)
                self._call(self._values().update(spreadsheetId=self.sid, range=f"'{TAB}'!A{row}:{last}{row}",
                                                 valueInputOption="RAW", body={"values": [cells]}))
                self.db.log_tracker(batch, self.sid, TAB, "insert", f"A{row}:{last}{row}", w["row_key"], None,
                                    dict(zip(("course", "title"), w["row_key"].split(" | ", 1))), "undo")
                done.append(f"put back {w['row_key']} at row {row}")
            else:
                self._call(self.svc.spreadsheets().batchUpdate(spreadsheetId=self.sid, body={"requests": [{"deleteDimension": {
                    "range": {"sheetId": self._sheet_gid(), "dimension": "ROWS", "startIndex": where - 1, "endIndex": where}}}]}))
                self.db.log_tracker(batch, self.sid, TAB, "delete", f"row {where}", w["row_key"], w["new"], None, "undo")
                done.append(f"removed row {where} ({w['row_key']})")
        self.db.mark_tracker_undone(writes[0]["batch"])
        msg = "Undid: " + "; ".join(done)
        if self.db.last_calendar_batch(writes[0]["batch"]):     # the calendar writes that followed it
            try:
                ok, cal = self.G.CalendarWriter("undo").undo(link=writes[0]["batch"])
            except self.G.GoogleError as e:
                ok, cal = False, f"couldn't undo its calendar writes: {e.say}"
            msg += f"\n{cal}" + ("" if ok else " Run `orrin calendar undo` once that's sorted.")
        return True, msg


# ── LEARN feed vs the sheet (read-only report) ──
def reconcile(rows, assignments, today=None):
    """What the sheet is missing or has differently from the LEARN feed, for upcoming deliverables.
    → [{"what": "missing" | "due", "course", "title", "feed_due", "row"?}]. Nothing is changed."""
    today = today or date.today()
    out = []
    for a in assignments:
        due = a["due"].date() if isinstance(a["due"], datetime) else a["due"]
        if due < today - timedelta(days=1) or not is_deliverable(a["title"]):
            continue
        hits = find(rows, a["course"], a["title"], strict=True)
        if not hits:
            out.append({"what": "missing", "course": a["course"], "title": a["title"], "feed_due": due})
        elif len(hits) == 1 and hits[0]["due"] and hits[0]["due"] != due:
            out.append({"what": "due", "course": a["course"], "title": a["title"], "feed_due": due,
                        "row": hits[0]["row"], "sheet_due": hits[0]["due"], "sheet_title": hits[0]["title"]})
    return out


# ── CLI ────────────────────────────────────────
def cli(argv):
    import google_api as G
    from integration_common import secrets
    cmd, rest = (argv[0] if argv else "show"), argv[1:]
    try:
        if cmd == "find":
            if rest:
                sid = rest[0].strip()
                meta = G.call("drive", G.service("drive").files().get(fileId=sid, fields="id,name,mimeType,owners(me)"))
            else:
                found = G.call("drive", G.service("drive").files().list(
                    q=f"name contains '{NAME_HINT}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false",
                    fields="files(id,name,owners(me),modifiedTime)", pageSize=20)).get("files", [])
                mine = [f for f in found if any(o.get("me") for o in f.get("owners", []))]
                for f in found:
                    print(f"  {'*' if f in mine else ' '} {f['name']}  ({f['id']})")
                if len(mine) != 1:
                    print("Found %d of your own sheets matching %r; run `orrin tracker find <ID>`." % (len(mine), NAME_HINT))
                    return 1
                meta = mine[0]
            if meta.get("mimeType", "application/vnd.google-apps.spreadsheet") != "application/vnd.google-apps.spreadsheet":
                print("That file isn't a Google Sheet.")
                return 1
            secrets.store("google", "tracker_sheet", meta["id"])
            print(f"Tracker: {meta['name']} ({meta['id']}) saved in the keyring.")
            missing = G.missing_scopes([G.NEEDS["sheets"]])
            if missing:
                print("Orrin can't open it yet: the Sheets permission is missing. Run `orrin connect google` and tick "
                      "\"See, edit, create and delete your spreadsheets\" (Orrin only ever opens this one).")
            return 0
        if not G.tracker_id():
            print("No tracker set. Run `orrin tracker find`.")
            return 1
        if cmd == "log":
            import orrin_db as db
            for w in reversed(db.tracker_writes(int(rest[0]) if rest else 20)):
                ts = datetime.fromtimestamp(w["ts"]).strftime("%m-%d %H:%M")
                flag = " (undone)" if w["undone"] else ""
                print(f"{ts}  {w['batch']}  {w['source']:<12} {w['kind']:<6} {w['cell']:<8} {w['row_key'][:50]:<50} "
                      f"{w['old']!r} → {w['new']!r}{flag}")
            return 0
        t = Tracker()
        if cmd == "undo":
            ok, msg = t.undo()
            print(msg)
            return 0 if ok else 1
        rows = t.load()
        if cmd == "show":
            by = {}
            for r in rows:
                by[r["status"] or "(blank)"] = by.get(r["status"] or "(blank)", 0) + 1
            cols = ", ".join(f"{f}={col_letter(i)}" for f, i in sorted(t.layout["cols"].items(), key=lambda x: x[1]))
            print(f"{TAB}: header row {t.layout['header']}, {len(rows)} rows ({cols})")
            print("  status: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
            print("  courses: " + ", ".join(courses(rows)))
            print(f"  graded rows: {sum(1 for r in rows if r['grade'] not in ('', None))}")
            return 0
        if cmd == "pending":
            soon, late = pending(rows, int(rest[0]) if rest else 7)
            for r in late:
                print(f"  OVERDUE {r['due']}  {r['course']:<9} {r['title']}  [{r['status']}]")
            for r in soon:
                print(f"  {r['due']}  {r['course']:<9} {r['title']}  [{r['status']}]")
            return 0
        if cmd == "diff":
            import academic
            for d in reconcile(rows, academic.known()):
                if d["what"] == "missing":
                    print(f"  missing  {d['course']:<9} {d['title']}  (LEARN due {d['feed_due']})")
                else:
                    print(f"  due      {d['course']:<9} {d['sheet_title']}  sheet {d['sheet_due']} vs LEARN {d['feed_due']}")
            return 0
    except G.GoogleError as e:
        print(f"{e.say}\n  ({e.kind}: {e.detail})")
        return 1
    except TrackerError as e:
        print(f"{e.say}\n  ({e.detail})")
        return 1
    print("usage: orrin tracker find [ID] | show | pending [DAYS] | diff | log [N] | undo")
    return 2


# ── course email (headers + Gmail's snippet only; the body is never fetched) ──
COURSE_SENDER = re.compile(r"@(?:[\w-]+\.)*(?:uwaterloo\.ca|crowdmark\.com|d2l\.com|desire2learn\.com|piazza\.com)>?$", re.I)
ANNOUNCES_NEW = re.compile(r"\b(?:new|posted|released|now (?:available|open)|is (?:available|open|out)|has been (?:posted|released))\b", re.I)
ANNOUNCES_MOVE = re.compile(r"\b(?:extension|extended|deadline (?:change[ds]?|moved|extended)|due date (?:change[ds]?|updated|moved)|"
                            r"now due|postponed|pushed back|new due date)\b", re.I)
GRADEISH = re.compile(r"\b(?:grade|graded|feedback|marks? (?:released|available)|results?)\b", re.I)
THING = re.compile(r"\b(?:(?:python |tutorial |weekly )?assignment\s*#?\s*[a-z]?\d+|a\d+|w\d+|lab\s*#?\d+|quiz\s*#?\d+|"
                   r"tutorial\s*#?\d+|project(?:\s*#?\d+)?|midterm|final exam)\b", re.I)
MONTHS = {m: i + 1 for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"))}


def mail_date(text, today=None):
    """'due Thursday, Nov 5' / 'November 5th' / '2026-11-05' → date (this year, or next if it's long past)."""
    today = today or date.today()
    t = text or ""
    m = re.search(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})(?:st|nd|rd|th)?\b", t, re.I)
    if not m:
        return None
    try:
        d = date(today.year, MONTHS[m.group(1).lower()], int(m.group(2)))
    except ValueError:
        return None
    return d.replace(year=d.year + 1) if d < today - timedelta(days=60) else d


def mail_event(headers, snippet, known_courses, today=None):
    """One course email → {"type": "new" | "due", "course", "title", "due"?} or None.
    Only from LEARN / Crowdmark / Piazza / UW addresses (DKIM not failed), only for a course already
    in the tracker, only when the subject itself announces a new deliverable or a moved deadline."""
    import academic
    subject = academic.FW_PREFIX.sub("", (headers.get("subject") or [""])[0])
    if academic.dkim_verdict(headers) is False or GRADEISH.search(subject):
        return None
    if not any(COURSE_SENDER.search(s) for s in academic.notice_senders(headers, snippet)):
        return None
    course = course_name(subject)
    if course not in known_courses:
        return None
    rest = COURSE.sub(" ", subject, count=1)
    thing = THING.search(rest)
    if not thing:
        return None
    title = clean_title(re.sub(r"\s+", " ", thing.group(0)).strip())
    title = title[0].upper() + title[1:]
    kind = "due" if ANNOUNCES_MOVE.search(subject) else "new" if ANNOUNCES_NEW.search(subject) else None
    if not kind:
        return None
    due = mail_date(subject, today) or mail_date(snippet, today)
    if kind == "due" and not due:
        return None
    return {"type": kind, "course": course, "title": title, **({"due": due.isoformat()} if due else {})}


def plan_event(rows, ev):
    """An event from the sync → (changes, sure). sure = safe to apply without asking when AUTO-UPDATE is on."""
    if ev["type"] == "grade":
        hits = find(rows, ev["course"], ev["title"], strict=True)
        if len(hits) != 1:
            return [], False
        r = hits[0]
        out = [change_set(r, "status", "Complete", "grade notice")] if r["status"] not in DONE else []
        if ev.get("score") is not None and r["grade"] in ("", None):
            out.append(change_set(r, "grade", ev["score"], "grade notice"))
        return out, True
    due = date.fromisoformat(ev["due"]) if ev.get("due") else None
    hits = find(rows, ev["course"], ev["title"], strict=True)
    if ev["type"] == "new":
        if hits or (ev.get("source") == "learn-feed" and not is_deliverable(ev["title"])):
            return [], False
        loose = find(rows, ev["course"], ev["title"], strict=False)
        title = clean_title(ev["title"])
        kind = "Bonus" if re.search(r"\bbonus\b", title, re.I) else "Assignment"
        return [change_insert(ev["course"], title, due, kind=kind, why=ev.get("source", ""))], \
            bool(due) and not loose and ident(title) is not None
    if ev["type"] == "due":
        if len(hits) != 1 or not due or hits[0]["status"] in DONE:
            return [], False
        r = hits[0]
        if ev.get("from") and r["due"]:
            # the feed moved: move the row by as many days, so his own convention (CHE 102 rows say
            # the day before LEARN's 8 AM deadline) survives
            due = r["due"] + (due - date.fromisoformat(ev["from"]))
        if r["due"] == due:
            return [], False
        return [change_set(r, "due", to_serial(due), ev.get("source", ""))], True
    return [], False
