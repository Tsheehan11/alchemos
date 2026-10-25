#!/usr/bin/env python3
"""30 tricky lines through speech.normalize (+ sentence splitting). Run: python tests/test_speech.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from core.speech import normalize, sentences  # noqa: E402

CASES = [
    ("It's 16:07, sir.", "It's four oh seven PM, sir."),
    ("It's 4:07 PM.", "It's four oh seven PM."),
    ("It's 4:00.", "It's four o'clock."),
    ("Lunch is at 12:00.", "Lunch is at noon."),
    ("The backup runs at 00:00.", "The backup runs at midnight."),
    ("It's 4:31 in the afternoon, sir.", "It's four thirty-one in the afternoon, sir."),
    ("Due at 16:39.", "Due at four thirty-nine PM."),
    ("Resetting Tuesday at 2 PM.", "Resetting Tuesday at two PM."),
    ("Meeting at 9am tomorrow.", "Meeting at nine AM tomorrow."),
    ("It's Sunday, the 25 of October.", "It's Sunday, the twenty-fifth of October."),
    ("Your exam is on Oct 3, 2026.", "Your exam is on October third, twenty twenty-six."),
    ("Due 2026-11-01.", "Due November first, twenty twenty-six."),
    ("Sunday the 22nd works.", "Sunday the twenty-second works."),
    ("Your CPU is at 82°C.", "Your CPU is at eighty-two degrees."),
    ("It's -3°C outside, feels like -8 °C.", "It's minus three degrees outside, feels like minus eight degrees."),
    ("You've used 32% of your limit.", "You've used thirty-two percent of your limit."),
    ("Battery at 5.5%.", "Battery at five point five percent."),
    ("Timer set for 5 min.", "Timer set for five minutes."),
    ("About 1h 30m left.", "About one hour thirty minutes left."),
    ("Wind at 11 km/h.", "Wind at eleven kilometres per hour."),
    ("16 GB of RAM, 2 TB free.", "sixteen gigabytes of RAM, two terabytes free."),
    ("PipeWire 1.6.10 is installed.", "PipeWire one point six point ten is installed."),
    ("◆ THEME → MARK III", "Theme to Mark three"),
    ("Switched to VIBRANIUM; lights follow.", "Switched to Vibranium, lights follow."),
    ("Status: all good.", "Status, all good."),
    ("Pi is about 3.14.", "Pi is about three point one four."),
    ("That's 1,250 files.", "That's one thousand two hundred fifty files."),
    ("Load is 5 percent (fine).", "Load is five percent, fine."),
    ("Opening UW CS e.g. the student server.", "Opening U W C S for example the student server."),
    ("It costs $4.99 & ships in 2025.", "It costs four point nine nine dollars and ships in twenty twenty-five."),
]
SPLITS = [
    ("It's four oh seven PM, sir. Shall I set a timer?", 2),
    ("The value is three point one four. Mr. Stark agrees.", 2),
    ("Done. Sir.", 1),
    ("Timer set. It'll ring at four PM; I'll remind you.", 1),   # short lead-in rides along; ';' is a comma   # ";" → a comma, not a stop

]

bad = 0
for i, (src, want) in enumerate(CASES, 1):
    got = normalize(src)
    ok = got == want
    bad += not ok
    print(f"{'ok ' if ok else 'BAD'} {i:>2}. {src!r}\n        → {got!r}" + ("" if ok else f"\n   want {want!r}"))
for src, n in SPLITS:
    got = sentences(normalize(src))
    ok = len(got) == n
    bad += not ok
    print(f"{'ok ' if ok else 'BAD'} split {src!r} → {got}")
print(f"\n{len(CASES) + len(SPLITS) - bad}/{len(CASES) + len(SPLITS)} passed")
sys.exit(1 if bad else 0)
