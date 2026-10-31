"""The fake Sheets service the tracker and calendar tests share: one tab of cells with the handful
of Sheets calls tracker.py makes, and the sample tracker rows."""
import re
from datetime import date, timedelta

import tracker as T

TODAY = date.today()


def serial(d):
    return (d - date(1899, 12, 30)).days


# ── a fake Sheets service ──
class Req:
    def __init__(self, fn):
        self.fn = fn

    def execute(self, **kw):
        return self.fn()


class FakeSheet:
    """One tab of cells (row lists), with the handful of Sheets calls tracker.py makes."""

    def __init__(self, grid, formulas=None):
        self.grid = [list(r) for r in grid]
        self.formulas = dict(formulas or {})      # (row, col) 1-based → "=…"
        self.calls = []

    # A1 helpers
    @staticmethod
    def a1(ref):
        m = re.fullmatch(r"([A-Z]+)(\d+)", ref)
        col = 0
        for ch in m.group(1):
            col = col * 26 + ord(ch) - 64
        return int(m.group(2)), col

    def _range(self, rng):
        assert rng.startswith(f"'{T.TAB}'!"), rng
        part = rng.split("!", 1)[1]
        a, _, b = part.partition(":")
        return self.a1(a), self.a1(b or a)

    def cell(self, r, c, formula=False):
        if formula and (r, c) in self.formulas:
            return self.formulas[(r, c)]
        row = self.grid[r - 1] if r - 1 < len(self.grid) else []
        return row[c - 1] if c - 1 < len(row) else ""

    def set(self, r, c, v):
        while len(self.grid) < r:
            self.grid.append([])
        row = self.grid[r - 1]
        while len(row) < c:
            row.append("")
        row[c - 1] = v
        self.formulas.pop((r, c), None)

    # the API surface
    def spreadsheets(self):
        return self

    def values(self):
        return self

    def get(self, spreadsheetId, range=None, fields=None, valueRenderOption=None, dateTimeRenderOption=None):
        assert spreadsheetId == "SHEET"
        if fields:                                   # spreadsheets.get (metadata)
            return Req(lambda: {"sheets": [{"properties": {"sheetId": 7, "title": T.TAB}}]})
        (r1, c1), (r2, c2) = self._range(range)
        r2 = min(r2, len(self.grid))

        def go():
            rows = [[self.cell(r, c, valueRenderOption == "FORMULA") for c in __import__("builtins").range(c1, c2 + 1)]
                    for r in __import__("builtins").range(r1, r2 + 1)]
            while rows and not any(x != "" for x in rows[-1]):
                rows.pop()
            return {"values": [self._trim(x) for x in rows]}
        return Req(go)

    @staticmethod
    def _trim(row):
        row = list(row)
        while row and row[-1] == "":
            row.pop()
        return row

    def update(self, spreadsheetId, range, valueInputOption, body):
        assert valueInputOption == "RAW"
        (r, c), _ = self._range(range)
        self.calls.append(("update", range, body["values"][0][0]))
        return Req(lambda: [self.set(r, c + i, v) for i, v in enumerate(body["values"][0])] and {})

    def batchUpdate(self, spreadsheetId, body):
        def go():
            if "data" in body:
                assert body["valueInputOption"] == "RAW"
                for d in body["data"]:
                    (r, c), _ = self._range(d["range"])
                    self.set(r, c, d["values"][0][0])
                self.calls.append(("values", len(body["data"])))
                return {}
            for q in body["requests"]:
                if "insertDimension" in q:
                    rg = q["insertDimension"]["range"]
                    self.grid.insert(rg["startIndex"], [])
                    self.formulas = {(r + (r > rg["startIndex"]), c): f for (r, c), f in self.formulas.items()}
                    self.calls.append(("insert", rg["startIndex"] + 1, q["insertDimension"]["inheritFromBefore"]))
                elif "deleteDimension" in q:
                    rg = q["deleteDimension"]["range"]
                    del self.grid[rg["startIndex"]]
                    gone = rg["startIndex"] + 1
                    self.formulas = {(r - (r > gone), c): f for (r, c), f in self.formulas.items() if r != gone}
                    self.calls.append(("delete", rg["startIndex"] + 1))
                else:
                    raise AssertionError(f"unexpected request {q}")
            return {}
        return Req(go)


HEAD = [["Pending Assignments:", "", "Completed Assignments:", "", "", "Percentage Completed:"],
        ["", "", "", "", "", ""],
        ["Course", "Assignment", "Due Date", "Days", "Difficulty", "Type", "Status", "Grade"]]


def sheet():
    d = TODAY
    rows = [
        ["MATH 135", "Weekly assessment W5 (quiz)", serial(d - timedelta(days=10)), "", "", "Assignment", "Complete", 90],
        ["CS 137", "Assignment A4 - Arrays and pointers", serial(d - timedelta(days=3)), "", "", "Assignment", "In Progress"],
        ["CS 137", "Assignment A5 - Structures and strings", serial(d + timedelta(days=2)), "", "", "Assignment", "Not Started"],
        ["MATH 135", "Weekly assessment W6 (quiz)", serial(d + timedelta(days=4)), "", "", "Assignment", "Not Started"],
        ["CHE 102", "Assignment 3 (Mobius)", serial(d + timedelta(days=6)), "", "", "Assignment", "Not Started"],
        ["MATH 115", "Python assignment 4", "", "", "", "Assignment", "Not Started"],
    ]
    return FakeSheet(HEAD + rows, formulas={(2, 1): '=COUNTIFS(G4:G1004, "<>Complete")', (8, 4): "=C8-TODAY()"})
