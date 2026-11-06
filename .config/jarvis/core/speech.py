"""
Text → what Jarvis should actually say. Runs on every line before TTS, so Kokoro
never sees "16:07" (it read "sixteen zero seven" with a pause at the colon), "82°C",
"32%", "Oct 25" or "◆".

  normalize("Timer due at 16:39, 32% done") → "Timer due at four thirty-nine PM, thirty-two percent done"
  sentences(text) → split only at real sentence ends (not decimals, times, "Mr.", "e.g.")

Tests: tests/test_speech.py (python tests/test_speech.py).
"""
import re

ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten", "eleven",
        "twelve", "thirteen", "fourteen", "fifteen", "sixteen", "seventeen", "eighteen", "nineteen"]
TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
ORD = {"one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth", "nine": "ninth",
       "twelve": "twelfth"}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December"]
MON = {m[:3].lower(): m for m in MONTHS} | {"sept": "September"}
DAYS = r"(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday)"
ROMAN = {"II": "two", "III": "three", "IV": "four", "VI": "six", "VII": "seven", "VIII": "eight", "IX": "nine"}
# Words the HUD writes in capitals that are words, not acronyms
CAPS_WORDS = r"STARK|MARK|VIBRANIUM|MATRIX|ARCTIC|SOLAR|AURUM|ARGENT|IRON|VERDIGRIS|MERCURY|LEAD|ALCHEMOS|ORRIN|SELENE|JARVIS|HOLOGRAM|SUIT|CLEAN|AUTO|MEDIA|TIMER|REMINDER|WEATHER"
ACRONYMS = r"HDMI|NVME|USB|ASCII|JSON|HTTPS|QWERTY"          # 5+ capitals that are still spelled out
UNITS = [  # (pattern after a number, singular, plural)
    (r"°\s?C\b|degrees? (?:C|Celsius)\b", "degree", "degrees"), (r"°\s?F\b|degrees? F(?:ahrenheit)?\b", "degree Fahrenheit", "degrees Fahrenheit"),
    (r"°", "degree", "degrees"), (r"km/h|kmh|kph", "kilometre per hour", "kilometres per hour"),
    (r"mph", "mile per hour", "miles per hour"), (r"km\b", "kilometre", "kilometres"), (r"kg\b", "kilogram", "kilograms"),
    (r"GB\b", "gigabyte", "gigabytes"), (r"MB\b", "megabyte", "megabytes"), (r"TB\b", "terabyte", "terabytes"),
    (r"KB\b", "kilobyte", "kilobytes"), (r"GHz\b", "gigahertz", "gigahertz"), (r"MHz\b", "megahertz", "megahertz"),
    (r"ms\b", "millisecond", "milliseconds"), (r"fps\b", "frame per second", "frames per second"),
    (r"hrs?\b|h\b", "hour", "hours"), (r"mins?\b|m\b", "minute", "minutes"), (r"secs?\b|s\b", "second", "seconds"),
    (r"W\b", "watt", "watts"), (r"%| per ?cent\b", "percent", "percent"),
]
ABBREV = {"e.g.": "for example", "i.e.": "that is", "etc.": "et cetera", "vs.": "versus", "vs": "versus",
          "approx.": "about", "Dr.": "Doctor", "Mr.": "Mister", "Mrs.": "Missus", "Ms.": "Miz", "St.": "Saint"}


# ── numbers ──
def number(n):
    """Integer → words: 1234 → 'one thousand two hundred thirty-four'."""
    n = int(n)
    if n < 0:
        return "minus " + number(-n)
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("-" + ONES[n % 10] if n % 10 else "")
    if n < 1000:
        return ONES[n // 100] + " hundred" + (" " + number(n % 100) if n % 100 else "")
    for size, word in ((10 ** 9, "billion"), (10 ** 6, "million"), (1000, "thousand")):
        if n >= size:
            return number(n // size) + " " + word + (" " + number(n % size) if n % size else "")
    return str(n)


def ordinal(n):
    """25 → 'twenty-fifth'."""
    w = number(n)
    head, sep, last = w.rpartition("-") if "-" in w.split()[-1] else w.rpartition(" ")
    if last in ORD:
        last = ORD[last]
    elif last.endswith("y"):
        last = last[:-1] + "ieth"
    else:
        last += "th"
    return head + sep + last


def year(y):
    y = int(y)
    if 2000 <= y < 2010:
        return number(y)
    if 1100 <= y < 2100:
        hi, lo = divmod(y, 100)
        return number(hi) + " " + ("hundred" if lo == 0 else ("oh " + ONES[lo] if lo < 10 else number(lo)))
    return number(y)


def decimal(s):
    """'3.14' → 'three point one four'; '1,234.5' → 'one thousand two hundred thirty-four point five'."""
    s = s.replace(",", "")
    neg = s.startswith("-")
    s = s.lstrip("-+")
    whole, _, frac = s.partition(".")
    out = number(int(whole or 0))
    if frac:
        out += " point " + " ".join(ONES[int(d)] for d in frac)
    return ("minus " if neg else "") + out


def clock(h, m, suffix=""):
    """(16, 7) → 'four oh seven PM'; (16, 0) → "four o'clock PM"; (12, 0) → 'noon'."""
    h, m = int(h), int(m)
    suffix = suffix.replace(".", "").upper()
    if suffix not in ("AM", "PM"):
        suffix = ""
        if h > 12:
            h, suffix = h - 12, "PM"
        elif h == 0:
            if m == 0:
                return "midnight"
            h, suffix = 12, "AM"
    if m == 0 and h == 12 and suffix in ("", "PM"):
        return "noon" if suffix == "PM" or not suffix else "midnight"
    if m == 0 and h == 12 and suffix == "AM":
        return "midnight"
    hour = number(h)
    if m == 0:
        spoken = f"{hour} o'clock" if not suffix else hour
    elif m < 10:
        spoken = f"{hour} oh {ONES[m]}"
    else:
        spoken = f"{hour} {number(m)}"
    return f"{spoken} {suffix}".strip()


# ── normalization passes ──
def _times(t):
    # 4:07 PM / 16:07 / 4pm / 4 p.m. / 16:07:31 (seconds dropped)
    ampm = r"(?:[AaPp]\.[Mm]\.|[AaPp][Mm]\b)"      # "p.m." eats its dots; "PM." keeps the full stop
    t = re.sub(rf"\b([01]?\d|2[0-3]):([0-5]\d)(?::[0-5]\d)?(?:\s*({ampm}))?(?![\d:])",
               lambda m: clock(m.group(1), m.group(2), m.group(3) or ""), t)
    t = re.sub(rf"\b(1[0-2]|0?[1-9])\s*({ampm})", lambda m: clock(m.group(1), 0, m.group(2)), t)
    return t


def _dates(t):
    # ISO 2026-10-25
    t = re.sub(r"\b(\d{4})-(\d{2})-(\d{2})\b",
               lambda m: f"{MONTHS[int(m.group(2)) - 1]} {ordinal(int(m.group(3)))}, {year(m.group(1))}"
               if 1 <= int(m.group(2)) <= 12 else m.group(0), t)
    mon = r"(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?|Sept?(?:ember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?"
    full = lambda s: MON.get(s.lower().rstrip(".")[:4] if s.lower().startswith("sept") else s.lower()[:3], s)
    # October 25(th)(, 2026)
    t = re.sub(rf"\b{mon} (\d{{1,2}})(?:st|nd|rd|th)?\b(?:,? (\d{{4}}))?",
               lambda m: f"{full(m.group(1))} {ordinal(int(m.group(2)))}" + (f", {year(m.group(3))}" if m.group(3) else ""), t)
    # (the) 25(th) (of) October
    t = re.sub(rf"\b(?:the )?(\d{{1,2}})(?:st|nd|rd|th)? (?:of )?{mon}\b(?:,? (\d{{4}}))?",
               lambda m: f"the {ordinal(int(m.group(1)))} of {full(m.group(2))}" + (f", {year(m.group(3))}" if m.group(3) else ""), t)
    # Sunday the 25th / the 3rd
    t = re.sub(r"\b(\d{1,2})(?:st|nd|rd|th)\b", lambda m: ordinal(int(m.group(1))), t)
    return t


def _units(t):
    num = r"(-?\d[\d,]*(?:\.\d+)?)"
    for pat, one, many in UNITS:
        t = re.sub(rf"{num}\s?(?:{pat})",
                   lambda m: f"{decimal(m.group(1))} {one if m.group(1).replace(',', '') in ('1', '1.0') else many}", t)
    return t


def _numbers(t):
    t = re.sub(r"\bv?(\d+)\.(\d+)\.(\d+)\b", lambda m: " point ".join(number(int(g)) for g in m.groups()), t)  # versions
    t = re.sub(r"(?<![\d.])(1[1-9]\d\d|20\d\d)(?!\d|[.,]\d)", lambda m: year(m.group(1))
               if re.search(r"(?:in|since|of|from|by|year|until|,)\s*$", t[:m.start()]) else m.group(0), t)
    t = re.sub(r"\$(\d[\d,]*(?:\.\d\d)?)", lambda m: decimal(m.group(1)) + " dollars", t)
    t = re.sub(r"(?<![\w.])-?\d[\d,]*\.\d+(?!\d|\.\d)", lambda m: decimal(m.group(0)), t)
    t = re.sub(r"(?<![\w.])-?\d{1,3}(?:,\d{3})+(?!\d|\.\d)|(?<![\w.])-?\d+(?!\d|\.\d)", lambda m: decimal(m.group(0)), t)
    return t


def _symbols(t):
    t = re.sub(r"https?://\S+", "a link", t)
    t = re.sub(r"[`*_#>|◆◇■□●○▸▶►•]+", " ", t)
    t = re.sub(r"^\s*[-–]\s+", "", t, flags=re.M)
    t = t.replace("→", " to ").replace("←", " from ").replace("&", " and ").replace("×", " times ")
    t = re.sub(r"\s[–—-]\s|[–—]", ", ", t)
    t = re.sub(r"\s*\(\s*|\s*\)\s*", ", ", t)
    t = t.replace("…", ".").replace("~", "about ").replace("≈", "about ").replace(" + ", " plus ").replace(" = ", " equals ")
    t = re.sub(r"(?<=[a-z]):\s", ", ", t)          # "Status: fine" — a colon makes Kokoro stop dead
    t = re.sub(r";\s*", ", ", t)
    return t


def _words(t):
    for a, b in ABBREV.items():
        t = re.sub(rf"(?<!\w){re.escape(a)}(?!\w)", b, t)
    t = re.sub(r"\b(II|III|IV|VI|VII|VIII|IX)\b", lambda m: ROMAN[m.group(1)], t)    # MARK III
    t = re.sub(rf"\b(?:{CAPS_WORDS})\b|\b(?!(?:{ACRONYMS})\b)[A-Z]{{5,}}\b", lambda m: m.group(0).title(), t)
    t = re.sub(r"\bUW ?CS\b", "U W C S", t)
    t = re.sub(r"\bSTARK OS\b|\bStark OS\b", "Stark O S", t)
    return t


def normalize(text):
    t = _symbols(text)
    t = _words(t)
    t = _times(t)
    t = _dates(t)
    t = _units(t)
    t = _numbers(t)
    t = re.sub(r"(?<=\w)/(?=\w)", " or ", t)       # after units, so km/h is already gone
    t = re.sub(r"\s+([,.!?])", r"\1", t)
    t = re.sub(r",\s*,+", ",", t)
    t = re.sub(r",\s*([.!?])", r"\1", t)
    t = re.sub(r"^[,\s]+|[,\s]+$", "", t)
    return re.sub(r"\s+", " ", t).strip()


def sentences(text):
    """Split at real sentence ends only. Short fragments ride with the previous sentence,
    so "Done. Sir." doesn't get its own pause."""
    parts = [p.strip() for p in re.split(r"(?<=[.!?])[\"')\]]?\s+(?=[\"'(\[]?[A-Z0-9])", text) if p.strip()]
    out = []
    for p in parts:
        if out and (len(p.split()) <= 2 or len(out[-1].split()) <= 2):
            out[-1] += " " + p
        else:
            out.append(p)
    return out
