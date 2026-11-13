#!/usr/bin/env python3
"""Live check of the SE tracker against Google (prints shapes and counts, not his data).

  tools/tracker_live_test.py read           reads the real tracker (no writes possible: read calls only)
  tools/tracker_live_test.py write COPY_ID  writes to a COPY of the tracker: the Sheets guard is pointed
                                            at COPY_ID for this process, and the write log goes to a
                                            throwaway database. Make the copy first (Drive → Make a copy)
                                            and delete it afterwards.
"""
import os
import sys
import tempfile
from datetime import date, timedelta

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path[:0] = [os.path.join(ROOT, "mcp")]
sys.path.append(ROOT)
os.environ.setdefault("ORRIN_DB", os.path.join(tempfile.mkdtemp(), "orrin.db"))   # write mode only uses this one
import academic  # noqa: E402
import google_api as G  # noqa: E402
import tracker as T  # noqa: E402

FAILS = []


def check(name, ok, detail=""):
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  ' + str(detail) if detail else ''}")
    if not ok:
        FAILS.append(name)


def read():
    t = T.Tracker()
    rows = t.load()
    check("layout found", t.layout["header"] == 3, t.layout)
    check("rows", len(rows) > 50, len(rows))
    check("every row has a course and title", all(r["course"] and r["title"] for r in rows))
    check("dates parsed", sum(1 for r in rows if r["due"]) > 50, sum(1 for r in rows if r["due"]))
    soon, late = T.pending(rows, 7)
    check("pending this week computed", True, f"{len(soon)} due, {len(late)} overdue")
    check("CS 137 A5 found", len(T.find(rows, "CS 137", "A5", strict=False)) == 1)
    check("MATH 135 A6 → W6", [r["ident"] for r in T.find(rows, "MATH 135", "A6", strict=False)] == ["w6"])
    check("reconcile vs LEARN", True, f"{len(T.reconcile(rows, academic.known()))} differences (read-only report)")
    try:                                                 # the guard: any other spreadsheet is refused before a request is made
        G.call("sheets", G.service("sheets").spreadsheets().get(spreadsheetId="1ALAOVaWhIsjHLAVkMaDvlxFj4m_ScTsfMno77bncn-8"))
        check("guard blocks another spreadsheet", False)
    except G.GoogleError as e:
        check("guard blocks another spreadsheet", e.kind == "forbidden", e.kind)


def write(copy_id):
    real = G.tracker_id()
    check("copy is not the real tracker", copy_id != real)
    if copy_id == real:
        return
    G.tracker_id = lambda: copy_id                       # this process only: the guard now allows the copy and nothing else
    svc = G.service("sheets")
    try:
        G.call("sheets", svc.spreadsheets().get(spreadsheetId=real, fields="spreadsheetId"))
        check("guard blocks the real tracker while testing", False)
    except G.GoogleError as e:
        check("guard blocks the real tracker while testing", e.kind == "forbidden")
    t = T.Tracker(svc=svc, sheet_id=copy_id)
    rows = t.load()
    target = dict(next(r for r in rows if r["status"] == "Not Started" and r["due"] and r["due"] >= date.today()))
    changes, _ = T.plan_update(rows, target["course"], target["title"], status="In Progress", grade=77.0)
    res = t.apply(changes, "live-test")
    check("set status + grade", all(r["ok"] for r in res), [r.get("cell") for r in res])
    t.load()
    after = next(r for r in t.rows if r["row"] == target["row"])
    check("values read back", (after["status"], after["grade"]) == ("In Progress", 77.0), (after["status"], after["grade"]))
    # a formula cell is refused (row 2's COUNTIFS sits above the header, so use the header's own check too)
    fake = T.change_set({"row": 2, "course": "", "title": ""}, "status", "Complete")
    check("summary row refused", not t.apply([fake], "live-test")[0]["ok"])
    # insert between two dated rows, then check it inherited the row above's look and validation
    due = target["due"] + timedelta(days=1)
    res = t.apply([T.change_insert(target["course"], "Orrin live test row", due)], "live-test")
    check("insert", res[0]["ok"], res[0].get("cell") or res[0].get("error"))
    row = int(res[0]["cell"].split(":")[0][1:])
    grid = G.call("sheets", svc.spreadsheets().get(
        spreadsheetId=copy_id, ranges=[f"'{T.TAB}'!A{row - 1}:H{row}"], includeGridData=True,
        fields="sheets(data(rowData(values(effectiveFormat(backgroundColor,textFormat(fontFamily,fontSize)),dataValidation(condition(type))))))"))
    data = grid["sheets"][0]["data"][0]["rowData"]
    above, new = data[0]["values"], data[1]["values"]
    check("validation inherited (Course / Type / Status)",
          all(new[i].get("dataValidation", {}).get("condition", {}).get("type") ==
              above[i].get("dataValidation", {}).get("condition", {}).get("type") for i in (0, 5, 6)))
    check("font inherited", new[1].get("effectiveFormat", {}).get("textFormat") == above[1].get("effectiveFormat", {}).get("textFormat"))
    t.load()
    dues = [r["due"] for r in t.rows if r["due"]]
    check("still sorted by due date", dues == sorted(dues))
    ok, msg = t.undo()
    check("undo insert", ok and not T.find(t.load(), target["course"], "Orrin live test row"), msg)
    ok, msg = t.undo()
    t.load()
    back = next(r for r in t.rows if r["row"] == target["row"])
    check("undo set", ok and back["status"] == target["status"] and back["grade"] == target["grade"], msg)


if __name__ == "__main__":
    if sys.argv[1:2] == ["read"]:
        read()
    elif sys.argv[1:2] == ["write"] and len(sys.argv) == 3:
        write(sys.argv[2])
    else:
        print(__doc__)
        sys.exit(2)
    print("\n" + ("FAILED: " + ", ".join(FAILS) if FAILS else "all live checks passed"))
    sys.exit(1 if FAILS else 0)
