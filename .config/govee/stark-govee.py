#!/usr/bin/env python3
"""stark-govee: STARK OS ambient lighting for a Govee LAN strip (H618C).

The daemon owns the strip: it follows the HUD theme colour, pulses to music
(via cava), and plays boot / login / lock / unlock / logout / shutdown /
sleep animations. Govee's LAN API is single-zone, so every effect is a
whole-strip colour.

Usage:
  stark-govee daemon                    run the light daemon (Hyprland exec-once)
  stark-govee event <name> [--wait]     boot|login|lock|unlock|logout|shutdown|sleep|wake
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
import json, math, os, queue, shutil, signal, socket, struct, subprocess, sys, threading, time
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
}
DEFAULT_THEME = {"primary": "#00dcff", "accent": "#ffffff"}
MODES = ("auto", "music", "theme", "off", "manual")
BLACK, WHITE = (0, 0, 0), (255, 255, 255)


def log(*a):
    print("[stark-govee]", *a, file=sys.stderr, flush=True)


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


def theme_colors(theme, cfg=None):
    ov = {}
    for k, v in ((cfg or {}).get("strip_overrides") or {}).items():
        try:
            ov[_norm(k)] = _norm(v)
        except ValueError:
            pass
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


def should_run(cfg):
    if cfg.get("require_docked", True) and not docked():
        return False
    return at_home(cfg)


def _calib(cfg):
    try:
        g = float(cfg.get("gamma", 2.2))
        wb = tuple(float(x) for x in cfg.get("white_balance", (1, 1, 1)))[:3]
        return clamp(g, 1.0, 3.5), wb if len(wb) == 3 else (1.0, 1.0, 1.0)
    except (TypeError, ValueError):
        return 2.2, (1.0, 1.0, 1.0)


class Strip:
    def __init__(self, ip, max_fps, gamma=2.2, wb=(1.0, 1.0, 1.0)):
        self.gamma, self.wb = gamma, tuple(wb)
        self.ip = ip
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.min_dt = 1.0 / max(1, max_fps)
        self.last_t = 0.0
        self.last_rgb = None
        self.quiet = False

    def send(self, cmd, data):
        if self.quiet or not self.ip:
            return
        try:
            self.sock.sendto(json.dumps({"msg": {"cmd": cmd, "data": data}}).encode(), (self.ip, CMD_PORT))
        except OSError:
            pass  # off-network / no route: stay silent

    def power(self, on):
        self.send("turn", {"value": 1 if on else 0})
        self.last_rgb = None

    def brightness(self, v):
        self.send("brightness", {"value": int(clamp(v, 1, 100))})

    def rgb(self, c, force=False):
        c = tuple(int(round(clamp(x, 0, 255))) for x in correct(c, self.gamma, self.wb))
        now = time.monotonic()
        if not force:
            if now - self.last_t < self.min_dt:
                return
            if c == self.last_rgb and now - self.last_t < 5.0:  # keepalive resend every 5 s
                return
        self.send("colorwc", {"color": {"r": c[0], "g": c[1], "b": c[2]}, "colorTemInKelvin": 0})
        self.last_rgb, self.last_t = c, now


# ---------- animations ----------
# Each yields an RGB tuple per frame, or "on" / "off".
def _n(sec, fps):
    return max(1, int(round(sec * fps)))


def ease(t):
    return 1 - (1 - t) ** 3


def fade(a, b, sec, fps, curve=ease):
    n = _n(sec, fps)
    for i in range(1, n + 1):
        yield mix(a, b, curve(i / n))


def hold(c, sec, fps):
    for _ in range(_n(sec, fps)):
        yield c


def flicker(p, levels, fps):
    for k in levels:
        yield from hold(scale(p, k), 0.09, fps)


def anim_boot(p, a, cur, fps):  # arc reactor ignition
    yield "on"
    yield from hold(BLACK, 0.3, fps)
    yield from flicker(p, (0.5, 0, 0.8, 0, 0.3, 0), fps)
    yield from fade(BLACK, scale(p, 0.25), 0.5, fps)
    yield from fade(scale(p, 0.25), WHITE, 0.5, fps)
    yield from fade(WHITE, p, 1.2, fps)


def anim_login(p, a, cur, fps):
    yield "on"
    yield from fade(cur, scale(p, 0.2), 0.3, fps)
    yield from flicker(p, (0.6, 0.15, 0.9), fps)
    yield from fade(p, WHITE, 0.25, fps)
    yield from fade(WHITE, p, 1.0, fps)


def anim_unlock(p, a, cur, fps):  # security doors open
    yield "on"
    yield from fade(cur, WHITE, 0.3, fps)
    yield from fade(WHITE, p, 0.9, fps)


def anim_lock(p, a, cur, fps):  # doors close, settle into standby glow
    yield from fade(cur, p, 0.2, fps)
    yield from fade(p, scale(p, 0.1), 1.2, fps)


def anim_logout(p, a, cur, fps):
    yield from fade(cur, WHITE, 0.25, fps)
    yield from fade(WHITE, p, 0.4, fps)
    yield from fade(p, BLACK, 1.3, fps)
    yield "off"


def anim_shutdown(p, a, cur, fps):  # reactor power-down
    yield from fade(cur, p, 0.2, fps)
    yield from flicker(p, (0.4, 1.0, 0.25, 0.7, 0.1), fps)
    yield from fade(scale(p, 0.5), BLACK, 1.4, fps)
    yield "off"


def anim_sleep(p, a, cur, fps):
    yield from fade(cur, BLACK, 0.6, fps)
    yield "off"


def anim_wake(p, a, cur, fps):
    yield "on"


ANIMS = {"boot": anim_boot, "login": anim_login, "unlock": anim_unlock, "lock": anim_lock,
         "logout": anim_logout, "shutdown": anim_shutdown, "sleep": anim_sleep, "wake": anim_wake}
GOES_DARK = {"logout", "shutdown", "sleep"}


# ---------- daemon ----------
class Daemon:
    def __init__(self):
        self.cfg = load_json(CONFIG, DEFAULTS)
        self.theme = load_json(THEME, DEFAULT_THEME)
        self.fps = int(clamp(self.cfg.get("max_fps", 12), 2, 30))
        self.strip = Strip(resolve_ip(self.cfg), self.fps, *_calib(self.cfg))
        self.q = queue.Queue()
        self.running = True
        self.locked = self.asleep = False
        self.powered = None
        self.cur = BLACK
        self.anim = self.anim_done = self.anim_after = None
        self.wake_until = 0.0
        self.parked = False       # not docked at home: strip left alone
        self.gate_vote, self.last_gate = 0, 0.0
        self.mtimes = {}
        self.last_poll = self.last_scan = 0.0
        # audio state (written by the cava thread)
        self.cava = None
        self.level = self.flash = self.bass_avg = 0.0
        self.last_sound = self.last_frame = self.last_beat = 0.0

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
                "parked": self.parked, "docked": docked(), "home": at_home(self.cfg)}

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
        self.cfg = load_json(CONFIG, DEFAULTS)
        self.theme = load_json(THEME, DEFAULT_THEME)
        if self.cfg.get("ip"):
            self.strip.ip = os.environ.get("GOVEE_IP") or self.cfg["ip"]
        self.strip.gamma, self.strip.wb = _calib(self.cfg)
        self.strip.last_rgb = None  # resend with new calibration

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
            if cmd == "reload":
                self.reload()
            elif cmd == "quiet":  # system shutdown takes over the strip
                self.strip.quiet = True
                self.running = False
            done.set()

    def event(self, name, done):
        now = time.monotonic()
        if name == "lock":
            self.locked = True
        elif name in ("unlock", "login", "boot"):
            if name == "unlock":
                self.locked = False
            self.asleep = False
        elif name == "wake":
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

    def start_anim(self, name, done=None):
        if self.anim_done:
            self.anim_done.set()  # interrupted: release any waiter, skip its after-action
        p, a = theme_colors(self.theme, self.cfg)
        self.anim = ANIMS[name](p, a, self.cur, self.fps)
        self.anim_done = done
        self.anim_after = name

    def finish_anim(self):
        if self.anim_after in GOES_DARK:
            self.asleep = True
        if self.anim_done:
            self.anim_done.set()
        self.anim = self.anim_done = self.anim_after = None

    # --- docked-at-home gate ---
    def gate(self):
        now = time.monotonic()
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
                self.start_anim("sleep")

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
        if self.strip.quiet:
            return
        if self.anim:
            try:
                f = next(self.anim)
            except StopIteration:
                self.finish_anim()
                return
            if f in ("on", "off"):
                self.set_power(f == "on")
            else:
                self.cur = f
                self.strip.rgb(f, force=True)
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
        self.cur = mix(self.cur, t, 0.55 if self.music_active() else 0.2)
        self.strip.rgb(self.cur)

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
        tick = 1.0 / self.fps
        while self.running:
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


def play_direct(name, route_timeout=3.0):
    cfg = load_json(CONFIG, DEFAULTS)
    if cfg.get("mode") == "off" and name not in GOES_DARK:
        return
    ip = resolve_ip(cfg, allow_scan=False)
    if not ip or not wait_for_route(ip, route_timeout):
        log("strip not reachable; skipping", name)
        return
    if not should_run(cfg):
        log("not docked at home; skipping", name)
        return
    fps = int(clamp(cfg.get("max_fps", 12), 2, 30))
    strip = Strip(ip, fps, *_calib(cfg))
    p, a = theme_colors(load_json(THEME, DEFAULT_THEME), cfg)
    start = BLACK if name in ("boot", "login", "wake") else p
    if name == "boot":
        strip.brightness(cfg.get("device_brightness", 100))
    for f in ANIMS[name](p, a, start, fps):
        if f in ("on", "off"):
            strip.power(f == "on")
        else:
            strip.rgb(f, force=True)
        time.sleep(1.0 / fps)
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
        try:
            ask(" ".join(["event"] + args))
        except OSError:
            play_direct(args[0])  # no daemon (e.g. suspend before login): animate directly
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
