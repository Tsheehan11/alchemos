#!/usr/bin/env python3
"""stark-govee: STARK OS ambient lighting for a Govee LAN strip (H618C).

The daemon owns the strip: it follows the HUD theme colour, pulses to music
(via cava), and plays boot / login / lock / unlock / logout / shutdown /
sleep animations. Animations and the music spectrum are drawn per segment
through the LAN "razer" (DreamView) stream; steady colours use the plain
whole-strip command. If segment streaming is turned off or fails, every
frame collapses to its average colour.

Usage:
  stark-govee daemon                    run the light daemon (Hyprland exec-once)
  stark-govee event <name> [--wait]     boot|login|lock|unlock|logout|shutdown|sleep|wake
  stark-govee anim <name>               play an animation only (no lock/sleep state), for testing
  stark-govee speed <0.5-2.0>           animation speed multiplier
  stark-govee suspend                   spiral the strip out, then systemctl suspend
  stark-govee mode <auto|music|theme|off>
  stark-govee theme <primary> [accent]  hex colours, e.g. 00dcff ff8a00
  stark-govee color <hex>               manual colour (mode becomes "manual")
  stark-govee status
  stark-govee setup                     find the strip and save its IP
  stark-govee home [--clear]            remember the current network as home
  stark-govee override <hud> <strip>    send <strip> whenever the theme uses <hud>
  stark-govee override <hud> --clear    remove one (no args: list them)
  stark-govee oneshot <name>            play an animation without the daemon
  stark-govee scan
"""
import base64, json, math, os, queue, shutil, signal, socket, struct, subprocess, sys, syslog, threading, time
from pathlib import Path

CFG_DIR = Path(os.environ.get("STARK_GOVEE_DIR", Path.home() / ".config/govee"))
CONFIG, THEME, CAVA_CONF = CFG_DIR / "config.json", CFG_DIR / "theme.json", CFG_DIR / "cava.conf"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}")
SOCK = RUNTIME / "stark-govee.sock"

MCAST, SCAN_PORT, LISTEN_PORT, CMD_PORT = "239.255.255.250", 4001, 4002, 4003

DEFAULTS = {
    "ip": None,
    "mode": "auto",            # auto = theme colour, switches to music when audio plays
    "manual_color": "#00dcff",
    "max_fps": 12,             # packets/sec ceiling; the strip lags if flooded
    "device_brightness": 100,  # hardware brightness set at start; effects scale RGB
    "idle_level": 1.0,         # theme-mode brightness (0-1)
    "music_floor": 0.12,       # dimmest point while music is playing
    "music_gain": 1.0,
    "silence_seconds": 3.0,    # auto mode drops back to theme after this much silence
    "gamma": 2.2,              # LED hue correction: screen colours look washed/purple without it
    "white_balance": [1.0, 1.0, 1.0],  # per-channel trim (r, g, b) if whites look tinted
    "require_docked": True,    # only light up with an external monitor connected
    "home_gateways": [],       # router MACs that count as home (set with: stark-govee home)
    "strip_overrides": {},     # {"#hudcolour": "#stripcolour"} for colours LEDs render badly
    "segments": 15,            # H618C: 15 segments, index 0 = the visible end
    "segment_stream": True,    # per-segment frames via razer; False = whole-strip only
    "segment_fps": 30,         # probe: 30 fps renders cleanly (network fine to 60)
    "anim_speed": 1.0,         # animation speed multiplier (0.5 slow - 2.0 fast)
}
DEFAULT_THEME = {"primary": "#00dcff", "accent": "#ffffff"}
MODES = ("auto", "music", "theme", "off", "manual")
BLACK, WHITE = (0, 0, 0), (255, 255, 255)


def log(*a):
    print("[stark-govee]", *a, file=sys.stderr, flush=True)
    if not os.environ.get("JOURNAL_STREAM"):  # not a systemd service: stderr isn't journaled
        syslog.openlog("stark-govee")
        syslog.syslog(" ".join(str(x) for x in a))


# ---------- config ----------
def load_json(path, defaults):
    out = dict(defaults)
    try:
        out.update(json.loads(path.read_text()))
    except (OSError, ValueError):
        pass
    return out


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def update_config(**kv):
    cfg = load_json(CONFIG, {})
    cfg.update(kv)
    save_json(CONFIG, cfg)


# ---------- colour helpers ----------
def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def hex_to_rgb(h):
    h = str(h).strip().lstrip("#")
    if len(h) == 8:  # #aarrggbb (QML style) -> drop alpha
        h = h[2:]
    if len(h) != 6:
        raise ValueError(f"bad colour: {h!r}")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def scale(c, k):
    return tuple(x * k for x in c)


def _norm(h):
    return "#%02x%02x%02x" % hex_to_rgb(h)


def _overrides_hex(cfg):
    ov = {}
    for k, v in ((cfg or {}).get("strip_overrides") or {}).items():
        try:
            ov[_norm(k)] = _norm(v)
        except ValueError:
            pass
    return ov


def overrides_rgb(cfg):
    return {hex_to_rgb(k): hex_to_rgb(v) for k, v in _overrides_hex(cfg).items()}


def theme_colors(theme, cfg=None):
    ov = _overrides_hex(cfg)
    if ov:
        theme = dict(theme)
        for key in ("primary", "accent"):
            try:
                theme[key] = ov.get(_norm(theme.get(key) or ""), theme.get(key))
            except ValueError:
                pass
    try:
        p = hex_to_rgb(theme.get("primary", DEFAULT_THEME["primary"]))
    except ValueError:
        p = hex_to_rgb(DEFAULT_THEME["primary"])
    try:
        a = hex_to_rgb(theme.get("accent") or "#ffffff")
    except ValueError:
        a = WHITE
    return p, a


# ---------- network ----------
def scan(timeout=2.0):
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    rx.bind(("", LISTEN_PORT))
    rx.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP,
                  struct.pack("4sl", socket.inet_aton(MCAST), socket.INADDR_ANY))
    rx.settimeout(timeout)
    tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    tx.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    found = []
    try:
        tx.sendto(json.dumps({"msg": {"cmd": "scan", "data": {"account_topic": "reserve"}}}).encode(),
                  (MCAST, SCAN_PORT))
        while True:
            d = json.loads(rx.recvfrom(4096)[0]).get("msg", {}).get("data", {})
            if "ip" in d:
                found.append(d)
    except (socket.timeout, OSError, ValueError):
        pass
    finally:
        rx.close(); tx.close()
    return found


def resolve_ip(cfg, allow_scan=True):
    ip = os.environ.get("GOVEE_IP") or cfg.get("ip")
    if ip or not allow_scan:
        return ip
    devs = scan()
    if devs:
        ip = devs[0]["ip"]
        update_config(ip=ip)
        log("found", devs[0].get("sku"), "at", ip)
    return ip


def wait_for_route(ip, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((ip, CMD_PORT))
            return True
        except OSError:
            time.sleep(0.5)
        finally:
            s.close()
    return False


def correct(c, gamma, wb):
    """Gamma-correct the hue while keeping brightness (the max channel) linear."""
    m = max(c)
    if m <= 0:
        return (0, 0, 0)
    return tuple(m * ((x / m) ** gamma) * g for x, g in zip(c, wb))


# ---------- "docked at home" gate ----------
def docked():
    """True if any external display connector (not the laptop panel) is connected."""
    for st in Path("/sys/class/drm").glob("card*-*/status"):
        name = st.parent.name.split("-", 1)[1]
        if name.startswith(("eDP", "LVDS", "DSI", "Writeback")):
            continue
        try:
            if st.read_text().strip() == "connected":
                return True
        except OSError:
            pass
    return False


def _default_gateways():
    gws = set()
    try:
        for line in Path("/proc/net/route").read_text().splitlines()[1:]:
            f = line.split()
            if len(f) > 3 and f[1] == "00000000" and int(f[3], 16) & 2:
                gws.add(socket.inet_ntoa(struct.pack("<L", int(f[2], 16))))
    except (OSError, ValueError):
        pass
    return gws


def _arp():
    out = {}
    try:
        for line in Path("/proc/net/arp").read_text().splitlines()[1:]:
            f = line.split()
            if len(f) >= 4 and f[3] != "00:00:00:00:00:00":
                out[f[0]] = f[3].lower()
    except OSError:
        pass
    return out


def gateway_macs():
    gws = _default_gateways()
    if not gws:
        return set()
    arp = _arp()
    if not all(g in arp for g in gws):  # nudge the kernel to resolve the router's MAC
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        for g in gws:
            try:
                s.sendto(b"", (g, 9))
            except OSError:
                pass
        s.close()
        time.sleep(0.3)
        arp = _arp()
    return {arp[g] for g in gws if g in arp}


def at_home(cfg):
    homes = {m.lower() for m in cfg.get("home_gateways") or []}
    if not homes:
        return True  # no home saved yet: don't block anything
    return bool(gateway_macs() & homes)


def gate_reason(cfg):
    """Why the dock+home gate is closed, or None if the lights may run."""
    if cfg.get("require_docked", True) and not docked():
        return "not docked"
    if not at_home(cfg):
        return "not on the home network"
    return None


def should_run(cfg):
    return gate_reason(cfg) is None


def strip_answers(ip, timeout=1.0):
    rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        rx.bind(("", LISTEN_PORT))
        rx.settimeout(timeout)
        rx.sendto(json.dumps({"msg": {"cmd": "devStatus", "data": {}}}).encode(), (ip, CMD_PORT))
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if rx.recvfrom(4096)[1][0] == ip:
                return True
    except OSError:
        pass
    finally:
        rx.close()
    return False


def wait_ready(cfg, ip, timeout, check_strip):
    """Before login the router's ARP entry, the dock's screens and the strip can each lag
    a few seconds behind network-online, so keep retrying until `timeout`."""
    end = time.monotonic() + timeout
    while True:
        why = gate_reason(cfg) or (None if not check_strip or strip_answers(ip) else "strip not answering")
        if why is None or time.monotonic() >= end:
            return why
        time.sleep(1.0)


def _calib(cfg):
    try:
        g = float(cfg.get("gamma", 2.2))
        wb = tuple(float(x) for x in cfg.get("white_balance", (1, 1, 1)))[:3]
        return clamp(g, 1.0, 3.5), wb if len(wb) == 3 else (1.0, 1.0, 1.0)
    except (TypeError, ValueError):
        return 2.2, (1.0, 1.0, 1.0)


def _seg_cfg(cfg):
    n = int(clamp(int(cfg.get("segments", 15) or 0), 0, 64))
    on = bool(cfg.get("segment_stream", True)) and n > 1
    fps = int(clamp(cfg.get("segment_fps", 30), 2, 30))
    speed = float(clamp(float(cfg.get("anim_speed", 1.0) or 1.0), 0.5, 2.0))
    return max(n, 1), on, fps, speed


def _xor(b):
    c = 0
    for x in b:
        c ^= x
    return c


def razer_packet(body):
    return base64.b64encode(bytes(body + [_xor(body)])).decode()


RAZER_ON = razer_packet([0xBB, 0x00, 0x01, 0xB1, 0x01])
TRACE = bool(os.environ.get("STARK_GOVEE_TRACE"))
RAZER_SETTLE = 0.3  # probe: frames sent sooner than this after enabling are dropped


def average(cols):
    return tuple(sum(c[i] for c in cols) / len(cols) for i in range(3))


def make_strip(cfg, ip):
    n, stream, _, _ = _seg_cfg(cfg)
    return Strip(ip, int(clamp(cfg.get("max_fps", 12), 2, 30)), *_calib(cfg),
                 overrides=overrides_rgb(cfg), segments=n, stream=stream)


class Strip:
    def __init__(self, ip, max_fps, gamma=2.2, wb=(1.0, 1.0, 1.0), overrides=None,
                 segments=15, stream=True):
        self.gamma, self.wb = gamma, tuple(wb)
        self.ip = ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.min_dt = 1.0 / max(1, max_fps)
        self.last_t = 0.0
        self.last_rgb = None
        self.quiet = False
        self.ov = overrides or {}
        self.n = segments
        self.stream = stream      # segment frames allowed (config + no runtime failure)
        self.razer = False        # strip currently in razer mode (any normal command drops it)
        self.razer_t = 0.0
        self.last_frame, self.last_ft = None, 0.0
        self.fails = 0

    def send(self, cmd, data):
        if self.quiet or not self.ip:
            return True
        try:
            self.sock.sendto(json.dumps({"msg": {"cmd": cmd, "data": data}}).encode(), (self.ip, CMD_PORT))
            return True
        except OSError:
            return False  # off-network / no route: stay silent

    def _px(self, c):
        """Per-colour override, then gamma: applied to every pixel we send."""
        c = tuple(int(round(clamp(x, 0, 255))) for x in c)
        c = self.ov.get(c, c)
        return tuple(int(round(clamp(x, 0, 255))) for x in correct(c, self.gamma, self.wb))

    def power(self, on):
        self.send("turn", {"value": 1 if on else 0})
        self.last_rgb = self.last_frame = None
        self.razer = False

    def brightness(self, v):
        self.send("brightness", {"value": int(clamp(v, 1, 100))})

    def rgb(self, c, force=False):
        c = self._px(c)
        now = time.monotonic()
        if not force:
            if now - self.last_t < self.min_dt:
                return
            if c == self.last_rgb and now - self.last_t < 5.0:  # keepalive resend every 5 s
                return
        self.send("colorwc", {"color": {"r": c[0], "g": c[1], "b": c[2]}, "colorTemInKelvin": 0})
        self.last_rgb, self.last_t = c, now
        self.razer, self.last_frame = False, None

    def frame(self, cols, force=False):
        """One colour per segment (index 0 = visible end). Falls back to the average colour."""
        if not self.stream:
            return self.rgb(average(cols), force=force and time.monotonic() - self.last_t >= self.min_dt)
        px = [self._px(c) for c in cols]
        now = time.monotonic()
        if px == self.last_frame and now - self.last_ft < 2.0:
            return
        if not self.razer:
            if not self.send("razer", {"pt": RAZER_ON}):
                return self._failed(cols)
            if not self.quiet and self.ip:
                time.sleep(RAZER_SETTLE)
            self.razer, self.razer_t = True, time.monotonic()
        elif now - self.razer_t > 10.0:  # keepalive, in case the strip times the stream out
            self.send("razer", {"pt": RAZER_ON})
            self.razer_t = now
        body = [0xBB, 0x00, 3 * len(px) + 2, 0xB0, 0x00, len(px)]
        for c in px:
            body += c
        if not self.send("razer", {"pt": razer_packet(body)}):
            return self._failed(cols)
        self.fails = 0
        if TRACE:
            log(f"frame dt={1000 * (now - self.last_ft):.0f}ms")
        self.last_frame, self.last_ft = px, now
        self.last_rgb = None

    def _failed(self, cols):
        self.fails += 1
        self.razer = False
        if self.fails >= 3:
            log("segment stream failing; falling back to whole-strip colour")
            self.stream = False
        self.rgb(average(cols), force=True)


# ---------- animations ----------
# Each yields a frame (list of n RGB tuples, index 0 = visible end), or "on" / "off".
# fps is already divided by the speed setting, so a faster speed means fewer frames.
def _n(sec, fps):
    return max(1, int(round(sec * fps)))


def ease(t):
    return 1 - (1 - t) ** 3


def ease_in_out(t):
    return 3 * t * t - 2 * t * t * t


def solid(c, n):
    return [tuple(c)] * n


def _seg(c, n):
    return list(c) if isinstance(c, list) else solid(c, n)


def fade(a, b, sec, fps, n, curve=ease):
    a, b = _seg(a, n), _seg(b, n)
    m = _n(sec, fps)
    for i in range(1, m + 1):
        t = curve(i / m)
        yield [mix(x, y, t) for x, y in zip(a, b)]


def hold(c, sec, fps, n):
    c = _seg(c, n)
    for _ in range(_n(sec, fps)):
        yield c


def flicker(p, levels, fps, n):
    for k in levels:
        yield from hold(scale(p, k), 0.09, fps, n)


# Front orders: the front reaches segment i at "distance" order[i].
def from_start(n):    # sweep from the visible end
    return list(range(n))


def ends_in(n):       # two fronts from both ends, meeting in the middle
    return [min(i, n - 1 - i) for i in range(n)]


def centre_out(n):    # one front splitting outward from the middle
    h = (n - 1) // 2
    return [h - min(i, n - 1 - i) for i in range(n)]


def toward_start(n):  # retreats from the far end toward the visible end
    return [n - 1 - i for i in range(n)]


EDGE_WHITE = 0.2  # how far edges lean toward white; above ~0.25 red reads as pink/white


def edge_color(p):
    """Door/sweep edges and flashes: the theme colour at full value, only nudged toward white.
    p is already override-mapped, and Strip applies gamma per pixel, so the hue survives."""
    m = max(p)
    if m <= 0:
        return WHITE
    return mix(scale(p, 255 / m), WHITE, EDGE_WHITE)


def front(frm, to, order, sec, fps, head=None, glow=0.8, curve=ease_in_out, soft=2.0):
    """A soft edge travelling along `order`: segments it has passed show `to`.
    The edge spans `soft` segments so motion reads smoothly on big physical segments."""
    n = len(order)
    frm, to = _seg(frm, n), _seg(to, n)
    span = max(order) + soft + 1.0
    m = _n(sec, fps)
    for k in range(1, m + 1):
        pos = curve(k / m) * span - 0.5
        out = []
        for i, d in enumerate(order):
            c = mix(frm[i], to[i], clamp((pos - d) / soft, 0.0, 1.0))
            if head is not None and k < m:
                g = glow * max(0.0, 1 - abs(pos - d - soft / 2) / (soft + 0.5))
                c = mix(c, head, g)
            out.append(c)
        yield out


def anim_boot(p, a, cur, fps, n):  # arc reactor charging: three accelerating sweeps, then ignite
    yield "on"
    yield from hold(BLACK, 0.3, fps, n)
    lvl, e = BLACK, edge_color(p)
    for k, sec in ((0.15, 0.9), (0.4, 0.6), (0.75, 0.4)):
        nxt = scale(p, k)
        yield from front(lvl, nxt, from_start(n), sec, fps, head=e, curve=lambda t: t)
        lvl = nxt
    yield from fade(lvl, WHITE, 0.15, fps, n)  # the one white flash: reactor ignition
    yield from fade(WHITE, p, 1.0, fps, n)


def anim_login(p, a, cur, fps, n):
    yield "on"
    e = edge_color(p)
    yield from front(cur, scale(p, 0.3), from_start(n), 0.6, fps, head=e, curve=lambda t: t)
    yield from front(scale(p, 0.3), p, from_start(n), 0.4, fps, head=e, curve=lambda t: t)
    yield from fade(p, e, 0.15, fps, n)
    yield from fade(e, p, 0.8, fps, n)


LOCK_GLOW = 0.12  # standby level the lock settles at (target() breathes around it)


def anim_lock(p, a, cur, fps, n):  # security doors close from both ends, flash where they meet
    shut, e = scale(p, LOCK_GLOW), edge_color(p)
    yield from front(cur, shut, ends_in(n), 1.2, fps, head=e, glow=1.0)
    mid, m = (n - 1) / 2, _n(0.6, fps)
    for k in range(m):
        g = 1 - k / m
        yield [mix(shut, e, g * max(0.0, 1 - abs(i - mid) / 2.5)) for i in range(n)]
    yield solid(shut, n)


def anim_unlock(p, a, cur, fps, n):  # doors part from the middle
    yield "on"
    yield from front(cur, p, centre_out(n), 1.3, fps, head=edge_color(p))


def anim_theme(p, a, cur, fps, n):  # wipe from the old colour (whatever is showing) to the new
    yield from front(cur, p, from_start(n), 1.4, fps, head=edge_color(p), glow=0.6)


def anim_logout(p, a, cur, fps, n):  # drain toward the visible end
    yield from fade(cur, p, 0.3, fps, n)
    yield from front(p, BLACK, toward_start(n), 1.6, fps)
    yield "off"


def anim_shutdown(p, a, cur, fps, n):  # reactor power-down, then drain
    yield from fade(cur, p, 0.2, fps, n)
    yield from flicker(p, (0.4, 1.0, 0.25, 0.7), fps, n)
    yield from front(scale(p, 0.7), BLACK, toward_start(n), 1.4, fps)
    yield "off"


def spiral_down(p, cur, fps, n, end):
    """Reactor spinning down: a comet laps the strip twice, slower and fainter each time,
    while the glow drains to `end`."""
    e, base, rest = edge_color(p), _seg(cur, n), _seg(end, n)
    laps = ((1.1, 1.0), (1.6, 0.55))  # (seconds, comet strength)
    total, done = sum(sec for sec, _ in laps), 0.0
    for sec, k in laps:
        m = _n(sec, fps)
        for i in range(1, m + 1):
            pos = i / m * (n + 3) - 1.0             # head runs off the far end
            left = (1 - (done + sec * i / m) / total) ** 1.6
            out = []
            for j in range(n):
                d = pos - j                          # > 0: segment is behind the head (tail)
                g = max(0.0, 1 - d / 3.5) if d >= 0 else max(0.0, 1 + d / 0.8)
                out.append(mix(mix(rest[j], base[j], left), e, g * k))
            yield out
        done += sec
    yield from hold(rest, 0.15, fps, n)


def anim_sleep(p, a, cur, fps, n):  # before suspend: settle on the lock-screen glow, stay on
    yield from spiral_down(p, cur, fps, n, scale(p, LOCK_GLOW))


def anim_park(p, a, cur, fps, n):   # undocked / left home: the only animation that ends fully off
    yield from spiral_down(p, cur, fps, n, BLACK)
    yield "off"


def anim_wake(p, a, cur, fps, n):
    yield "on"


ANIMS = {"boot": anim_boot, "login": anim_login, "unlock": anim_unlock, "lock": anim_lock,
         "logout": anim_logout, "shutdown": anim_shutdown, "sleep": anim_sleep, "wake": anim_wake}
EXTRA_ANIMS = {"theme": anim_theme, "park": anim_park}  # not system events; played by the daemon / `anim`
GOES_DARK = {"logout", "shutdown", "sleep"}


# ---------- suspend: logind delay inhibitor ----------
class Logind:
    """Holds a logind sleep "delay" lock and reports PrepareForSleep(true/false).
    NetworkManager drops Wi-Fi ~0.1 s after PrepareForSleep, so on_sleep must be quick."""

    def __init__(self, on_sleep, on_resume):
        from gi.repository import Gio, GLib  # noqa: lazy so the CLI never needs gi
        self.Gio, self.GLib = Gio, GLib
        self.on_sleep, self.on_resume = on_sleep, on_resume
        self.bus = Gio.bus_get_sync(Gio.BusType.SYSTEM, None)
        self.fd = None
        self.bus.signal_subscribe("org.freedesktop.login1", "org.freedesktop.login1.Manager",
                                  "PrepareForSleep", "/org/freedesktop/login1", None,
                                  Gio.DBusSignalFlags.NONE, self._signal)
        self.take()
        threading.Thread(target=GLib.MainLoop().run, daemon=True).start()

    def take(self):
        if self.fd is not None:
            return
        try:
            res, fds = self.bus.call_with_unix_fd_list_sync(
                "org.freedesktop.login1", "/org/freedesktop/login1", "org.freedesktop.login1.Manager",
                "Inhibit", self.GLib.Variant("(ssss)", ("sleep", "stark-govee", "Ambient lights off", "delay")),
                self.GLib.VariantType("(h)"), self.Gio.DBusCallFlags.NONE, -1, None, None)
            self.fd = fds.get(res.unpack()[0])
        except Exception as e:  # GLib.Error
            log("couldn't take the sleep inhibitor:", e)

    def release(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None

    def _signal(self, conn, sender, path, iface, name, params):
        if params.unpack()[0]:
            try:
                self.on_sleep()
            finally:
                self.release()
        else:
            self.take()
            self.on_resume()


# ---------- daemon ----------
class Daemon:
    def __init__(self):
        self.cfg = load_json(CONFIG, DEFAULTS)
        self.theme = load_json(THEME, DEFAULT_THEME)
        self.strip = make_strip(self.cfg, resolve_ip(self.cfg))
        self.nseg, _, self.seg_fps, self.speed = _seg_cfg(self.cfg)
        self.fps = self.loop_fps()
        self.q = queue.Queue()
        self.running = True
        self.locked = self.asleep = False
        self.powered = None
        self.cur = BLACK
        self.curf = solid(BLACK, self.nseg)  # last frame shown, per segment
        self.anim = self.anim_done = self.anim_after = self.anim_name = None
        self.wake_until = 0.0
        self.parked = False       # not docked at home: strip left alone
        self.gate_vote, self.last_gate = 0, 0.0
        self.mtimes = {}
        self.last_poll = self.last_scan = 0.0
        # audio state (written by the cava thread)
        self.cava = None
        self.level = self.flash = self.bass_avg = 0.0
        self.last_sound = self.last_frame = self.last_beat = 0.0
        self.bars = []
        self.seg_lvl = [0.0] * self.nseg
        self.suspending = False   # between PrepareForSleep(true) and the resume handling
        self.logind = None

    def loop_fps(self):
        # segment frames need the faster loop; whole-strip output is throttled to max_fps anyway
        return self.seg_fps if self.strip.stream else int(clamp(self.cfg.get("max_fps", 12), 2, 30))

    # --- control socket ---
    def serve(self):
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(SOCK))
        os.chmod(SOCK, 0o600)
        srv.listen(8)
        self.srv = srv
        while self.running:
            try:
                conn, _ = srv.accept()
            except OSError:
                break
            threading.Thread(target=self.client, args=(conn,), daemon=True).start()

    def client(self, conn):
        with conn:
            try:
                conn.settimeout(15)
                parts = conn.makefile().readline().split()
                if not parts:
                    return
                if parts[0] == "status":
                    conn.sendall((json.dumps(self.status()) + "\n").encode())
                    return
                done = threading.Event()
                self.q.put((parts, done))
                if "--wait" in parts:
                    done.wait(12)
                conn.sendall(b"ok\n")
            except OSError:
                pass

    def status(self):
        return {"ip": self.strip.ip, "mode": self.cfg.get("mode"), "locked": self.locked,
                "asleep": self.asleep, "music_active": self.music_active(),
                "level": round(self.level, 2), "theme": self.theme,
                "rgb": [int(x) for x in self.cur], "cava": self.cava is not None,
                "parked": self.parked, "docked": docked(), "home": at_home(self.cfg),
                "segments": self.nseg, "stream": self.strip.stream, "fps": self.fps,
                "anim_speed": self.speed, "anim": self.anim_name,
                "inhibitor": bool(self.logind and self.logind.fd is not None)}

    # --- audio via cava ---
    def want_audio(self):
        return (self.cfg.get("mode") in ("auto", "music") and not self.locked
                and not self.asleep and not self.parked and self.strip.ip is not None)

    def manage_cava(self):
        want = self.want_audio()
        if want and self.cava is None:
            if not shutil.which("cava") or not CAVA_CONF.exists():
                return
            try:
                self.cava = subprocess.Popen(["cava", "-p", str(CAVA_CONF)], stdout=subprocess.PIPE,
                                             stderr=subprocess.DEVNULL, text=True, bufsize=1)
                threading.Thread(target=self.read_cava, args=(self.cava,), daemon=True).start()
            except OSError as e:
                log("cava failed:", e)
                self.cava = None
        elif not want and self.cava is not None:
            self.stop_cava()

    def stop_cava(self):
        if self.cava:
            self.cava.terminate()
            try:
                self.cava.wait(2)
            except subprocess.TimeoutExpired:
                self.cava.kill()
        self.cava = None
        self.level = self.flash = 0.0

    def read_cava(self, proc):
        for line in proc.stdout:
            try:
                v = [int(x) / 1000 for x in line.strip().split(";") if x]
            except ValueError:
                continue
            if not v:
                continue
            self.bars = v
            now = time.monotonic()
            bass = sum(v[:3]) / min(3, len(v))
            overall = sum(v) / len(v)
            raw = min(1.0, (0.7 * bass + 0.3 * overall) * self.cfg.get("music_gain", 1.0))
            self.level = max(raw, self.level * 0.85)  # instant attack, smooth decay
            self.bass_avg = 0.95 * self.bass_avg + 0.05 * bass
            if bass > 0.35 and bass > self.bass_avg * 1.35 and now - self.last_beat > 0.18:
                self.flash, self.last_beat = 1.0, now
            else:
                self.flash *= 0.85
            if overall > 0.02:
                self.last_sound = now
            self.last_frame = now

    def music_active(self):
        mode = self.cfg.get("mode")
        if mode == "music":
            return True
        return mode == "auto" and self.cava is not None and \
            time.monotonic() - self.last_sound < self.cfg.get("silence_seconds", 3.0)

    # --- file watching ---
    def poll_files(self):
        now = time.monotonic()
        if now - self.last_poll < 1.0:
            return
        self.last_poll = now
        for path in (CONFIG, THEME):
            try:
                m = path.stat().st_mtime
            except OSError:
                continue
            if self.mtimes.get(path) != m:
                self.mtimes[path] = m
                self.reload()
        if self.strip.ip is None and now - self.last_scan > 30:
            self.last_scan = now
            self.strip.ip = resolve_ip(self.cfg)

    def reload(self):
        old = theme_colors(self.theme, self.cfg)[0]
        self.cfg = load_json(CONFIG, DEFAULTS)
        self.theme = load_json(THEME, DEFAULT_THEME)
        if self.cfg.get("ip"):
            self.strip.ip = os.environ.get("GOVEE_IP") or self.cfg["ip"]
        self.strip.gamma, self.strip.wb = _calib(self.cfg)
        self.strip.ov = overrides_rgb(self.cfg)
        n, stream, self.seg_fps, self.speed = _seg_cfg(self.cfg)
        if n != self.nseg:
            self.nseg, self.strip.n = n, n
            self.curf, self.seg_lvl = solid(self.cur, n), [0.0] * n
        self.strip.stream, self.strip.fails = stream, 0  # a reload retries a failed stream
        self.fps = self.loop_fps()
        self.strip.last_rgb = self.strip.last_frame = None  # resend with new calibration
        if theme_colors(self.theme, self.cfg)[0] != old and self.can_wipe():
            self.start_anim("theme", manual=True)

    def can_wipe(self):
        return (self.anim is None and self.powered is True and not self.locked and not self.asleep
                and not self.parked and self.cfg.get("mode") not in ("off", "manual"))

    # --- commands / events ---
    def drain(self):
        while True:
            try:
                parts, done = self.q.get_nowait()
            except queue.Empty:
                return
            cmd = parts[0]
            if cmd == "event" and len(parts) > 1 and parts[1] in ANIMS:
                self.event(parts[1], done)
                continue
            if cmd == "anim" and len(parts) > 1 and (parts[1] in ANIMS or parts[1] in EXTRA_ANIMS):
                if self.parked:  # the dock+home gate still applies to test runs
                    done.set()
                else:
                    self.asleep = False
                    self.start_anim(parts[1], done, manual=True)
                continue
            if cmd == "_slept":
                self.anim = self.anim_done = self.anim_after = self.anim_name = None
                self.asleep = True
                self.cur = scale(theme_colors(self.theme, self.cfg)[0], LOCK_GLOW)
                self.curf = solid(self.cur, self.nseg)
            elif cmd == "_resumed":
                self.resumed(parts[1])
            elif cmd == "reload":
                self.reload()
            elif cmd == "quiet":  # system shutdown takes over the strip
                self.strip.quiet = True
                self.running = False
            done.set()

    def event(self, name, done):
        now = time.monotonic()
        if self.suspending:  # asleep / strip unreachable: track the lock state, resume animates it
            if name in ("lock", "unlock"):
                self.locked = name == "lock"
            done.set()
            return
        if name == "lock":
            self.locked = True
            if self.asleep:  # e.g. hypridle locking after the pre-suspend spiral: stay dark
                done.set()
                return
        elif name in ("unlock", "login", "boot"):
            if name == "unlock":
                self.locked = False
            self.asleep = False
        elif name == "wake":
            if self.logind:  # the old system-sleep hook; resume is handled via logind now
                done.set()
                return
            self.asleep = False
            self.wake_until = now + 15  # network may still be coming up after resume
        if self.parked:
            done.set()
            return
        if self.cfg.get("mode") == "off":
            if name in GOES_DARK:
                self.asleep = True
            done.set()
            return
        self.start_anim(name, done)

    # --- suspend / resume (logind thread) ---
    def before_sleep(self):
        """Wi-Fi has ~0.1 s left: a fade can't finish, so go dark in one shot."""
        self.suspending = True
        if self.parked or self.cfg.get("mode") == "off" or not self.strip.ip or self.powered is False:
            log("suspend: strip left alone (parked, off or already dark)")
            return
        # Leave razer for plain colour + brightness commands: the strip holds those on its own
        # while the laptop sleeps. Sent first thing; the spiral (if any) already played.
        t0 = time.monotonic()
        dim = scale(theme_colors(self.theme, self.cfg)[0], LOCK_GLOW)
        self.strip.rgb(dim, force=True)
        self.strip.brightness(self.cfg.get("device_brightness", 100))
        how = "after the spiral" if self.asleep else "no spiral: suspend didn't come from the HUD"
        log(f"suspend: dim glow held ({1000 * (time.monotonic() - t0):.1f} ms, {how})")
        self.q.put((["_slept"], threading.Event()))

    def after_resume(self):
        threading.Thread(target=self._await_strip, daemon=True).start()

    def _await_strip(self, timeout=20.0):
        """Wait for Wi-Fi + the strip. If the gate closed while we slept (undocked), the strip
        is still on its dim glow: switch it off once reachable; if it isn't (away), leave it."""
        end, t0 = time.monotonic() + timeout, time.monotonic()
        result, gate = "fail", None
        while self.strip.ip and time.monotonic() < end:
            gate = gate_reason(self.cfg)
            if strip_answers(self.strip.ip):
                dt = time.monotonic() - t0
                if gate is None:
                    log(f"resume: strip back after {dt:.1f} s")
                    result = "ok"
                else:
                    self.strip.power(False)
                    log(f"resume: {gate} while asleep; strip off after {dt:.1f} s")
                    result = "parked"
                break
            time.sleep(1.0)
        else:
            what = f"{gate}, " if gate else ""
            log(f"resume: strip not reachable after {timeout:.0f} s ({what}Wi-Fi or away); leaving it")
        self.q.put((["_resumed", result], threading.Event()))

    def resumed(self, result):
        """ok: gate open + strip answered; parked: the strip was switched off (undocked);
        fail: unreachable, the gate takes it from here."""
        self.suspending = False
        self.strip.razer, self.strip.last_frame, self.strip.last_rgb = False, None, None
        self.gate_vote, self.last_gate = 0, time.monotonic()
        if result == "parked":
            self.parked, self.powered = True, False
            self.curf, self.cur = solid(BLACK, self.nseg), BLACK
            return
        if result != "ok" or self.cfg.get("mode") == "off":
            return
        self.parked = self.asleep = False
        # The strip is still on the dim lock glow. Unlocked already (fingerprint often beats
        # Wi-Fi back): open the doors from it. Still locked: keep the glow; unlock opens it.
        if not self.locked:
            self.start_anim("unlock")  # frames re-enter razer mode, then the active mode resumes

    def start_anim(self, name, done=None, manual=False):
        """manual: play the light show only; don't go dark/asleep afterwards."""
        if self.anim_done:
            self.anim_done.set()  # interrupted: release any waiter, skip its after-action
        p, a = theme_colors(self.theme, self.cfg)
        fn = ANIMS.get(name) or EXTRA_ANIMS[name]
        self.anim = fn(p, a, list(self.curf), self.fps / self.speed, self.nseg)
        self.anim_done = done
        self.anim_after = None if manual else name
        self.anim_name = name

    def finish_anim(self):
        if self.anim_after in GOES_DARK:
            self.asleep = True
        if self.anim_done:
            self.anim_done.set()
        self.anim = self.anim_done = self.anim_after = self.anim_name = None

    # --- docked-at-home gate ---
    def gate(self):
        now = time.monotonic()
        if self.suspending:  # Wi-Fi is down mid-resume: the resume check decides instead
            self.gate_vote, self.last_gate = 0, now
            return
        if now - self.last_gate < 3.0:
            return
        self.last_gate = now
        ok = should_run(self.cfg)
        if ok == (not self.parked):
            self.gate_vote = 0
            return
        self.gate_vote += 1
        if self.gate_vote < 2:  # need two readings in a row (~6 s) so docking blips don't flicker
            return
        self.gate_vote = 0
        if ok:
            log("docked at home: lights on")
            self.parked = self.asleep = False
            if self.cfg.get("mode") != "off":
                self.start_anim("login")
        else:
            log("not docked at home: lights off")
            self.parked = True
            if self.cfg.get("mode") != "off":
                self.start_anim("park", manual=True)

    # --- rendering ---
    def target(self):
        mode = self.cfg.get("mode", "auto")
        if mode == "off":
            return None
        p, a = theme_colors(self.theme, self.cfg)
        if self.locked:  # slow standby breathing
            return scale(p, 0.09 + 0.06 * math.sin(time.monotonic() * 2 * math.pi / 4))
        if mode == "manual":
            try:
                return hex_to_rgb(self.cfg.get("manual_color"))
            except ValueError:
                return p
        if self.music_active():
            if time.monotonic() - self.last_frame > 0.5:
                self.level = self.flash = 0.0
            floor = self.cfg.get("music_floor", 0.12)
            return scale(mix(p, a, self.flash * 0.85), floor + (1 - floor) * self.level)
        return scale(p, self.cfg.get("idle_level", 1.0))

    def set_power(self, on):
        self.strip.power(on)
        self.powered = on

    def step(self):
        if self.strip.quiet or self.suspending:
            return
        if self.anim:
            try:
                f = next(self.anim)
            except StopIteration:
                self.finish_anim()
                return
            if f in ("on", "off"):
                if self.powered is not (f == "on"):  # a redundant "turn" drops razer mode
                    self.set_power(f == "on")
            else:
                self.curf, self.cur = f, average(f)
                self.strip.frame(f, force=True)
            return
        if self.asleep or self.parked:
            return
        now = time.monotonic()
        if now < self.wake_until and now - self.strip.last_t > 1.0:
            self.set_power(True)
        t = self.target()
        if t is None:
            if self.powered is not False:
                self.set_power(False)
            return
        if self.powered is not True:
            self.set_power(True)
        music = self.music_active() and not self.locked and self.cfg.get("mode") != "manual"
        if music and self.strip.stream:
            f = self.spectrum()
            self.curf, self.cur = f, average(f)
            self.strip.frame(f)
            return
        k = 0.55 if music else 0.2  # per-step smoothing tuned for 12 steps/s
        self.cur = mix(self.cur, t, 1 - (1 - k) ** (12 / self.fps))
        self.curf = solid(self.cur, self.nseg)
        if self.strip.stream:  # stay in razer mode: no re-enable stall before the next animation
            self.strip.frame(self.curf)
        else:
            self.strip.rgb(self.cur)

    def spectrum(self):
        """cava bars across the strip: bass at the visible end, treble at the far end."""
        n = self.nseg
        p, a = theme_colors(self.theme, self.cfg)
        bars = self.bars
        if not bars or time.monotonic() - self.last_frame > 0.5:
            vals = [0.0] * n
        elif len(bars) == n:
            vals = bars
        else:  # resample to the segment count
            vals = []
            for i in range(n):
                x = i * (len(bars) - 1) / max(1, n - 1)
                j = min(int(x), len(bars) - 2) if len(bars) > 1 else 0
                fr = x - j
                vals.append(bars[j] * (1 - fr) + bars[min(j + 1, len(bars) - 1)] * fr)
        gain = self.cfg.get("music_gain", 1.0)
        floor = max(self.cfg.get("music_floor", 0.12), 0.3)  # segments never blink to black
        out = []
        for i in range(n):
            # each band spills into its neighbours: one lit segment alone reads as a glitch
            v = max(vals[j] * w for j, w in ((i, 1.0), (i - 1, 0.6), (i + 1, 0.6), (i - 2, 0.3), (i + 2, 0.3))
                    if 0 <= j < n)
            v = clamp(v * gain, 0.0, 1.0)
            lv = self.seg_lvl[i]
            self.seg_lvl[i] = lv + (v - lv) * (0.45 if v > lv else 0.08)  # soft attack, slow decay
            pos = i / max(1, n - 1)
            c = mix(p, a, 0.75 * pos)                        # primary at the bass end, accent up top
            c = mix(c, WHITE, self.flash * 0.12 * (1 - pos))  # kick drums lift the bass end
            out.append(scale(c, floor + (1 - floor) * self.seg_lvl[i]))
        return out

    def run(self):
        try:
            ask("status", timeout=1)
            sys.exit("stark-govee daemon already running")
        except OSError:
            pass
        try:
            SOCK.unlink()
        except FileNotFoundError:
            pass

        def stop(*_):
            self.strip.quiet = True  # session teardown: go silent, shutdown hook animates
            self.running = False
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        signal.signal(signal.SIGHUP, stop)

        threading.Thread(target=self.serve, daemon=True).start()
        try:
            self.logind = Logind(self.before_sleep, self.after_resume)
        except Exception as e:  # no gi / no system bus: the system-sleep hook still works
            log("logind unavailable, suspend handled by the system-sleep hook:", e)
        if self.strip.ip:
            self.strip.brightness(self.cfg.get("device_brightness", 100))
        else:
            log("no strip IP yet; will rescan every 30 s")
        self.poll_files()
        self.parked = not should_run(self.cfg)
        self.last_gate = time.monotonic()
        if self.parked:
            log("not docked at home: idling")
        elif self.cfg.get("mode") != "off":
            self.start_anim("login")
        while self.running:
            tick = 1.0 / self.fps
            t0 = time.monotonic()
            self.poll_files()
            self.drain()
            self.gate()
            self.manage_cava()
            self.step()
            time.sleep(max(0.0, tick - (time.monotonic() - t0)))
        self.stop_cava()
        try:
            self.srv.close()
            SOCK.unlink()
        except (OSError, AttributeError):
            pass


# ---------- client side ----------
def ask(line, timeout=15):
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect(str(SOCK))
        s.sendall((line + "\n").encode())
        return s.makefile().readline().strip()
    finally:
        s.close()


def session_frozen():
    # systemd freezes user.slice for suspend; a frozen daemon accepts the connection but never answers
    try:
        return "frozen 1" in Path("/sys/fs/cgroup/user.slice/cgroup.events").read_text()
    except OSError:
        return False


def play_direct(name, route_timeout=3.0):
    cfg = load_json(CONFIG, DEFAULTS)
    if cfg.get("mode") == "off" and name not in GOES_DARK:
        return
    ip = resolve_ip(cfg, allow_scan=False)
    if not ip or not wait_for_route(ip, route_timeout):
        log("strip not reachable; skipping", name)
        return
    boot = name == "boot"
    why = wait_ready(cfg, ip, 15.0 if boot else 0.0, check_strip=boot)
    if why:
        log(f"{why}; skipping", name)
        return
    strip = make_strip(cfg, ip)
    n, stream, seg_fps, speed = _seg_cfg(cfg)
    fps = seg_fps if stream else int(clamp(cfg.get("max_fps", 12), 2, 30))
    p, a = theme_colors(load_json(THEME, DEFAULT_THEME), cfg)
    start = solid(BLACK if name in ("boot", "login", "wake") else p, n)
    if name == "boot":
        strip.brightness(cfg.get("device_brightness", 100))
    fn = ANIMS.get(name) or EXTRA_ANIMS[name]
    for f in fn(p, a, start, fps / speed, n):
        t0 = time.monotonic()
        if f in ("on", "off"):
            strip.power(f == "on")
        else:
            strip.frame(f, force=True)
        time.sleep(max(0.0, 1.0 / fps - (time.monotonic() - t0)))
    if name == "wake":
        strip.rgb(p, force=True)


def main(argv):
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, args = argv[0], argv[1:]

    if cmd == "daemon":
        Daemon().run()
    elif cmd == "event":
        if not args or args[0] not in ANIMS:
            sys.exit("events: " + ", ".join(ANIMS))
        if session_frozen():  # suspend hook: network is already down, so don't hold up sleep
            play_direct(args[0], route_timeout=0.5)
            return
        try:
            ask(" ".join(["event"] + args))
        except OSError:
            play_direct(args[0])  # no daemon (e.g. suspend before login): animate directly
    elif cmd == "anim":
        names = list(ANIMS) + list(EXTRA_ANIMS)
        if not args or args[0] not in names:
            sys.exit("animations: " + ", ".join(names))
        try:
            ask(f"anim {args[0]} --wait")
        except OSError:
            play_direct(args[0])
    elif cmd == "suspend":
        # Wi-Fi is gone ~0.1 s into a suspend, so the spiral has to play before asking for one
        try:
            ask("event sleep --wait", timeout=6)
        except OSError:
            pass
        if subprocess.run(["systemctl", "suspend"]).returncode != 0:
            try:
                ask("event login", timeout=2)  # suspend refused: don't leave the strip dark
            except OSError:
                pass
            sys.exit(1)
    elif cmd == "speed":
        try:
            v = float(args[0])
        except (IndexError, ValueError):
            sys.exit("usage: stark-govee speed <0.5-2.0>")
        update_config(anim_speed=round(clamp(v, 0.5, 2.0), 2))
        _poke()
    elif cmd == "oneshot":
        if not args or args[0] not in ANIMS:
            sys.exit("animations: " + ", ".join(ANIMS))
        if args[0] == "shutdown":
            try:
                ask("quiet", timeout=2)
            except OSError:
                pass
        play_direct(args[0], route_timeout=20.0 if args[0] == "boot" else 3.0)
    elif cmd == "mode":
        if not args or args[0] not in MODES:
            sys.exit("modes: auto, music, theme, off")
        update_config(mode=args[0])
        _poke()
    elif cmd == "theme":
        if not args:
            sys.exit("usage: stark-govee theme <primary> [accent]")
        prim = "#%02x%02x%02x" % hex_to_rgb(args[0])
        acc = "#%02x%02x%02x" % hex_to_rgb(args[1]) if len(args) > 1 else "#ffffff"
        cur = load_json(THEME, {})
        if cur.get("primary") != prim or cur.get("accent") != acc:
            save_json(THEME, {"primary": prim, "accent": acc})
            _poke()
    elif cmd == "color":
        if not args:
            sys.exit("usage: stark-govee color <hex>")
        update_config(mode="manual", manual_color="#%02x%02x%02x" % hex_to_rgb(args[0]))
        _poke()
    elif cmd == "status":
        try:
            print(json.dumps(json.loads(ask("status", timeout=2)), indent=2))
        except OSError:
            print("daemon not running")
            print(json.dumps(load_json(CONFIG, DEFAULTS), indent=2))
    elif cmd == "setup":
        cfg = load_json(CONFIG, {})
        for k, v in DEFAULTS.items():
            cfg.setdefault(k, v)
        ip = os.environ.get("GOVEE_IP") or cfg.get("ip")
        if not ip:
            devs = scan(3.0)
            ip = devs[0]["ip"] if devs else None
            if devs:
                print("found", devs[0].get("sku"), "at", ip)
        if not ip:
            sys.exit("no strip found: check LAN Control and UDP 4002 in the firewall")
        cfg["ip"] = ip
        save_json(CONFIG, cfg)
        if not THEME.exists():
            save_json(THEME, DEFAULT_THEME)
        print("saved", CONFIG)
    elif cmd == "home":
        if args and args[0] == "--clear":
            update_config(home_gateways=[])
            print("home cleared: lights run on any network (still needs docking)")
        else:
            macs = gateway_macs()
            if not macs:
                sys.exit("couldn't read your router's address; are you online?")
            cfg = load_json(CONFIG, {})
            homes = sorted(set(cfg.get("home_gateways") or []) | macs)
            update_config(home_gateways=homes)
            print("home network saved:", ", ".join(sorted(macs)))
        _poke()
    elif cmd == "override":
        cfg = load_json(CONFIG, {})
        ov = dict(cfg.get("strip_overrides") or {})
        if not args:
            for k, v in ov.items():
                print(f"{k} -> {v}")
            return
        key = _norm(args[0])
        if len(args) > 1 and args[1] == "--clear":
            ov.pop(key, None)
        elif len(args) > 1:
            ov[key] = _norm(args[1])
        else:
            sys.exit("usage: stark-govee override <hud> <strip>")
        update_config(strip_overrides=ov)
        _poke()
    elif cmd == "scan":
        for d in scan():
            print(f"{d.get('sku')}  {d['ip']}  {d.get('device')}")
    else:
        sys.exit(__doc__)


def _poke():
    try:
        ask("reload", timeout=2)
    except OSError:
        pass


if __name__ == "__main__":
    main(sys.argv[1:])
