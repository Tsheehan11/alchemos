"""
STARK OS actions for Jarvis: the explicit allowlist of things it may do.

Each action validates its arguments, then wraps an existing command or HUD IPC
call (hyprctl, qs ipc, stark-govee, stark-vpn, playerctl, wpctl, the uwcs fish
function). Nothing here runs a shell string built from arguments. Used by the
MCP server (stark_tools.py) and directly by Jarvis's no-AI fast path.

Every action returns a dict: {"ok": True, ...} or {"ok": False, "error": "..."}.
With STARK_DRY_RUN=1 (or set_dry_run(True)) actions validate, then report what
they would do instead of doing it.
"""
import configparser
import difflib
import glob
import json
import os
import re
import shlex
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

import jarvis_db as db

HOME = Path.home()
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
DRY_RUN = os.environ.get("STARK_DRY_RUN") == "1"
CLAUDE_URL = "https://claude.ai/new"


def set_dry_run(on):
    global DRY_RUN
    DRY_RUN = bool(on)


class Invalid(ValueError):
    """A tool argument outside the allowlist."""


# ── plumbing ───────────────────────────────────
def _run(cmd, timeout=6):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    except FileNotFoundError:
        return 127, "", f"{cmd[0]} not installed"
    except subprocess.TimeoutExpired:
        return 124, "", f"{cmd[0]} timed out"


def _do(would, cmd, ok_msg=None, timeout=6):
    """Run cmd (a list, no shell) unless dry-running; result dict either way."""
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": would}
    rc, out, err = _run(cmd, timeout)
    if rc != 0:
        return {"ok": False, "error": (err or out or f"exit {rc}")[-300:]}
    return {"ok": True, "result": ok_msg or out or "done"}


def _qs(target, fn, *args):
    return ["qs", "ipc", "call", target, fn, *[str(a) for a in args]]


def _lua(s):
    """A Lua string literal, for Hyprland's Lua dispatchers (hyprctl dispatch 'hl.dsp…')."""
    s = str(s).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{s}"'


def _hypr_dispatch(dsp):
    return ["hyprctl", "dispatch", dsp]


def _hypr_exec(cmd):
    """Start a program through Hyprland so it isn't a child of Jarvis."""
    return _hypr_dispatch(f"hl.dsp.exec_cmd({_lua(cmd)})")


def _norm(s):
    s = s.lower().strip()
    s = re.sub(r"[^\w\s']", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _int(v, lo, hi, what):
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        raise Invalid(f"{what} must be a number from {lo} to {hi}")
    if not lo <= n <= hi:
        raise Invalid(f"{what} must be from {lo} to {hi}")
    return n


def _choice(v, options, what):
    v = str(v or "").strip().lower().replace(" ", "_").replace("-", "_")
    if v not in options:
        raise Invalid(f"{what} must be one of: {', '.join(options)}")
    return v


def safe(fn):
    """Turn validation errors / surprises into {"ok": False} results."""
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except Invalid as e:
            return {"ok": False, "error": str(e)}
        except Exception as e:  # never crash the caller over one tool
            return {"ok": False, "error": f"{type(e).__name__}: {e}"[:300]}
    wrapper.__name__, wrapper.__doc__ = fn.__name__, fn.__doc__
    wrapper.__wrapped__ = fn
    return wrapper


# ── apps ───────────────────────────────────────
ALIASES = {
    "claude": f"zen-browser --new-window {CLAUDE_URL}",
    "claude code": "kitty -e claude",
    "code": "code", "vs code": "code", "vscode": "code", "v s code": "code",
    "visual studio code": "code", "visual studio": "code",
    "browser": "zen-browser", "zen": "zen-browser", "web": "zen-browser", "internet": "zen-browser",
    "terminal": "kitty", "kitty": "kitty", "console": "kitty",
    "files": "dolphin", "file manager": "dolphin", "dolphin": "dolphin",
    "spotify": "spotify-launcher", "music": "spotify-launcher",
    "steam": "steam", "games": "steam",
    "discord": "discord",
    "settings": "systemsettings", "system settings": "systemsettings",
}
_APPS = None


def apps():
    """name → command for every installed app (.desktop files), cached."""
    global _APPS
    if _APPS is not None:
        return _APPS
    found = {}
    for d in ["/usr/share/applications", str(HOME / ".local/share/applications"),
              "/var/lib/flatpak/exports/share/applications"]:
        for path in glob.glob(os.path.join(d, "*.desktop")):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            try:
                cp.read(path, encoding="utf-8")
                e = cp["Desktop Entry"]
            except Exception:
                continue
            if e.get("Type", "") != "Application" or e.get("NoDisplay", "false").lower() == "true":
                continue
            name, exe = e.get("Name"), e.get("Exec")
            if not name or not exe:
                continue
            exe = re.sub(r"\s*%[a-zA-Z]", "", exe).strip()
            found.setdefault(_norm(name), exe)
            if e.get("GenericName"):
                found.setdefault(_norm(e.get("GenericName")), exe)
    _APPS = found
    return found


def find_app(target):
    """(command, display name) for a spoken app name, or (None, None)."""
    t = _norm(target)
    t = re.sub(r"^(the|my)\s+", "", t)
    t = re.sub(r"\s+(app|application)$", "", t)
    if not t:
        return None, None
    table = apps()
    if t in ALIASES:
        return ALIASES[t], t
    if t in table:
        return table[t], t
    for n, cmd in table.items():
        if n.startswith(t) or t in n.split():
            return cmd, n
    m = difflib.get_close_matches(t, list(ALIASES) + list(table), n=1, cutoff=0.75)
    if m:
        return ALIASES.get(m[0]) or table[m[0]], m[0]
    return None, None


# Single-window apps: "open X" shows the running window instead of starting another.
# Spotify lives on the special:music workspace (Super+M), so that gets shown.
SINGLE = {"spotify-launcher": "spotify", "spotify": "spotify", "discord": "discord", "steam": "steam",
          "systemsettings": "systemsettings"}


def _running_window(cmd):
    cls = SINGLE.get(cmd.split()[0])
    if not cls:
        return None
    rc, out, _ = _run(["hyprctl", "clients", "-j"])
    try:
        clients = json.loads(out) if rc == 0 else []
    except ValueError:
        return None
    return next((c for c in clients if cls in (c.get("class") or "").lower()), None)


def _show_window(win, found):
    ws = (win.get("workspace") or {}).get("name", "")
    if ws.startswith("special:"):
        rc, out, _ = _run(["hyprctl", "monitors", "-j"])
        try:
            shown = {(m.get("specialWorkspace") or {}).get("name") for m in json.loads(out)} if rc == 0 else set()
        except ValueError:
            shown = set()
        if ws not in shown:
            r = _do(f"show {ws}", _hypr_dispatch(f"hl.dsp.workspace.toggle_special({_lua(ws.split(':', 1)[1])})"))
            if not r["ok"]:
                return r
    return _do(f"focus {found}", _hypr_dispatch(f"hl.dsp.focus({{ window = {_lua('address:' + win['address'])} }})"), f"{found} is up")


@safe
def open_app(name):
    """Open an installed application by name (e.g. "spotify", "vs code", "discord"). Shows it if it's already running."""
    cmd, found = find_app(str(name))
    if not cmd:
        raise Invalid(f'no installed app called "{name}"')
    win = _running_window(cmd)
    if win:
        return _show_window(win, found)
    return _do(f"open {found} ({cmd})", _hypr_exec(cmd), f"opened {found}")


@safe
def close_focused_window():
    """Close the focused window. Needs confirmation."""
    rc, out, _ = _run(["hyprctl", "activewindow", "-j"])
    try:
        w = json.loads(out) if rc == 0 else {}
    except ValueError:
        w = {}
    if not w.get("address"):
        raise Invalid("no window is focused")
    title = w.get("class") or w.get("title") or "window"
    return _do(f"close {title}", _hypr_dispatch("hl.dsp.window.close()"), f"closed {title}")


def focused_window_name():
    rc, out, _ = _run(["hyprctl", "activewindow", "-j"])
    try:
        w = json.loads(out) if rc == 0 else {}
    except ValueError:
        return "the window"
    name = w.get("initialTitle") or w.get("class") or w.get("title") or "the window"
    return name[:1].upper() + name[1:]


# ── workspaces ─────────────────────────────────
@safe
def switch_workspace(n):
    """Switch to workspace n (1-10)."""
    n = _int(n, 1, 10, "workspace")
    return _do(f"workspace {n}", _hypr_dispatch(f"hl.dsp.focus({{ workspace = {n} }})"), f"workspace {n}")


@safe
def move_window_to_workspace(n):
    """Move the focused window to workspace n (1-10), following it."""
    n = _int(n, 1, 10, "workspace")
    return _do(f"move window to workspace {n}", _hypr_dispatch(f"hl.dsp.window.move({{ workspace = {n}, follow = true }})"),
               f"window moved to workspace {n}")


# ── theme ──────────────────────────────────────
_NUM = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
        "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
_ROMAN = {"i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5", "vi": "6", "vii": "7",
          "viii": "8", "ix": "9", "x": "10"}


def _preset_key(s):
    """'MARK III' / 'mark three' / 'Mark 3' → 'mark3'."""
    words = _norm(s).split()
    out = []
    for i, w in enumerate(words):
        if w in _NUM:
            w = _NUM[w]
        elif w in _ROMAN and i > 0:  # only after a word: "mark iii", not a lone "i"
            w = _ROMAN[w]
        out.append(w)
    return "".join(out)


_PRESETS = (0.0, [])


def theme_presets():
    """Preset names from the HUD (built-ins + custom), [] if the HUD isn't running.
    Cached for a few seconds: one spoken request asks several times."""
    global _PRESETS
    if time.monotonic() - _PRESETS[0] < 5 and _PRESETS[1]:
        return _PRESETS[1]
    rc, out, _ = _run(_qs("theme", "presets"), timeout=3)
    try:
        names = json.loads(out) if rc == 0 else []
    except ValueError:
        names = []
    names = [n for n in names if isinstance(n, str)]
    _PRESETS = (time.monotonic(), names)
    return names


def match_preset(spoken, presets=None):
    presets = presets if presets is not None else theme_presets()
    key = _preset_key(spoken)
    for p in presets:
        if _preset_key(p) == key:
            return p
    keys = {_preset_key(p): p for p in presets}
    m = difflib.get_close_matches(key, list(keys), n=1, cutoff=0.8)
    return keys[m[0]] if m else None


@safe
def set_theme(preset):
    """Apply a HUD theme preset: built-in (STARK, MARK III, VIBRANIUM, MATRIX, ARCTIC, SOLAR) or a custom one."""
    presets = theme_presets()
    if not presets:
        return {"ok": False, "error": "the HUD isn't running, so themes can't change"}
    name = match_preset(str(preset), presets)
    if not name:
        raise Invalid(f"no theme preset \"{preset}\"; presets: {', '.join(presets)}")
    r = _do(f"theme {name}", _qs("theme", "preset", name), f"theme {name}")
    if r.get("ok") and not DRY_RUN and r.get("result", "").startswith("no preset"):
        return {"ok": False, "error": r["result"]}
    return r


# ── lights (Govee strip via stark-govee) ───────
LIGHT_MODES = ["auto", "music", "theme", "off"]
_ANIMS = None


def light_anims():
    global _ANIMS
    if _ANIMS is None:
        _, out, err = _run(["stark-govee", "anim"])
        m = re.search(r"animations:\s*(.+)", err or out)
        _ANIMS = [a.strip() for a in m.group(1).split(",")] if m else []
    return _ANIMS


@safe
def lights(action, value=""):
    """Govee light strip. action: mode (value auto|music|theme|off), on, off, brightness (value 5-100 %), anim (value = animation name)."""
    action = _choice(action, ["mode", "on", "off", "brightness", "anim"], "action")
    if action == "off":
        return _do("lights off", ["stark-govee", "mode", "off"], "lights off")
    if action == "on":
        return _do("lights on (auto)", ["stark-govee", "mode", "auto"], "lights on")
    if action == "mode":
        m = _choice(value, LIGHT_MODES, "mode")
        return _do(f"lights mode {m}", ["stark-govee", "mode", m], f"lights {m}")
    if action == "brightness":
        pct = _int(str(value).rstrip("%"), 5, 100, "brightness")
        return _do(f"lights {pct}%", ["stark-govee", "level", f"{pct / 100:.2f}"], f"lights at {pct}%")
    names = light_anims()
    a = _choice(value, names or ["boot"], "animation")
    return _do(f"lights animation {a}", ["stark-govee", "anim", a], f"played {a}", timeout=20)


# ── media ──────────────────────────────────────
MEDIA_ACTIONS = ["play", "pause", "play_pause", "next", "previous", "volume_up", "volume_down",
                 "set_volume", "mute", "unmute"]
SINK = "@DEFAULT_AUDIO_SINK@"


@safe
def media(action, value=""):
    """Music / volume. action: play, pause, play_pause, next, previous, volume_up, volume_down, set_volume (value 0-100), mute, unmute."""
    action = _choice(action, MEDIA_ACTIONS, "action")
    simple = {
        "play": ["playerctl", "play"], "pause": ["playerctl", "pause"],
        "play_pause": ["playerctl", "play-pause"], "next": ["playerctl", "next"],
        "previous": ["playerctl", "previous"],
        # same commands as the volume keys in hypr/stark/binds.lua
        "volume_up": ["wpctl", "set-volume", "-l", "1", SINK, "10%+"],
        "volume_down": ["wpctl", "set-volume", SINK, "10%-"],
        "mute": ["wpctl", "set-mute", SINK, "1"], "unmute": ["wpctl", "set-mute", SINK, "0"],
    }
    if action in simple:
        r = _do(action.replace("_", " "), simple[action], action.replace("_", " "))
        if not r["ok"] and "No players found" in r.get("error", ""):
            r["error"] = "nothing is playing"
        return r
    pct = _int(str(value).rstrip("%"), 0, 100, "volume")
    return _do(f"volume {pct}%", ["wpctl", "set-volume", "-l", "1", SINK, f"{pct / 100:.2f}"], f"volume {pct}%")


@safe
def what_is_playing():
    """Current track (title, artist, player, playing/paused) and output volume."""
    rc, out, _ = _run(["playerctl", "-a", "metadata", "--format",
                       "{{status}}\t{{playerName}}\t{{artist}}\t{{title}}"])
    players = [l.split("\t") for l in out.splitlines() if l.count("\t") == 3] if rc == 0 else []
    players.sort(key=lambda p: p[0] != "Playing")
    vol = None
    rc2, vout, _ = _run(["wpctl", "get-volume", SINK])
    m = re.search(r"([\d.]+)", vout or "")
    if rc2 == 0 and m:
        vol = round(float(m.group(1)) * 100)
    if not players:
        return {"ok": True, "playing": False, "volume": vol}
    status, player, artist, title = players[0]
    return {"ok": True, "playing": status == "Playing", "status": status.lower(), "player": player,
            "artist": artist, "title": title, "volume": vol, "muted": "MUTED" in (vout or "")}


# ── system status ──────────────────────────────
def _read(path, default=""):
    try:
        return Path(path).read_text().strip()
    except OSError:
        return default


def _hwmon(name):
    for d in glob.glob("/sys/class/hwmon/hwmon*"):
        if _read(f"{d}/name") == name:
            return d
    return None


def _cpu_percent(sample=0.15):
    def snap():
        f = [int(x) for x in _read("/proc/stat").splitlines()[0].split()[1:]]
        return sum(f), f[3] + f[4]
    t1, i1 = snap()
    time.sleep(sample)
    t2, i2 = snap()
    return round(100 * (1 - (i2 - i1) / max(1, t2 - t1)))


def docked():
    rc, out, _ = _run(["hyprctl", "monitors", "-j"])
    try:
        return any(not m["name"].startswith("eDP") for m in json.loads(out)) if rc == 0 else False
    except (ValueError, KeyError):
        return False


def combat_mode():
    try:
        return bool(json.loads(_read(RUNTIME / "stark-game/state.json", "{}")).get("active"))
    except ValueError:
        return False


@safe
def system_status():
    """Battery, temperatures, CPU/RAM use, network, VPN, docked or not, combat mode."""
    s = {"ok": True}
    cap = _read("/sys/class/power_supply/BAT0/capacity")
    if cap:
        s["battery"] = {"percent": int(cap), "status": _read("/sys/class/power_supply/BAT0/status").lower(),
                        "ac": _read("/sys/class/power_supply/AC/online") == "1"}
    temps = {}
    ct = _hwmon("coretemp")  # cheap reads; nvme / dell_smm are slow (BIOS SMM)
    if ct:
        for lab in glob.glob(f"{ct}/temp*_label"):
            if _read(lab).startswith("Package"):
                temps["cpu_c"] = int(_read(lab.replace("_label", "_input"), "0")) // 1000
    ddv = _hwmon("dell_ddv")
    if ddv:
        vals = [int(_read(p, "0")) // 1000 for p in glob.glob(f"{ddv}/temp*_input")]
        if vals:
            temps["max_board_c"] = max(vals)
    s["temps"] = temps
    s["cpu_percent"] = _cpu_percent()
    mem = dict(l.split(":", 1) for l in _read("/proc/meminfo").splitlines() if ":" in l)
    total = int(mem["MemTotal"].split()[0])
    avail = int(mem["MemAvailable"].split()[0])
    s["ram"] = {"used_percent": round(100 * (1 - avail / total)), "total_gb": round(total / 1048576, 1)}
    rc, out, _ = _run(["nmcli", "-t", "-f", "NAME,TYPE", "connection", "show", "--active"])
    s["network"] = [l.split(":")[0] for l in out.splitlines()
                    if l and ":loopback" not in l and ":dummy" not in l] if rc == 0 else []
    rc, out, _ = _run(["nmcli", "networking", "connectivity"])
    s["connectivity"] = out or "unknown"
    s["vpn"] = _vpn_summary(_vpn_state())
    s["docked"] = docked()
    s["combat_mode"] = combat_mode()
    return s


# ── VPN (stark-vpn) ────────────────────────────
def _vpn_state():
    rc, out, _ = _run(["stark-vpn", "status"], timeout=8)
    try:
        return json.loads(out) if rc == 0 else {}
    except ValueError:
        return {}


def _vpn_summary(st):
    active = st.get("active") or ""
    p = next((p for p in st.get("providers", []) if p.get("id") == active), {})
    return {"active": active or None, "state": p.get("state", "disconnected"),
            "server": p.get("server"), "country": p.get("country"),
            "kill_switch": next((q.get("killSwitch") for q in st.get("providers", []) if q.get("id") == "proton"), None)}


@safe
def vpn(action):
    """VPN. action: status, connect_proton, disconnect, open_school_login (opens the UWaterloo login window; Jarvis never handles its credentials), killswitch_on, killswitch_off."""
    action = _choice(action, ["status", "connect_proton", "disconnect", "open_school_login",
                              "killswitch_on", "killswitch_off"], "action")
    if action == "status":
        return {"ok": True, **_vpn_summary(_vpn_state())}
    if action in ("connect_proton", "disconnect"):
        # Through the HUD (VPN.qml runs stark-vpn detached and shows progress), so this
        # returns at once instead of blocking ~10 s; stark-vpn directly if the HUD is down.
        on = action == "connect_proton"
        r = _do("connect Proton VPN" if on else "disconnect VPN",
                _qs("vpn", "connect", "proton") if on else _qs("vpn", "disconnect"),
                "Proton connecting; the HUD shows when it's up" if on else "VPN disconnecting")
        if r["ok"]:
            return r
        return _do("", ["stark-vpn", "connect", "proton"] if on else ["stark-vpn", "disconnect"],
                   "Proton connected" if on else "VPN disconnected", timeout=45)
    if action == "open_school_login":
        st = _vpn_summary(_vpn_state())
        if st["active"] == "school" and st["state"] in ("connected", "connecting"):
            return {"ok": True, "result": f"school VPN already {st['state']}"}
        # toggle = the HUD's own path: opens the floating auth window
        return _do("open school VPN login", _qs("vpn", "toggle", "school"), "school VPN login window opened")
    on = action == "killswitch_on"
    return _do(f"Proton kill switch {'on' if on else 'off'}", ["stark-vpn", "killswitch", "on" if on else "off"],
               f"kill switch {'on' if on else 'off'}", timeout=15)


# ── UW CS servers ──────────────────────────────
def uwcs_hosts():
    """Host suffixes from ~/.ssh/config: '' (load-balanced) plus 002, 004, …"""
    hosts = set()
    for line in _read(HOME / ".ssh/config").splitlines():
        m = re.match(r"\s*Host\s+(.+)", line)
        if m:
            hosts |= {h[5:] for h in m.group(1).split() if re.fullmatch(r"uwcs-\d{3}", h)}
    return sorted(hosts)


@safe
def open_uwcs(host="", folder=""):
    """Open VS Code on the UWaterloo CS servers. host: "" (load-balanced) or a server number like 004; folder: optional path on the server, e.g. ~/cs136."""
    h = re.sub(r"^(uwcs-?|ubuntu2404-?)", "", str(host or "").strip().lower())
    if h:
        h = h.zfill(3) if h.isdigit() else h
        allowed = uwcs_hosts()
        if h not in allowed:
            raise Invalid(f"host must be one of: uwcs, {', '.join(allowed)}")
    folder = str(folder or "").strip()
    if folder and not re.fullmatch(r"~?[\w./-]{1,120}", folder) or ".." in folder:
        raise Invalid("folder must be a plain path like ~/cs136")
    # fish single quotes keep ~ for the server to expand (the regex rules out quotes)
    inner = "uwcs" + (f" '{h}'" if h or folder else "") + (f" '{folder}'" if folder else "")
    cmd = "fish -c " + shlex.quote(inner)
    where = f"uwcs-{h}" if h else "uwcs"
    return _do(f"VS Code on {where} {folder}".strip(), _hypr_exec(cmd), f"opening VS Code on {where}")


# ── lock / power ───────────────────────────────
@safe
def lock_screen():
    """Lock the screen."""
    return _do("lock screen", _qs("stark", "lock"), "locked")


POWER = {"suspend": "suspend the system", "shutdown": "shut down", "reboot": "restart", "logout": "log you out"}


@safe
def power(action):
    """Power. action: suspend, shutdown, reboot, logout. Always needs confirmation."""
    action = _choice(action, list(POWER), "action")
    if action == "suspend":
        return _do("suspend", ["stark-govee", "suspend"], "suspending", timeout=15)  # same as the power menu
    return _do(action, _qs("stark", "power", action), f"{action} started")


# ── timers / reminders ─────────────────────────
@safe
def set_timer(minutes, label="", screen="", position=""):
    """Start a timer. It shows as a countdown widget (on `screen`, default: where the cursor is)
    and rings, flashes the lights and speaks when done. Without the HUD it's a spoken timer.
    minutes: 0.1-1440; label optional."""
    try:
        m = float(minutes)
    except (TypeError, ValueError):
        raise Invalid("minutes must be a number")
    if not 0.1 <= m <= 1440:
        raise Invalid("minutes must be from 0.1 to 1440")
    label = " ".join(str(label or "").split())[:32]
    if screen or position or widget_types():
        r = widget_add("timer", screen=screen, position=position, label=label, seconds=round(m * 60))
        if r.get("ok"):
            r["ends"] = datetime.fromtimestamp(time.time() + m * 60).strftime("%H:%M:%S")
        return r
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"timer {m:g} min {label}".strip()}
    rid = db.add_reminder(time.time() + m * 60, label or "timer", "timer")
    return {"ok": True, "id": rid, "ends": datetime.fromtimestamp(time.time() + m * 60).strftime("%H:%M:%S")}


def parse_when(when, now=None):
    """'HH:MM' (24 h, or with am/pm) → next such time; ISO 'YYYY-MM-DDTHH:MM' → that time."""
    now = now or datetime.now()
    w = str(when or "").strip().lower().replace(".", "")
    try:
        t = datetime.fromisoformat(w.upper().replace(" ", "T")) if re.match(r"\d{4}-\d\d-\d\d", w) else None
    except ValueError:
        t = None
    if t is None:
        m = re.fullmatch(r"(\d{1,2})(?::(\d\d))?\s*(am|pm)?", w)
        if not m:
            raise Invalid("when must be HH:MM, h:mm am/pm, or YYYY-MM-DDTHH:MM (local time)")
        h, mi, ap = int(m.group(1)), int(m.group(2) or 0), m.group(3)
        if ap:
            if not 1 <= h <= 12:
                raise Invalid("hour must be 1-12 with am/pm")
            h = h % 12 + (12 if ap == "pm" else 0)
        if h > 23 or mi > 59:
            raise Invalid("not a valid time")
        t = now.replace(hour=h, minute=mi, second=0, microsecond=0)
        if t <= now:
            t += timedelta(days=1)
    if t <= now:
        raise Invalid("that time has already passed")
    if t - now > timedelta(days=60):
        raise Invalid("reminders can be at most 60 days ahead")
    return t


@safe
def set_reminder(when, text):
    """Reminder at a local time. when: HH:MM, h:mm am/pm, or YYYY-MM-DDTHH:MM; text: what to remind about."""
    t = parse_when(when)
    text = " ".join(str(text or "").split())[:160]
    if not text:
        raise Invalid("text is required")
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"reminder {t:%a %H:%M}: {text}"}
    rid = db.add_reminder(t.timestamp(), text, "reminder")
    return {"ok": True, "id": rid, "at": t.strftime("%a %d %b %H:%M")}


@safe
def list_reminders():
    """Pending timers (including countdown widgets) and reminders (id, kind, text, due time)."""
    now = time.time()
    items = [{"id": r["id"], "kind": r["kind"], "text": r["text"],
              "due": datetime.fromtimestamp(r["due"]).strftime("%a %H:%M:%S"),
              "minutes_left": round((r["due"] - now) / 60, 1)} for r in db.pending_reminders()]
    for w in _widget_list():
        if w["type"] == "timer" and not w.get("done"):
            items.append({"id": w["id"], "kind": "timer", "text": w.get("label") or "timer", "screen": w["screen"],
                          "due": datetime.fromtimestamp(now + w["seconds_left"]).strftime("%a %H:%M:%S"),
                          "minutes_left": round(w["seconds_left"] / 60, 1)})
    items.sort(key=lambda i: i["minutes_left"])
    return {"ok": True, "items": items}


@safe
def cancel_reminder(id):
    """Cancel a pending timer/reminder by id (from list_reminders). Needs confirmation."""
    rid = _int(id, 1, 10**9, "id")
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"cancel reminder {rid}"}
    r = db.cancel_reminder(rid)
    return {"ok": True, "cancelled": r["text"]}


# ── memory ─────────────────────────────────────
@safe
def remember(fact):
    """Store a fact Trevor explicitly asked you to remember."""
    fact = str(fact or "").strip()
    if len(fact) < 3:
        raise Invalid("fact is too short")
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"remember: {fact}"}
    return {"ok": True, "stored": db.remember(fact)}


@safe
def recall(query=""):
    """Search remembered facts (empty query = list all). Returns ids for forget."""
    q = str(query or "").strip()
    facts = db.recall(q, limit=8) if q else db.all_facts()[-30:]
    return {"ok": True, "facts": facts}


@safe
def forget(fact_id):
    """Delete one remembered fact by id (from recall). Needs confirmation."""
    fid = _int(fact_id, 1, 10**9, "fact_id")
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"forget fact {fid}"}
    return {"ok": True, "forgot": db.forget(fid)}


def fact_text(fact_id):
    try:
        return next((f["fact"] for f in db.all_facts() if f["id"] == int(fact_id)), None)
    except (TypeError, ValueError):
        return None


# ── browser ────────────────────────────────────
@safe
def open_in_browser(query):
    """Open claude.ai in the browser with a question. ONLY when Trevor explicitly says to open it in the browser."""
    q = " ".join(str(query or "").split())[:2000]
    url = f"{CLAUDE_URL}?q={urllib.parse.quote(q)}" if q else CLAUDE_URL
    return _do(f"browser: {url[:80]}", _hypr_exec(f"zen-browser --new-window {shlex.quote(url)}"), "opened in the browser")


# ── desktop widgets (quickshell/Widgets.qml, through `qs ipc call widgets …`) ──
WIDGET_POSITIONS = ["top-left", "top", "top-right", "left", "center", "right", "bottom-left", "bottom", "bottom-right"]
WIDGET_ROLES = {"main": "main monitor", "diag": "second monitor", "media": "laptop screen"}
WIDGET_SIZES = {"small": "small", "smaller": "smaller", "tiny": "small", "little": "small", "normal": "normal",
                "medium": "normal", "regular": "normal", "default": "normal", "large": "large", "big": "large",
                "bigger": "bigger", "larger": "bigger", "huge": "huge", "giant": "huge", "massive": "huge",
                "full": "huge", "full screen": "huge", "fullscreen": "huge", "dashboard": "huge", "max": "huge"}


def norm_size(spoken):
    t = _norm(spoken or "")
    return WIDGET_SIZES.get(t) if t else ""
# Spoken screen names → Roles roles. Undocked, the HUD shows everything on the laptop.
SCREEN_WORDS = [
    (r"(?:main|primary|first|left) (?:monitor|screen|display)|monitor (?:1|one)|screen (?:1|one)|main", "main"),
    (r"(?:second|middle|diagnostics?|diag) (?:monitor|screen|display)|monitor (?:2|two)|screen (?:2|two)|diagnostics|diag", "diag"),
    (r"laptop(?: screen| display)?|(?:built in|internal) (?:screen|display)|media(?: screen)?", "media"),
    (r"(?:this|current) (?:monitor|screen|display)|here|current", ""),
]
CITY_TZ = {"new york": "America/New_York", "nyc": "America/New_York", "toronto": "America/Toronto",
           "waterloo": "America/Toronto", "vancouver": "America/Vancouver", "los angeles": "America/Los_Angeles",
           "la": "America/Los_Angeles", "san francisco": "America/Los_Angeles", "seattle": "America/Los_Angeles",
           "chicago": "America/Chicago", "denver": "America/Denver", "london": "Europe/London",
           "paris": "Europe/Paris", "berlin": "Europe/Berlin", "tokyo": "Asia/Tokyo", "sydney": "Australia/Sydney",
           "beijing": "Asia/Shanghai", "shanghai": "Asia/Shanghai", "hong kong": "Asia/Hong_Kong",
           "singapore": "Asia/Singapore", "dubai": "Asia/Dubai", "mumbai": "Asia/Kolkata", "delhi": "Asia/Kolkata",
           "india": "Asia/Kolkata", "utc": "UTC", "gmt": "UTC", "seoul": "Asia/Seoul", "moscow": "Europe/Moscow"}
_WTYPES = (0.0, [])


def norm_screen(spoken):
    """'monitor 2' / 'the laptop screen' / 'diag' / '' → 'main' | 'diag' | 'media' | '' (current); None if unknown."""
    t = _norm(spoken or "")
    t = re.sub(r"^(?:the|my|on|to)\s+", "", t)
    if t in ("", "-"):
        return ""
    for pat, role in SCREEN_WORDS:
        if re.fullmatch(pat, t):
            return role
    return None


def norm_position(spoken):
    t = _norm(spoken or "").replace("centre", "center").replace("middle", "center").replace("upper", "top").replace("lower", "bottom")
    t = re.sub(r"^(?:the|at|in|to)\s+", "", t)
    t = re.sub(r"\s+(?:corner|side|of the screen|edge)$", "", t).replace(" ", "-")
    t = re.sub(r"^(top|bottom)-center$", r"\1", t)
    t = re.sub(r"^center-(left|right)$|^(left|right)-center$", lambda m: m.group(1) or m.group(2), t)
    t = re.sub(r"^(left|right)-(top|bottom)$", r"\2-\1", t)
    return t if t in WIDGET_POSITIONS else None


def city_tz(place):
    """'New York' → 'America/New_York'; also takes IANA names. None if unknown."""
    p = " ".join(str(place or "").split())
    if not p:
        return None
    if p.lower() in CITY_TZ:
        return CITY_TZ[p.lower()]
    if re.fullmatch(r"[A-Za-z_]+(/[A-Za-z0-9_+-]+){1,2}", p) and Path("/usr/share/zoneinfo", p).is_file():
        return p
    under = p.title().replace(" ", "_")
    hits = sorted(glob.glob(f"/usr/share/zoneinfo/*/{under}")) + sorted(glob.glob(f"/usr/share/zoneinfo/*/*/{under}"))
    hits = [h for h in hits if "/posix/" not in h and "/right/" not in h]
    return hits[0].split("zoneinfo/", 1)[1] if hits else None


def _ipc_widgets(*args):
    rc, out, err = _run(_qs("widgets", *args), timeout=4)
    if rc != 0:
        raise Invalid("the HUD isn't answering (widgets need Quickshell running)")
    try:
        return json.loads(out)
    except ValueError:
        raise Invalid(f"unexpected reply from the HUD: {out[:120]}")


def widget_types():
    """Widget types the HUD has (widgets/*.qml), cached; [] if the HUD isn't running."""
    global _WTYPES
    if time.monotonic() - _WTYPES[0] < 30 and _WTYPES[1]:
        return _WTYPES[1]
    try:
        types = _ipc_widgets("types").get("types") or []
    except Invalid:
        types = []
    _WTYPES = (time.monotonic(), types)
    return types


def _widget_list():
    try:
        return _ipc_widgets("list").get("widgets") or []
    except Invalid:
        return []


def _check_screen(screen):
    role = norm_screen(screen)
    if role is None:
        raise Invalid(f'unknown screen "{screen}" (main monitor, second monitor, laptop screen, or empty for the current one)')
    return role or "current"


def _check_position(position):
    if not position:
        return "-"
    pos = norm_position(position)
    if pos is None:
        raise Invalid(f'unknown position "{position}" ({", ".join(WIDGET_POSITIONS)})')
    return pos


@safe
def widget_add(type, screen="", position="", label="", minutes=0, seconds=0, tz="", analog=False, text="", pinned=False,
               size=""):
    """Show a desktop widget. type: clock | timer | stopwatch | media | stats | note (see widget_types()).
    screen: main monitor / second monitor / laptop screen, empty = the one in use. position: top-left …
    bottom-right, empty = the type's default. clock: tz (city or IANA zone), analog. timer: minutes/seconds.
    note: text. pinned: stays above windows. size: small | normal | large | huge (stats becomes a dashboard)."""
    t = str(type or "").lower().strip()
    types = widget_types()
    if t not in (types or ["clock", "timer", "stopwatch", "media", "stats", "note"]):
        raise Invalid(f'unknown widget type "{type}" ({", ".join(types)})')
    role, pos = _check_screen(screen), _check_position(position)
    params = {}
    label = " ".join(str(label or "").split())[:32]
    if label:
        params["label"] = label
    if t == "clock":
        if tz:
            zone = city_tz(tz)
            if not zone:
                raise Invalid(f'unknown time zone or city "{tz}"')
            params["tz"] = zone
            params.setdefault("label", str(tz).title() if "/" not in str(tz) else zone.split("/")[-1].replace("_", " "))
        params["analog"] = bool(analog)
    if t == "timer":
        try:
            secs = float(minutes or 0) * 60 + float(seconds or 0)
        except (TypeError, ValueError):
            raise Invalid("minutes / seconds must be numbers")
        if not 1 <= secs <= 86400:
            raise Invalid("a timer runs from 1 second to 24 hours")
        params["seconds"] = round(secs)
    if t == "note":
        params["text"] = str(text or "")[:600]
    if pinned:
        params["pinned"] = True
    if size:
        sz = norm_size(size)
        if sz is None or sz in ("bigger", "smaller"):
            raise Invalid(f'unknown size "{size}" (small, normal, large, huge)')
        params["size"] = sz
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"widget {t} on {role} at {pos} {params}"}
    return _ipc_widgets("add", t, role, pos, json.dumps(params))


def _widget_targets(target, screen=""):
    """'clock' / 'timer4' / 'all' (+ screen) → the matching widgets."""
    t = _norm(target or "").replace("widgets", "all").replace("widget", "").strip() or "all"
    t = {"music": "media", "now playing": "media", "player": "media", "system": "stats", "stat": "stats",
         "countdown": "timer", "timers": "timer", "clocks": "clock", "notes": "note", "sticky note": "note",
         "everything": "all"}.get(t, t)
    role = _check_screen(screen) if screen else ""
    items = _widget_list()
    if role == "current":
        try:
            role = _ipc_widgets("list").get("current", "")
        except Invalid:
            role = ""
    hits = [w for w in items if (w["id"] == t or t == "all" or w["type"] == t) and (not role or w["screen"] == role)]
    return hits


@safe
def widget_remove(target, screen=""):
    """Close desktop widgets. target: a widget id, a type (clock, timer…), or "all"; screen narrows it.
    Removing a note needs Trevor's yes (its text is lost)."""
    hits = _widget_targets(target, screen)
    if not hits:
        raise Invalid(f"no {target} widget" + (f" on the {screen}" if screen else "") + " is showing")
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": "remove " + ", ".join(w["id"] for w in hits)}
    for w in hits:
        _ipc_widgets("remove", w["id"])
    return {"ok": True, "removed": [w["id"] for w in hits], "types": sorted({w["type"] for w in hits})}


@safe
def widget_move(target, screen="", position="", pinned=None, size=""):
    """Move a desktop widget (the newest match) to another screen and/or position; pinned true/false
    puts it above windows or back behind them; size small | normal | large | huge | bigger | smaller."""
    hits = _widget_targets(target)
    if not hits:
        raise Invalid(f"no {target} widget is showing")
    w = hits[-1]
    role = _check_screen(screen) if screen else "-"
    pos = _check_position(position)
    sz = norm_size(size) if size else ""
    if sz is None:
        raise Invalid(f'unknown size "{size}" (small, normal, large, huge, bigger, smaller)')
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"move {w['id']} to {role} {pos} pinned={pinned} size={sz}"}
    r = _ipc_widgets("move", w["id"], role, pos) if (role != "-" or pos != "-") else {"ok": True, "id": w["id"]}
    if r.get("ok") and pinned is not None:
        _ipc_widgets("pin", w["id"], "true" if pinned else "false")
        r["pinned"] = bool(pinned)
    if r.get("ok") and sz:
        rs = _ipc_widgets("resize", w["id"], sz)
        if not rs.get("ok"):
            return rs
        r["size"] = rs.get("size")
    return r


@safe
def widget_list():
    """Desktop widgets showing now: id, type, screen (main / diag / media), position, label, timer time left."""
    try:
        d = _ipc_widgets("list")
    except Invalid as e:
        raise e
    return {"ok": True, "docked": d.get("docked"), "current_screen": d.get("current"), "widgets": d.get("widgets", [])}


def widget_note_count(target, screen=""):
    try:
        return sum(1 for w in _widget_targets(target, screen) if w["type"] == "note")
    except Invalid:
        return 0


# ── what each screen's HUD shows (quickshell/Roles.qml, through `qs ipc call roles …`) ──
# Not widgets: a whole screen's panel (arc-reactor clock / diagnostics wall / audio deck /
# nothing), saved per monitor. Never moves workspaces.
SCREEN_ROLES = ["auto", "clock", "stats", "music", "none"]
ROLE_WORDS = [   # spoken → role; fullmatch on the normalized phrase
    (r"(?:the )?(?:arc )?(?:reactor|clock|time)(?: panel| hud| view)?", "clock"),
    (r"(?:the )?(?:system )?(?:stats|statistics|diagnostics|diag|telemetry)(?: wall| panel| hud| view)?", "stats"),
    (r"(?:the )?(?:music|media|audio|now playing|visualizer|visualiser|player|spotify)(?: deck| panel| hud| view)?", "music"),
    (r"nothing|none|blank|empty|(?:just )?(?:the )?grid|no panel|off", "none"),
    (r"auto|automatic|default|normal", "auto"),
]
# Spoken screen → the HUD's target token. "TV" = any screen that isn't a Dell / Acer / the laptop
ROLE_SCREENS = [
    (r"(?:the |my )?(?:tv|t v|television|telly)(?: screen)?", "tv"),
    (r"(?:the |my )?(?:laptop(?: screen| display)?|(?:built in|internal) (?:screen|display))", "laptop"),
    (r"(?:the |my )?(?:monitor|screen|display) (?:1|one)", "monitor 1"),
    (r"(?:the |my )?(?:monitor|screen|display) (?:2|two)", "monitor 2"),
    (r"(?:the |my )?(?:monitor|screen|display) (?:3|three)", "monitor 3"),
    (r"(?:the |my )?(?:main|primary|first|left)(?: (?:monitor|screen|display))?", "main"),
    (r"(?:the |my )?(?:second|middle|diagnostics?)(?: (?:monitor|screen|display))?", "diag"),
    (r"(?:this|current|the current)(?: (?:monitor|screen|display))?|this one|here", "current"),
]


def norm_role(spoken):
    """'the music deck' → 'music'; None if it isn't a role."""
    t = _norm(spoken or "")
    t = re.sub(r"^(?:a|an|my)\s+", "", t)
    for pat, role in ROLE_WORDS:
        if re.fullmatch(pat, t):
            return role
    return t if t in SCREEN_ROLES else None


def norm_role_screen(spoken):
    """'the TV' / 'monitor 2' / 'laptop screen' / '' → HUD target token ('' = the focused one); None if unknown."""
    t = _norm(spoken or "")
    t = re.sub(r"^(?:on|to|for)\s+", "", t)
    if t in ("", "-"):
        return "current"
    for pat, token in ROLE_SCREENS:
        if re.fullmatch(pat, t):
            return token
    return None


@safe
def set_screen_role(screen, role):
    """Choose what a screen's HUD shows: clock (arc reactor) | stats (diagnostics) | music (audio deck +
    visualizer) | none (grid only) | auto (by position). screen: "TV" | "laptop screen" | "monitor 2" |
    "main monitor" | "second monitor" | "" (the one in use). Saved per monitor; workspaces don't move."""
    r = norm_role(role)
    if r is None:
        raise Invalid(f"role must be one of: {', '.join(SCREEN_ROLES)}")
    s = norm_role_screen(screen)
    if s is None:
        raise Invalid(f'unknown screen "{screen}" (TV, laptop screen, monitor 1/2, main / second monitor, or empty for this one)')
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"roles set {s} {r}"}
    rc, out, err = _run(_qs("roles", "set", s, r), timeout=4)
    if rc != 0:
        raise Invalid("the HUD isn't answering (screen roles need Quickshell running)")
    try:
        d = json.loads(out)
    except ValueError:
        raise Invalid(f"unexpected reply from the HUD: {out[:120]}")
    if not d.get("ok"):
        raise Invalid(d.get("error") or "the HUD refused")
    return {"ok": True, "role": r, "screens": [x.get("name") for x in d.get("set", [])]}


# ── weather (Open-Meteo: no key, no account; read-only) ──
HUD_SETTINGS = HOME / ".config/quickshell/settings.json"
DEFAULT_PLACE = "Waterloo, Ontario"
WMO = {0: "clear", 1: "mostly clear", 2: "partly cloudy", 3: "overcast", 45: "foggy", 48: "foggy",
       51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 56: "freezing drizzle", 57: "freezing drizzle",
       61: "light rain", 63: "rain", 65: "heavy rain", 66: "freezing rain", 67: "freezing rain",
       71: "light snow", 73: "snow", 75: "heavy snow", 77: "snow grains", 80: "light showers", 81: "showers",
       82: "heavy showers", 85: "snow showers", 86: "heavy snow showers", 95: "thunderstorms",
       96: "thunderstorms with hail", 99: "thunderstorms with hail"}
_places = {}


def _get_json(url, timeout=4):
    req = urllib.request.Request(url, headers={"User-Agent": "stark-jarvis/2"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read(200_000))


def home_place():
    """Settings → jarvisPlace, else Waterloo."""
    try:
        return str(json.loads(HUD_SETTINGS.read_text()).get("jarvisPlace") or DEFAULT_PLACE)
    except (OSError, ValueError):
        return DEFAULT_PLACE


@safe
def weather(place=""):
    """Current weather plus today's and tomorrow's forecast, for a place (default: home)."""
    place = " ".join(str(place or "").split()) or home_place()
    if len(place) > 60 or not re.fullmatch(r"[\w .,'-]+", place):
        raise Invalid("place must be a town or city name")
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"weather for {place}"}
    key = place.lower()
    if key not in _places:
        name, _, region = place.partition(",")
        g = _get_json("https://geocoding-api.open-meteo.com/v1/search?count=5&language=en&name="
                      + urllib.parse.quote(name.strip()))
        hits = g.get("results") or []
        if region.strip():
            r = region.strip().lower()
            hits = [h for h in hits if r in " ".join(str(h.get(k, "")) for k in ("admin1", "country", "country_code")).lower()] or hits
        if not hits:
            raise Invalid(f'no place called "{place}"')
        h = hits[0]
        _places[key] = (h["latitude"], h["longitude"], h["name"])
    lat, lon, name = _places[key]
    w = _get_json(f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&timezone=auto&forecast_days=2"
                  "&current=temperature_2m,apparent_temperature,weather_code,wind_speed_10m"
                  "&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code")
    c, d = w["current"], w["daily"]
    day = lambda i: {"high_c": round(d["temperature_2m_max"][i]), "low_c": round(d["temperature_2m_min"][i]),
                     "sky": WMO.get(d["weather_code"][i], "mixed"), "rain_chance_pct": d["precipitation_probability_max"][i]}
    return {"ok": True, "place": name, "now": {"temp_c": round(c["temperature_2m"]),
            "feels_like_c": round(c["apparent_temperature"]), "sky": WMO.get(c["weather_code"], "mixed"),
            "wind_kmh": round(c["wind_speed_10m"])}, "today": day(0), "tomorrow": day(1)}


# ── Jarvis's own voice volume (Settings → JARVIS → VOICE VOLUME) ──
VOICE_STEP = 15


def _hud_settings():
    try:
        return json.loads(HUD_SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def _write_hud_setting(key, value):
    """One key in quickshell/settings.json, written atomically. The HUD (FileView watchChanges)
    reloads it, and Jarvis's Config re-reads it by mtime, so the next sentence is at the new level."""
    data = _hud_settings()
    data[key] = value
    tmp = HUD_SETTINGS.with_suffix(".jarvis.tmp")
    tmp.write_text(json.dumps(data, indent=4, ensure_ascii=False) + "\n")
    tmp.replace(HUD_SETTINGS)


def _speaker_in_use(mac):
    """Jarvis is talking through the Bluetooth speaker: it's connected and the default output isn't
    headphones (the same rule as core/voice.py Speaker.wanted + core/effects.on_headphones)."""
    if not mac:
        return False
    rc, out, _ = _run(["pactl", "-f", "json", "list", "sinks"], timeout=3)
    rc2, default, _ = _run(["pactl", "get-default-sink"], timeout=3)
    try:
        sinks = json.loads(out) if rc == 0 else []
    except ValueError:
        return False
    if not any(s.get("name", "").startswith("bluez_output." + mac.replace(":", "_")) for s in sinks):
        return False
    for s in sinks:
        if s.get("name") == default:
            p = s.get("properties", {})
            hints = " ".join(str(x) for x in (p.get("device.form_factor"), p.get("device.icon_name"), s.get("active_port")))
            return not (re.search(r"head(phone|set)", hints, re.I) or p.get("device.bus") == "usb")
    return True


@safe
def jarvis_volume(action, percent=0):
    """Jarvis's own speaking volume (not the music). action: up | down (one step) | set (percent 0-100).
    Changes the Bluetooth speaker's own level instead when that's what Jarvis is playing on and it
    has a separate level."""
    action = _choice(action, ["up", "down", "set"], "action")
    cfg = _hud_settings()
    key = "jarvisVoiceVolume"
    try:
        if int(cfg.get("jarvisSpeakerVolume", -1)) >= 0 and _speaker_in_use(str(cfg.get("jarvisSpeaker") or "")):
            key = "jarvisSpeakerVolume"
        now = int(round(float(cfg.get(key, 60))))
    except (TypeError, ValueError):
        now = 60
    if action == "set":
        new = _int(str(percent).rstrip("%"), 0, 100, "percent")
    elif action == "up":
        new = min(100, now + VOICE_STEP)
    else:
        new = max(10, now - VOICE_STEP)          # a step down never makes him inaudible
    where = "Bluetooth speaker" if key == "jarvisSpeakerVolume" else "voice"
    if DRY_RUN:
        return {"ok": True, "dry_run": True, "would": f"Jarvis {where} volume {now}% → {new}%", "percent": new, "was": now}
    if new != now or key not in cfg:
        _write_hud_setting(key, new)
    return {"ok": True, "percent": new, "was": now, "where": where,
            **({"note": "already at the limit"} if new == now and action != "set" else {})}


# ── background tasks (run by the voice process, core/tasks.py) ──
MAX_QUEUED_TASKS = 4


def start_task(title, instructions):
    """Queue a long, multi-step job. Jarvis's task runner picks it up (at most two at once), runs it
    with its own Claude session behind the same confirmations, and announces the result."""
    title = " ".join(str(title or "").split())[:80]
    instructions = str(instructions or "").strip()[:4000]
    if not title or not instructions:
        return {"ok": False, "error": "a task needs a short title and instructions"}
    if len(db.list_tasks(status="queued")) >= MAX_QUEUED_TASKS:
        return {"ok": False, "error": "too many tasks already waiting", "say": "I've a queue of tasks already, sir."}
    if DRY_RUN:
        return {"ok": True, "would": f"queue task {title!r}"}
    tid = db.add_task(title, instructions)
    return {"ok": True, "task": tid, "say": "I've started on that in the background, sir. I'll let you know when it's done."}


# ── registry, confirmation policy, HUD labels ──
TOOLS = {f.__name__: f for f in [
    open_app, close_focused_window, switch_workspace, move_window_to_workspace, set_theme, lights,
    media, what_is_playing, system_status, vpn, open_uwcs, lock_screen, power,
    set_timer, set_reminder, list_reminders, cancel_reminder, remember, recall, forget, open_in_browser, weather,
    widget_add, widget_remove, widget_move, widget_list, set_screen_role, jarvis_volume, start_task,
]}


def confirmation_prompt(tool, args):
    """Spoken question if this call needs Trevor's "yes" first, else None.

    Enforced by Jarvis itself (not the model): power, closing windows, deleting
    anything, the Proton kill switch.
    """
    a = args or {}
    if tool == "power":
        what = POWER.get(str(a.get("action", "")).lower())
        return f"Shall I {what}, sir?" if what else None   # invalid action fails validation anyway
    if tool == "close_focused_window":
        return f"Close {focused_window_name()}, sir?"
    if tool == "forget":
        f = fact_text(a.get("fact_id"))
        return f"Forget that {f.rstrip('.!')}, sir?" if f else "Forget that, sir?"
    if tool == "cancel_reminder":
        return "Cancel that reminder, sir?"
    if tool == "widget_remove":
        n = widget_note_count(a.get("target", ""), a.get("screen", ""))
        if n:
            return ("Remove that note, sir? Its text will be lost." if n == 1
                    else f"That closes {n} notes, sir, and their text is lost. Go ahead?")
    if tool == "vpn" and str(a.get("action", "")).lower() == "killswitch_on":
        return "Turn on the Proton kill switch, sir? It cuts the internet if the tunnel drops."
    return None


def tool_label(tool, args):
    """HUD line for a running tool, e.g. 'THEME → MARK III'."""
    a = args or {}
    v = lambda k: str(a.get(k, "")).replace("_", " ").upper()
    labels = {
        "open_app": lambda: f"OPEN → {v('name')}",
        "close_focused_window": lambda: "WINDOW → CLOSE",
        "switch_workspace": lambda: f"WORKSPACE → {v('n')}",
        "move_window_to_workspace": lambda: f"MOVE → WS {v('n')}",
        "set_theme": lambda: f"THEME → {match_preset(str(a.get('preset', ''))) or v('preset')}",
        "lights": lambda: f"LIGHTS → {v('action')} {v('value')}".strip(),
        "media": lambda: f"MEDIA → {v('action')} {v('value')}".strip(),
        "what_is_playing": lambda: "MEDIA → NOW PLAYING",
        "system_status": lambda: "SYSTEM → STATUS",
        "vpn": lambda: {"CONNECT PROTON": "VPN → PROTON", "OPEN SCHOOL LOGIN": "VPN → SCHOOL"}.get(v("action"), f"VPN → {v('action')}"),
        "open_uwcs": lambda: f"UW CS → {v('host') or 'UWCS'}",
        "lock_screen": lambda: "SYSTEM → LOCK",
        "power": lambda: f"POWER → {v('action')}",
        "set_timer": lambda: f"TIMER → {v('minutes')} MIN",
        "set_reminder": lambda: f"REMINDER → {v('when')}",
        "list_reminders": lambda: "REMINDERS → LIST",
        "cancel_reminder": lambda: "REMINDER → CANCEL",
        "remember": lambda: "MEMORY → STORE",
        "recall": lambda: "MEMORY → RECALL",
        "forget": lambda: "MEMORY → FORGET",
        "open_in_browser": lambda: "BROWSER → CLAUDE",
        "weather": lambda: f"WEATHER → {v('place') or 'HOME'}",
        "widget_add": lambda: f"WIDGET → {v('type')}" + (f" · {v('tz') or v('label')}" if a.get("tz") or a.get("label") else "")
                              + (f" @ {(WIDGET_ROLES.get(norm_screen(a.get('screen')) or '', '') or 'HERE').upper()}"),
        "widget_remove": lambda: f"WIDGET ✕ {v('target') or 'ALL'}" + (f" @ {v('screen')}" if a.get("screen") else ""),
        "widget_move": lambda: f"WIDGET → {v('target')} ⇢ {v('position') or v('screen') or v('size') or ('PIN' if a.get('pinned') else 'UNPIN' if a.get('pinned') is False else '')}".rstrip(" ⇢"),
        "widget_list": lambda: "WIDGETS → LIST",
        "set_screen_role": lambda: f"SCREEN → {(norm_role_screen(a.get('screen')) or v('screen')).upper()} ⇢ {(norm_role(a.get('role')) or v('role')).upper()}",
        "jarvis_volume": lambda: f"VOICE → {v('percent') + '%' if a.get('action') == 'set' else v('action')}",
        "start_task": lambda: f"TASK → {v('title')}",
    }
    try:
        return labels[tool]()
    except Exception:
        return tool.replace("_", " ").upper()
