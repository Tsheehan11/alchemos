"""
Audio devices for Jarvis: what's plugged in, what a spoken name means, and switching.

Used by the set_audio_output / set_audio_input / list_audio_devices tools (stark_actions), the
fast path, the HUD (`jarvis audio …`, called by quickshell Audio.qml so a pick in Settings also
moves the playing streams and counts as his choice), and the voice loop's microphone pick.

Kinds, worked out from PipeWire's own properties (pactl -f json):
  headphones  Bluetooth headphones / headsets, the 3.5 mm jack, USB headsets
  speaker     the Bluetooth room speaker (jarvisSpeaker, the Google Home)
  laptop      the laptop's built-in speakers / digital microphone
  tv          an HDMI / DisplayPort output whose port is connected (a monitor or TV with speakers)
  usb         other USB audio (a dongle, the desk's USB mic)
  other

An explicit choice (his voice command or a Settings pick) is written to
$XDG_RUNTIME_DIR/jarvis/audio-choice.json with the set of devices present at the time. While that
set is unchanged, Jarvis's voice follows the default output instead of the "room speaker when
no headphones" rule (core/voice.py Speaker.wanted). Plugging or unplugging anything ends it.
"""
import json
import os
import re
import subprocess
import time
from pathlib import Path

HOME = Path.home()
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
CHOICE_FILE = RUNTIME / "jarvis" / "audio-choice.json"
HUD_SETTINGS = HOME / ".config/quickshell/settings.json"
JARVIS_STREAM = "Jarvis wake word"          # Jarvis's own capture: it follows jarvisMic, never moved here

# spoken word → kinds it can mean (first is preferred when several kinds are present)
WORDS = [
    (r"head ?phones?|head ?sets?|ear ?buds?|ear ?phones?|air ?pods?|cans|my sony|sonys?|xm ?\d|bluetooth headphones?", ["headphones"]),
    (r"(?:room |bluetooth |google |nest )?speakers?|google home|google|nest|home speaker|room", ["speaker"]),
    (r"bluetooth", ["bluetooth"]),
    (r"laptop(?: speakers?| mic(?:rophone)?| audio)?|built ?in(?: speakers?| mic(?:rophone)?)?|internal(?: speakers?| mic(?:rophone)?)?|"
     r"computer(?: speakers?)?|(?:digital |laptop |the )?mic(?:rophone)?|dmic", ["laptop"]),
    (r"(?:tv|television)(?: speakers?)?|monitor(?: speakers?)?|hdmi|display ?port|screen", ["tv"]),
    (r"usb(?: audio| mic(?:rophone)?| dongle)?|desk mic(?:rophone)?", ["usb"]),
]
# "the speakers" when no room speaker is set up means the laptop's own
SPEAKER_FALLBACK = "laptop"


def _pactl(*args, timeout=3):
    try:
        p = subprocess.run(["pactl", *args], capture_output=True, text=True, timeout=timeout)
        return p.stdout if p.returncode == 0 else ""
    except (OSError, subprocess.TimeoutExpired):
        return ""


def _json(*args):
    try:
        return json.loads(_pactl("-f", "json", *args) or "[]")
    except ValueError:
        return []


def room_speaker_mac():
    try:
        return str(json.loads(HUD_SETTINGS.read_text()).get("jarvisSpeaker") or "").strip()
    except (OSError, ValueError):
        return ""


def _port_ok(d):
    """False when PipeWire says the active port is unplugged (HDMI with nothing on it, an empty jack)."""
    port = d.get("active_port")
    for p in d.get("ports") or []:
        if p.get("name") == port:
            return p.get("availability") != "not available"
    return True


def classify(d, direction, mac=""):
    p = d.get("properties") or {}
    name = d.get("name", "")
    hints = " ".join(str(x) for x in (p.get("device.form_factor"), p.get("device.icon_name"), d.get("active_port"),
                                      d.get("description"))).lower()
    bus = p.get("device.bus") or ""
    if name.startswith(("bluez_output.", "bluez_input.")):
        dev_mac = (p.get("api.bluez5.address") or re.sub(r"^bluez_(?:output|input)\.|\.\d+$", "", name)).replace("_", ":").upper()
        if mac and dev_mac.startswith(mac.upper()):
            return "speaker"
        if re.search(r"head(phone|set)|hands-?free", hints):
            return "headphones"
        return "speaker" if direction == "out" else "headphones"
    if re.search(r"hdmi|displayport|video-display", hints) or "HDMI" in name:
        return "tv"
    if re.search(r"head(phone|set)", hints):
        return "headphones"
    if bus == "usb":
        return "usb"
    if bus == "pci" or "alsa_" in name:
        return "laptop"
    return "other"


def devices(direction="out"):
    """[{name, label, kind, available, default, bluetooth}] for outputs ("out") or inputs ("in"), no monitors."""
    mac = room_speaker_mac()
    raw = _json("list", "sinks" if direction == "out" else "sources")
    default = _pactl("get-default-sink" if direction == "out" else "get-default-source").strip()
    out = []
    for d in raw:
        name = d.get("name", "")
        if name.endswith(".monitor") or (d.get("properties") or {}).get("device.class") == "monitor":
            continue
        kind = classify(d, direction, mac)
        out.append({"name": name, "label": d.get("description") or name, "kind": kind,
                    "available": _port_ok(d), "default": name == default,
                    "bluetooth": name.startswith("bluez_")})
    return out


def signature():
    """The set of devices present (outputs + inputs, available ones): changes on any plug / unplug."""
    names = [d["name"] for d in devices("out") + devices("in") if d["available"]]
    return sorted(names)


# ── explicit choice ────────────────────────────
def mark_choice(direction, name):
    try:
        CHOICE_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            data = json.loads(CHOICE_FILE.read_text())
        except (OSError, ValueError):
            data = {}
        data[direction] = name
        data["devices"] = signature()
        data["at"] = time.time()
        tmp = CHOICE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(data))
        tmp.replace(CHOICE_FILE)
    except OSError:
        pass


def explicit_output(sig=None):
    """The output he picked himself, if no device has come or gone since; else None (and the choice is dropped)."""
    try:
        data = json.loads(CHOICE_FILE.read_text())
    except (OSError, ValueError):
        return None
    if not data.get("out"):
        return None
    if (sig if sig is not None else signature()) != data.get("devices"):
        try:
            CHOICE_FILE.unlink()
        except OSError:
            pass
        return None
    return data["out"]


def choice_mtime():
    try:
        return CHOICE_FILE.stat().st_mtime
    except OSError:
        return 0.0


# ── spoken name → device ───────────────────────
def _norm(s):
    s = re.sub(r"[^\w\s]", " ", str(s or "").lower())
    s = re.sub(r"^(?:to |on |onto |the |my |back to |over to )+", "", " ".join(s.split()))
    s = re.sub(r"^(?:the |my )+", "", s)
    return re.sub(r"\s+(?:please|instead|now)$", "", s).strip()


def resolve(spoken, direction="out", devs=None):
    """→ ("ok", device) | ("ask", [devices]) | ("none", reason). Never guesses between two candidates."""
    devs = devs if devs is not None else devices(direction)
    usable = [d for d in devs if d["available"]]
    t = _norm(spoken)
    if not t:
        return "none", "no device named"
    for d in usable:                                   # an exact node name (the HUD, or Claude after list_audio_devices)
        if t == d["name"].lower():
            return "ok", d
    words = set(t.split())
    by_label = [d for d in usable if t in d["label"].lower()
                or (len(t) > 3 and words <= set(re.sub(r"[^\w\s]", " ", d["label"].lower()).split()))]
    if len(by_label) == 1:
        return "ok", by_label[0]
    kinds = None
    tk = re.sub(r"\s+(?:mic(?:rophone)?|audio|output|input|sound)$", "", t) or t     # "headset mic" → "headset"
    for pat, ks in WORDS:
        if re.fullmatch(pat, tk) or re.fullmatch(pat, t):
            kinds = ks
            break
    if kinds is None:
        if len(by_label) > 1:
            return "ask", by_label
        return "none", f'no {"output" if direction == "out" else "microphone"} called "{spoken}"'
    kind = kinds[0]
    hits = [d for d in usable if (d["bluetooth"] if kind == "bluetooth" else d["kind"] == kind)]
    if kind in ("speaker", "tv") and direction == "in":
        return "none", "that has no microphone"
    if kind == "speaker" and not hits:
        if direction == "out" and room_speaker_mac():
            return "connect", room_speaker_mac()      # the Google Home is paired but not connected right now
        hits = [d for d in usable if d["kind"] == SPEAKER_FALLBACK]
    if kind == "laptop" and len(hits) > 1:            # several laptop sinks: the actual speaker / DMIC, not a jack
        best = [d for d in hits if re.search(r"speaker|digital microphone|mic1", d["label"] + " " + d["name"], re.I)]
        hits = best or hits
    if len(hits) == 1:
        return "ok", hits[0]
    if not hits:
        what = {"headphones": "headphones or headset", "speaker": "room speaker", "laptop": "laptop speakers",
                "tv": "TV or monitor with sound", "usb": "USB audio device"}.get(kind, kind)
        return "none", f"no {what} {'connected' if kind != 'laptop' else 'found'}"
    return "ask", hits


# ── switching ──────────────────────────────────
def _connect_bt(mac, wait_s=10):
    """Connect the room speaker and wait for its sink. → sink name or None."""
    prefix = "bluez_output." + mac.replace(":", "_")
    for _ in range(3):              # the first page after idle often times out (core/voice.py Speaker)
        try:
            subprocess.run(["bluetoothctl", "--timeout", "8", "connect", mac], capture_output=True, timeout=12)
        except (OSError, subprocess.TimeoutExpired):
            pass
        t0 = time.monotonic()
        while time.monotonic() - t0 < wait_s / 3:
            s = next((d["name"] for d in devices("out") if d["name"].startswith(prefix)), None)
            if s:
                return s
            time.sleep(0.3)
    return None


def move_streams(direction, target):
    """Move every playing stream (outputs) / recording stream (inputs, except Jarvis's own) to target. → count."""
    kind = "sink-inputs" if direction == "out" else "source-outputs"
    moved = 0
    for s in _json("list", kind):
        p = s.get("properties") or {}
        if direction == "in" and (p.get("media.name") == JARVIS_STREAM or p.get("stream.monitor") == "true"
                                  or str(p.get("node.name", "")).startswith(("bluez_capture_internal", "loopback"))):
            continue
        if direction == "out" and str(p.get("node.name", "")).startswith(("loopback",)):
            continue
        try:
            r = subprocess.run(["pactl", "move-" + kind[:-1], str(s["index"]), target], capture_output=True, timeout=3)
            moved += r.returncode == 0
        except (OSError, subprocess.TimeoutExpired, KeyError):
            pass
    return moved


def switch(direction, name, mark=True):
    """Make node `name` the default output / input and bring the streams with it."""
    r = subprocess.run(["pactl", "set-default-sink" if direction == "out" else "set-default-source", name],
                       capture_output=True, text=True, timeout=3)
    if r.returncode != 0:
        return {"ok": False, "error": (r.stderr or "pactl failed").strip()[:200]}
    moved = move_streams(direction, name)
    if mark:
        mark_choice(direction, name)
    return {"ok": True, "device": name, "moved": moved}


def cli(argv):
    """jarvis audio list [--json] | output NAME | input NAME   (the HUD's Settings → AUDIO calls output / input)."""
    if not argv or argv[0] == "list":
        d = {"outputs": devices("out"), "inputs": devices("in")}
        if "--json" in argv:
            print(json.dumps(d))
        else:
            for k, items in d.items():
                print(k.upper())
                for x in items:
                    print(f"  {'*' if x['default'] else ' '} {x['kind']:<10} {x['label']}{'' if x['available'] else ' (unplugged)'}")
        return 0
    if argv[0] in ("output", "input") and len(argv) > 1:
        r = switch("out" if argv[0] == "output" else "in", argv[1])
        print(json.dumps(r))
        return 0 if r["ok"] else 1
    print(cli.__doc__)
    return 2
