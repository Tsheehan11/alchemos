"""
Window reading for Jarvis: find the ONE window (or monitor) Trevor named, refuse the ones that are never
captured, get its text if the app will give it, else its pixels, all in memory.

  resolve(target)       "this window" / "" → the focused window; "the Discord window" → class / title match;
                        "monitor 2" / "laptop" / "left screen" / "DP-5" → a monitor. Ambiguous → an error
                        listing the candidates (Jarvis asks which one), never a guess at a different window.
  excluded(win, cfg)    the lock screen (hyprlock up → nothing is captured at all), polkit / password /
                        keyring dialogs, password managers, and any title or class matching the blocklist
                        (Settings → JARVIS, jarvisCaptureBlocklist). Checked again on every capture.
  capture(target)       pixels: Hyprland's toplevel export for a window (works while it's covered or on
                        another workspace), else grim on its visible geometry; grim -o for a monitor, with
                        every excluded window on it blacked out. grim writes to a pipe, never a file.
  read_text(win)        kitty's own text (kitty @ get-text, if that kitty listens on a socket), then
                        AT-SPI (mcp/atspi_text.py, system python), else None.
  png / thumb / Grid    PNG bytes for Claude, and the local change detector the watchers use.

Nothing here writes a capture to disk; nothing here acts on what it reads (screen text is data).
"""
import json
import os
import re
import stat
import subprocess
import time
import zlib
from pathlib import Path

import numpy as np

from . import config as C
from . import wlcap

HERE = Path(__file__).resolve().parent.parent
ATSPI = HERE / "mcp" / "atspi_text.py"

DEFAULT_BLOCKLIST = C.DEFAULTS["jarvisCaptureBlocklist"]
# never captured, whatever the blocklist says
HARD_CLASS = re.compile(r"polkit|pinentry|gcr-prompter|askpass|lxpolkit|hyprpolkit|kwallet|seahorse|keyring|"
                        r"keepass|bitwarden|1password|hyprlock|swaylock|gtklock", re.I)
HARD_TITLE = re.compile(r"authenticat(e|ion) (is )?required|\bpassword\b|passphrase|unlock (login )?keyring|"
                        r"\bsudo\b|\bpolkit\b|enter pin", re.I)
SELF_CLASS = re.compile(r"^(org\.quickshell|quickshell)$", re.I)     # the HUD itself


class ScreenError(Exception):
    """A spoken-friendly reason ("that window is on my never-read list, sir")."""


def _json(args, timeout=3):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if r.returncode != 0:
        raise ScreenError(f"{args[0]} failed")
    return json.loads(r.stdout or "null")


def clients():
    return [c for c in (_json(["hyprctl", "clients", "-j"]) or []) if c.get("mapped", True)]


def monitors():
    return _json(["hyprctl", "monitors", "-j"]) or []


def active_window():
    w = _json(["hyprctl", "activewindow", "-j"])
    return w if w and w.get("address") else None


def locked():
    """The session is locked (hyprlock up): nothing may be captured."""
    return subprocess.run(["pgrep", "-x", "hyprlock"], capture_output=True).returncode == 0


# The HUD's hotplug settle gate (quickshell/Hotplug.qml): while screens come or go, this flag is
# fresh (touched every 4 s; older than 10 s = stale). Windows can be left on no monitor at all
# then (hyprctl clients: "monitor": -1), and Hyprland 0.56.2 segfaults when one of those is
# captured through the toplevel export, so nothing is captured while it's up. 0.57.0 fixed the crash and re-homes
# those workspaces itself (nested repro 2026-11-02); the gate stays anyway.
SETTLE_FLAG = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "stark-hotplug-settling")


def settling():
    try:
        return time.time() - os.stat(SETTLE_FLAG).st_mtime < 10
    except OSError:
        return False


def hud_log(msg):
    """One line in the journal under the HUD's tag (journalctl --user -t stark-hud)."""
    try:
        subprocess.run(["logger", "-t", "stark-hud", msg[:900]], timeout=2)
    except Exception:
        pass


def blocklist(cfg=None):
    v = cfg["jarvisCaptureBlocklist"] if cfg is not None else None
    if isinstance(v, str):
        v = [x for x in re.split(r"[,\n]", v)]
    terms = [str(x).strip().lower() for x in (v if v is not None else DEFAULT_BLOCKLIST)]
    return [t for t in terms if t]


def excluded(win, cfg=None):
    """Why this window is never captured, or "" if it may be."""
    cls = f"{win.get('class', '')} {win.get('initialClass', '')}"
    title = f"{win.get('title', '')} {win.get('initialTitle', '')}"
    if HARD_CLASS.search(cls) or HARD_TITLE.search(title):
        return "it's a lock, password or permission prompt, which I never read"
    if SELF_CLASS.search(win.get("class", "")):
        return "that's my own display"
    hay = f"{cls} {title}".lower()
    for t in blocklist(cfg):
        if re.search(r"(?<![a-z0-9])" + re.escape(t) + r"(?![a-z0-9])", hay):
            return "its title is on your never-read list"
    return ""


APP_NAMES = {"zen": "Zen", "firefox": "Firefox", "kitty": "the terminal", "code": "VS Code", "discord": "Discord",
             "vesktop": "Discord", "spotify": "Spotify", "steam": "Steam", "obsidian": "Obsidian", "kate": "Kate",
             "org.gnome.nautilus": "Files", "thunar": "Files", "dolphin": "Files", "heroic": "Heroic"}


def app_name(win):
    c = (win.get("class") or "").strip()
    return APP_NAMES.get(c.lower()) or (c.rsplit(".", 1)[-1] if c else "the window")


def describe(win):
    """"Discord: #general" — the app's plain name, then the title."""
    t = (win.get("title") or "").strip()
    a = app_name(win)
    return f"{a}: {t[:60]}" if t else a


# ── naming a target ──
ORDINALS = {"first": 1, "one": 1, "second": 2, "two": 2, "third": 3, "three": 3, "fourth": 4, "four": 4}
THIS = re.compile(r"^(this|that|the|my|current|focused|active|front)?\s*(window|app|one|screen\s*window)?$", re.I)
APP_ALIASES = {"browser": ["zen", "firefox", "chromium", "chrome"], "terminal": ["kitty", "foot", "alacritty"],
               "music": ["spotify"], "editor": ["code", "kate"], "vs code": ["code"], "vscode": ["code"]}


def monitors_ordered():
    """Left to right (then top to bottom): "monitor 1" is the leftmost."""
    return sorted(monitors(), key=lambda m: (m["x"], m["y"]))


def _monitor_of(text):
    t = text.lower().strip()
    mons = monitors_ordered()
    m = re.search(r"\b(?:monitor|screen|display)\s*(?:number\s*)?(\d+|one|two|three|four)\b|"
                  r"\b(first|second|third|fourth)\s+(?:monitor|screen|display)\b", t)
    if m:
        n = m.group(1) or m.group(2)
        n = int(n) if n.isdigit() else ORDINALS[n]
        if not 1 <= n <= len(mons):
            raise ScreenError(f"there are only {len(mons)} monitors, sir")
        return mons[n - 1]
    for mon in mons:
        if mon["name"].lower() in t:
            return mon
    if re.search(r"\b(this|my|current|that)\s+(screen|monitor|display)\b", t):
        for mon in mons:
            if mon.get("focused"):
                return mon
    if re.search(r"\b(laptop|built.?in|internal)\b", t):
        for mon in mons:
            if mon["name"].startswith("eDP"):
                return mon
    side = re.search(r"\b(left|right|middle|centre|center)\s+(?:monitor|screen|display)\b", t)
    if side and mons:
        ext = [m for m in mons if not m["name"].startswith("eDP")] or mons
        return {"left": ext[0], "right": ext[-1]}.get(side.group(1), ext[len(ext) // 2])
    return None


def resolve(target, cfg=None):
    """→ ("window", client) | ("monitor", monitor). Raises ScreenError with a reason Jarvis can say."""
    if locked():
        raise ScreenError("the screen is locked, sir; I don't read anything while it is")
    text = re.sub(r"\s+", " ", (target or "").strip())
    t = re.sub(r"^(read|show me|what'?s on|look at)\s+", "", text.lower()).strip(" ?.!")
    mon = _monitor_of(t) if re.search(r"monitor|screen|display", t) and not re.search(r"\bwindow\b", t) else None
    if mon:
        return "monitor", mon
    if not t or THIS.match(t):
        w = active_window()
        if not w:
            raise ScreenError("no window has focus, sir")
        why = excluded(w, cfg)
        if why:
            raise ScreenError(f"I won't read that one, sir: {why}")
        return "window", w
    if t.startswith("0x"):
        cands = [c for c in clients() if c["address"] == t.split()[0]]
    else:
        name = re.sub(r"\b(the|my|window|app|application|tab|please)\b", " ", t)
        name = re.sub(r"\s+", " ", name).strip()
        if not name:
            raise ScreenError("which window, sir?")
        keys = APP_ALIASES.get(name, [name])
        cands = []
        for c in clients():
            hay_c = f"{c.get('class', '')} {c.get('initialClass', '')}".lower()
            hay_t = (c.get("title") or "").lower()
            if any(k in hay_c for k in keys) or any(k in hay_t for k in keys):
                cands.append(c)
    if not cands:
        raise ScreenError(f"I can't find a window matching \"{text}\", sir")
    allowed = [c for c in cands if not excluded(c, cfg)]
    if not allowed:
        raise ScreenError(f"I won't read that one, sir: {excluded(cands[0], cfg)}")
    if len(allowed) > 1:
        focused = active_window()
        hit = [c for c in allowed if focused and c["address"] == focused["address"]]
        if hit:
            return "window", hit[0]
        raise ScreenError("more than one window matches: " + "; ".join(describe(c) for c in allowed[:5]) + ". Which one, sir?")
    return "window", allowed[0]


def window_by_address(address):
    for c in clients():
        if c["address"] == address:
            return c
    return None


# ── pixels ──
def _ppm(data):
    """grim -t ppm output → H×W×3 array."""
    parts, i = [], 0
    while len(parts) < 4:
        while data[i:i + 1].isspace():
            i += 1
        if data[i:i + 1] == b"#":
            i = data.index(b"\n", i) + 1
            continue
        j = i
        while not data[j:j + 1].isspace():
            j += 1
        parts.append(data[i:j])
        i = j
    i += 1
    w, h = int(parts[1]), int(parts[2])
    return np.frombuffer(data, dtype=np.uint8, count=w * h * 3, offset=i).reshape(h, w, 3).copy()


def _grim(args):
    r = subprocess.run(["grim", "-t", "ppm", *args, "-"], capture_output=True, timeout=6)   # "-" = stdout, no file
    if r.returncode != 0:
        raise ScreenError("the screen capture failed, sir")
    return _ppm(r.stdout)


def ws_name(ws):
    """A workspace's key. Hyprland 0.57 gives special workspaces no id at all (only address / type / name), in
    clients, monitors and workspaces alike; names are unique ("1", "special:music"), so compare those."""
    ws = ws or {}
    return ws.get("name") or (str(ws["id"]) if "id" in ws else "")


def shown_on(mon):
    """Names of the workspaces a monitor shows: its active one, plus its special one if it's open."""
    return {n for n in (ws_name(mon.get("activeWorkspace")), ws_name(mon.get("specialWorkspace"))) if n}


def _visible(win):
    mons = {m["id"]: m for m in monitors()}
    m = mons.get(win.get("monitor"))
    if not m:
        return False
    return ws_name(win["workspace"]) in shown_on(m)


def capture_window(win, cfg=None):
    """→ (H×W×3 RGB, how). Re-checks the exclusions against the window as it is now."""
    if locked():
        raise ScreenError("the screen is locked, sir")
    now = window_by_address(win["address"])
    if not now:
        raise ScreenError("that window has closed, sir")
    why = excluded(now, cfg)
    if why:
        raise ScreenError(f"I won't read that one, sir: {why}")
    if settling():
        hud_log(f"jarvis: capture skipped for {now.get('class') or '?'} (workspace {now['workspace']['name']}): screens still settling")
        raise ScreenError("the screens are still changing, sir; give me a moment")
    if now.get("monitor", -1) not in {m["id"] for m in monitors()}:
        hud_log(f"jarvis: capture skipped for {now.get('class') or '?'} (workspace {now['workspace']['name']}): "
                f"on no monitor (monitor {now.get('monitor')})")
        raise ScreenError("that window is between screens right now, sir")
    try:
        return wlcap.capture_window(now["address"]), "export"
    except wlcap.CaptureError as e:
        export_err = str(e)
    if not _visible(now):
        raise ScreenError(f"I couldn't capture that window ({export_err}) and it isn't on screen, sir")
    (x, y), (w, h) = now["at"], now["size"]
    return _grim(["-g", f"{x},{y} {w}x{h}"]), "grim"


def capture_monitor(mon, cfg=None):
    """The monitor's picture with every never-read window on it blacked out."""
    if locked():
        raise ScreenError("the screen is locked, sir")
    if settling():
        hud_log(f"jarvis: capture skipped for monitor {mon['name']}: screens still settling")
        raise ScreenError("the screens are still changing, sir; give me a moment")
    img = _grim(["-o", mon["name"]])
    scale = mon.get("scale", 1) or 1
    lw, lh = mon["width"] / scale, mon["height"] / scale            # hyprctl sizes are pixels; window coords are logical
    if mon.get("transform", 0) % 2:
        lw, lh = lh, lw
    fx, fy = img.shape[1] / lw, img.shape[0] / lh
    shown = shown_on(mon)
    for c in clients():
        if ws_name(c["workspace"]) in shown and excluded(c, cfg):
            (x, y), (w, h) = c["at"], c["size"]
            x0, y0 = int((x - mon["x"]) * fx), int((y - mon["y"]) * fy)
            x1, y1 = int(x0 + w * fx + 1), int(y0 + h * fy + 1)
            img[max(0, y0):max(0, y1), max(0, x0):max(0, x1)] = 0
    return img, "grim"


def capture(kind, obj, cfg=None):
    return capture_window(obj, cfg) if kind == "window" else capture_monitor(obj, cfg)


# ── text ──
KITTY_SOCKET = "kitty-rc-{pid}"     # kitty.conf: listen_on unix:${XDG_RUNTIME_DIR}/kitty-rc-{kitty_pid}


def _kitty_socket(pid):
    """That kitty's remote-control socket, only if it is a real socket file in $XDG_RUNTIME_DIR (0700) owned by
    this user. Abstract sockets (@name) are never used: anyone on the machine could create or connect to one."""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return None
    run = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    path = os.path.join(run, KITTY_SOCKET.format(pid=pid))
    try:
        st = os.lstat(path)
    except OSError:
        return None
    if not stat.S_ISSOCK(st.st_mode) or st.st_uid != os.getuid():
        return None
    return "unix:" + path


def _kitty_public_key(pid):
    """kitty encrypts password requests with the target instance's public key, which it only hands to its
    child processes (KITTY_PUBLIC_KEY): read it from one of that kitty's children (same user, /proc)."""
    try:
        kids = " ".join(Path(f"/proc/{pid}/task/{t}/children").read_text() for t in os.listdir(f"/proc/{pid}/task")).split()
    except OSError:
        return None
    for c in kids:
        try:
            env = dict(x.split("=", 1) for x in Path(f"/proc/{c}/environ").read_bytes().decode(errors="replace").split("\0") if "=" in x)
        except OSError:
            continue
        if env.get("KITTY_PID") == str(pid) and env.get("KITTY_PUBLIC_KEY"):
            return env["KITTY_PUBLIC_KEY"]
    return None


def _kitty_password():
    from . import secrets
    return secrets.get("kitty", "rc_password")


def kitty_text(win):
    """The visible text of a kitty window, through its own remote control. kitty only lets the keyring password
    run get-text, over the socket (~/.config/kitty/jarvis-rc-check.py); the password goes in the environment,
    never on the command line."""
    sock = _kitty_socket(win.get("pid"))
    pw = _kitty_password() if sock else None
    key = _kitty_public_key(win.get("pid")) if pw else None
    if not sock or not pw or not key:
        return None
    env = {k: v for k, v in os.environ.items() if not k.startswith("KITTY_")}     # not the env of a kitty we run in
    env.update(KITTY_RC_PASSWORD=pw, KITTY_PUBLIC_KEY=key)
    try:
        r = subprocess.run(["kitty", "@", "--to", sock, "--password-env", "KITTY_RC_PASSWORD", "--use-password", "always",
                            "get-text", "--match", "state:focused_os_window and state:active", "--extent", "screen"],
                           capture_output=True, text=True, timeout=3, env=env)
        return r.stdout.rstrip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def kitty_rc_cli(argv):
    """jarvis kitty-rc [status | setup | rotate]: the keyring password kitty lets run get-text only.
    kitty reads it at start (kitty.conf → geninclude jarvis-rc-password.sh), so a rotation reaches each kitty
    when it reloads its config (a theme change does that) or restarts."""
    import secrets as pysecrets
    from . import secrets
    cmd = argv[0] if argv else "status"
    have = secrets.has("kitty", "rc_password")
    if cmd in ("setup", "rotate"):
        if have and cmd == "setup":
            print("kitty remote-control password: already in the keyring (jarvis:kitty / rc_password)")
            return 0
        secrets.store("kitty", "rc_password", pysecrets.token_urlsafe(32))
        print("kitty remote-control password " + ("rotated" if have else "stored") + " in the keyring. Running kittys pick it "
              "up when they reload their config (e.g. a theme change); new kittys straight away.")
        return 0
    if cmd != "status":
        print("usage: jarvis kitty-rc [status | setup | rotate]")
        return 2
    run = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    socks = sorted(f for f in os.listdir(run) if re.fullmatch(r"kitty-rc-\d+", f))
    live = [f for f in socks if Path(f"/proc/{f.rsplit('-', 1)[1]}").exists()]
    print(f"password in keyring: {'yes' if have else 'no (jarvis kitty-rc setup)'}")
    print(f"kittys with a reader socket: {len(live)}" + (f" ({', '.join(live)})" if live else ""))
    return 0


def atspi_text(win):
    try:
        r = subprocess.run(["/usr/bin/python3", "-I", str(ATSPI), str(win.get("pid")), win.get("title", "")],
                           capture_output=True, text=True, timeout=6)
        d = json.loads(r.stdout or "{}")
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return None
    return d.get("text") if d.get("ok") else None


MIN_TEXT = 40


def read_text(win):
    """→ (text, how) or (None, "")."""
    if "kitty" in f"{win.get('class', '')} {win.get('initialClass', '')}".lower() or _kitty_socket(win.get("pid")):
        t = kitty_text(win)
        if t and len(t.strip()) >= MIN_TEXT:
            return t, "kitty"
    t = atspi_text(win)
    if t and len(t.strip()) >= MIN_TEXT:
        return t, "accessibility"
    return None, ""


# ── images for Claude ──
def shrink(img, long_side=1568, max_px=1_150_000):
    h, w = img.shape[:2]
    f = max(1, int(np.ceil(max(max(h, w) / long_side, np.sqrt(h * w / max_px)))))
    if f == 1:
        return img
    h2, w2 = h // f, w // f
    return img[:h2 * f, :w2 * f].reshape(h2, f, w2, f, 3).mean(axis=(1, 3)).astype(np.uint8)


def png(img):
    """H×W×3 uint8 → PNG bytes (in memory)."""
    h, w = img.shape[:2]
    raw = b"".join(b"\0" + img[y].tobytes() for y in range(h))

    def chunk(kind, data):
        return struct_pack(len(data)) + kind + data + struct_pack(zlib.crc32(kind + data) & 0xFFFFFFFF)
    ihdr = struct_pack(w) + struct_pack(h) + bytes([8, 2, 0, 0, 0])
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b"")


def struct_pack(n):
    return int(n).to_bytes(4, "big")


# ── local change detection (watchers) ──
def thumb(img, cell=8, max_cols=320):
    """Grey thumbnail of `cell`-pixel block means, as float32: one new line of text still moves a row of cells,
    while anti-aliasing and sub-pixel jitter average out."""
    g = img[..., 0] * 0.299 + img[..., 1] * 0.587 + img[..., 2] * 0.114
    h, w = g.shape
    f = max(cell, -(-w // max_cols))
    rows, cols = max(1, h // f), max(1, w // f)
    return g[:rows * f, :cols * f].reshape(rows, f, cols, f).mean(axis=(1, 3)).astype(np.float32)


def dhash(t):
    """64-bit difference hash of a thumbnail."""
    rows = np.linspace(0, t.shape[0] - 1, 8).astype(int)
    cols = np.linspace(0, t.shape[1] - 1, 9).astype(int)
    s = t[np.ix_(rows, cols)]
    return (s[:, 1:] > s[:, :-1]).flatten()


class Grid:
    """Compares thumbnails against a baseline. Ignored as noise: cells that keep flickering on their own
    (a seconds clock, a spinner, a blinking caret), and the cells of a small change Claude already said
    wasn't it (a minute clock, a "last updated" line). The pointer is never in a capture."""
    LEVEL = 12.0        # grey levels a cell must move to count as changed
    MIN_CELLS = 6       # fewer changed cells than this is never a change (a caret, a blinking dot)
    NOISY_AFTER = 3     # changed in this many of the last WINDOW looks, in a small flicker → noise
    WINDOW = 6
    SMALL = 0.005       # a rejected change smaller than this share of the window is learned as noise

    def __init__(self, min_area=0.0005):
        self.min_area = min_area
        self.base = None
        self.prev = None
        self.history = []
        self.noise = None
        self.changed = None

    def reset(self, t):
        self.base, self.prev = t, t

    def learn(self):
        """Claude said the last change wasn't it. A small change rejected twice in the same cells (a minute
        clock, a "last updated" line) is noise from then on; once isn't enough, since a status line that
        changed to something else first may still change to the thing he's waiting for."""
        if self.changed is not None and self.changed.mean() < self.SMALL:
            self.rejected[self.changed] += 1
            self.noise |= self.rejected >= 2

    def need(self, size):
        return max(self.MIN_CELLS, int(self.min_area * size))

    def compare(self, t):
        """→ dict(area, cells, hamming, region, settled). area / cells: non-noise cells changed vs the baseline."""
        if self.base is None or self.base.shape != t.shape:
            self.reset(t)
            self.history.clear()
            self.noise = np.zeros(t.shape, bool)
            self.rejected = np.zeros(t.shape, np.uint8)
            self.changed = None
            return {"area": 0.0, "cells": 0, "hamming": 0, "region": None, "settled": True, "first": True}
        step = np.abs(t - self.prev) > self.LEVEL           # what moved since the last look
        self.history = (self.history + [step])[-self.WINDOW:]
        if len(self.history) >= self.NOISY_AFTER and step.mean() < 0.02:     # only flicker-sized changes teach noise
            self.noise |= np.sum(self.history, axis=0) >= self.NOISY_AFTER
        changed = (np.abs(t - self.base) > self.LEVEL) & ~self.noise
        self.changed = changed
        cells = int(changed.sum())
        region = None
        if cells:
            ys, xs = np.nonzero(changed)
            region = (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)
        settled = int((step & ~self.noise).sum()) < self.MIN_CELLS
        self.prev = t
        return {"area": float(changed.mean()), "cells": cells, "hamming": int(np.sum(dhash(t) != dhash(self.base))),
                "region": region, "settled": settled, "first": False}

    def passes(self, r):
        return r["cells"] >= self.need(self.base.size if self.base is not None else 1)
