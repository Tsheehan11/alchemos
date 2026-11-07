"""fontcheck.py [HUD_DIR]: every Text-like element in the HUD names a font role (Style.fonts.<role>), so
nothing falls back to whatever face the system picks. Prints one line per offender, exits 1 if any.

A Text passes when its own block sets font.family to an expression that uses Style.fonts.<role>, or to
<id>.<prop> where <prop> is declared in the same file as a string property built from Style.fonts.
Text-like: Text, TextInput, TextEdit, TextField, TextArea, Label, NumText; SigilText is exempt (it sets its own)."""
import re
import sys
from pathlib import Path

hud = Path(sys.argv[1] if len(sys.argv) > 1 else Path(__file__).resolve().parents[2])
TEXTY = r"(?<![\w.])(Text|TextInput|TextEdit|TextField|TextArea|Label|NumText)\s*\{"


def block(s, i):
    """the text of the { … } block that opens just before i, nested blocks blanked out"""
    depth, j = 1, i
    while depth and j < len(s):
        depth += {"{": 1, "}": -1}.get(s[j], 0)
        j += 1
    body = s[i:j - 1]
    flat = body
    while re.search(r"\{[^{}]*\}", flat):
        flat = re.sub(r"\{[^{}]*\}", "", flat)
    return flat


bad = []
for f in sorted(hud.rglob("*.qml")):
    rel = f.relative_to(hud)
    if rel.parts[0] == "tools" or "baseline" in rel.parts:
        continue
    s = f.read_text()
    roleprops = set(re.findall(r"property\s+string\s+(\w+)\s*:[^\n]*Style\.fonts\.", s))
    for m in re.finditer(TEXTY, s):
        flat = block(s, m.end())
        line = s[:m.start()].count("\n") + 1
        if re.search(r"(?<![\w.])font\s*:\s*\w+\.font\b", flat):
            continue          # a placeholder taking its input's font (which has a role)
        fam = re.search(r"font\.family\s*:\s*([^;\n]+)", flat)
        if not fam:
            bad.append(f"{rel}:{line}: {m.group(1)} without font.family")
            continue
        rhs = fam.group(1).strip()
        if "Style.fonts." in rhs:
            continue
        ref = re.fullmatch(r"(?:\w+\.)?(\w+)", rhs)
        if ref and ref.group(1) in roleprops:
            continue
        bad.append(f"{rel}:{line}: font.family {rhs} is not a Style.fonts role")
for b in bad:
    print(b)
sys.exit(1 if bad else 0)
