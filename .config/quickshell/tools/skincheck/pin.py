"""pin.py FILE...: rewrite the HUD's window files in skincheck's temp copy so they render as plain Items, the
same every run: PanelWindow → WinStub (minus the layer-shell lines), Hyprland → HyprMock, Math.random →
Seeded.at, no live audio sink / commands / clock, continuous spins stopped."""
import re
import sys
from pathlib import Path

def seeded(s):
    # each Math.random() call site gets its own fixed value per delegate index: the same however often
    # (and in whatever order) a binding re-evaluates
    n = iter(range(1, 10 ** 6))
    return re.sub(r"Math\.random\(\)", lambda m: f'Seeded.at({next(n)}, typeof index === "number" ? index : 0)', s)


for f in map(Path, sys.argv[1:]):
    s = f.read_text()
    if "Math.random()" in s:
        s = seeded(s)
    if not re.search(r"^PanelWindow \{", s, re.M):
        f.write_text(s)
        continue
    s = re.sub(r"^PanelWindow \{", "WinStub {", s, count=1, flags=re.M)
    # the window's own layer-shell settings (root level, four spaces in)
    s = re.sub(r"^    (WlrLayershell\.\w+|exclusionMode|margins|mask)\b.*\n", "", s, flags=re.M)
    s = re.sub(r"^    anchors \{[^}\n]*: *true[^}\n]*\}\n", "", s, flags=re.M)
    s = re.sub(r"(?<![.\w])Hyprland\.", "HyprMock.", s)
    s = s.replace("Pipewire.defaultAudioSink", "null")
    s = s.replace("new Date()", "new Date(2026, 0, 1, 10, 8, 30)")
    # endless spins and drifts, and timers that poll the system: not running
    s = re.sub(r"((?:RotationAnimation|NumberAnimation) on (?:rotation|t|x) \{[^}]*?running:)[^;\n}]+", r"\1 false", s)
    s = re.sub(r"(Timer \{[^}]*?running:)[^;\n}]+(;[^}]*?onTriggered: poll\.running)", r"\1 false\2", s)
    f.write_text(s)
