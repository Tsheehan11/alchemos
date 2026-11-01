"""
A tiny pure-Python Wayland client for one thing: copying a single window's pixels into memory with
Hyprland's hyprland_toplevel_export_v1 (it renders the window itself, so it works while the window is
covered or on another workspace). No files: the frame lives in a memfd-backed wl_shm buffer that is
mapped, copied into a numpy array and closed.

    img = capture_window("0x55a7f545b3d0")   # hyprctl clients address → H×W×3 uint8 RGB, or raises CaptureError

Same wire format as ~/.claude/.../memory/vptr.py (the virtual pointer client); fds go over SCM_RIGHTS.
"""
import array
import mmap
import os
import socket
import struct
import time

import numpy as np

EXPORT = "hyprland_toplevel_export_manager_v1"

# wl_shm formats → (byte order of the 4 channels in memory, little endian)
FORMATS = {0: "BGRA", 1: "BGRX", 0x34324241: "RGBA", 0x34324258: "RGBX"}


class CaptureError(Exception):
    pass


def _s(txt):
    b = txt.encode() + b"\0"
    return struct.pack("<I", len(b)) + b + b"\0" * ((4 - len(b) % 4) % 4)


class _Conn:
    def __init__(self, timeout=3.0):
        path = os.path.join(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"),
                            os.environ.get("WAYLAND_DISPLAY", "wayland-1"))
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(timeout)
        self.sock.connect(path)
        self.next_id = 2
        self.buf = b""
        self.deadline = time.monotonic() + timeout

    def new_id(self):
        i = self.next_id
        self.next_id += 1
        return i

    def send(self, obj, op, payload=b"", fd=None):
        data = struct.pack("<II", obj, ((8 + len(payload)) << 16) | op) + payload
        if fd is None:
            self.sock.sendall(data)
        else:
            self.sock.sendmsg([data], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array("i", [fd]))])

    def events(self):
        """Yield (object, opcode, body) until the caller stops or the deadline passes."""
        while True:
            while len(self.buf) >= 8:
                obj, so = struct.unpack("<II", self.buf[:8])
                size, op = so >> 16, so & 0xFFFF
                if len(self.buf) < size:
                    break
                body, self.buf = self.buf[8:size], self.buf[size:]
                if obj == 1 and op == 0:            # wl_display.error
                    code = struct.unpack("<I", body[4:8])[0]
                    why = body[12:].rstrip(b"\0").decode(errors="replace")
                    raise CaptureError(f"wayland error {code}: {why}")
                yield obj, op, body
            left = self.deadline - time.monotonic()
            if left <= 0:
                raise CaptureError("timed out")
            self.sock.settimeout(left)
            try:
                chunk = self.sock.recv(65536)
            except socket.timeout:
                raise CaptureError("timed out") from None
            if not chunk:
                raise CaptureError("compositor closed the connection")
            self.buf += chunk

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass


def _globals(c):
    reg, cb = c.new_id(), c.new_id()
    c.send(1, 1, struct.pack("<I", reg))     # get_registry
    c.send(1, 0, struct.pack("<I", cb))      # sync
    g = {}
    for obj, op, body in c.events():
        if obj == reg and op == 0:
            name, ln = struct.unpack("<II", body[:8])
            iface = body[8:8 + ln - 1].decode()
            ver = struct.unpack("<I", body[8 + ((ln + 3) & ~3):][:4])[0]
            g[iface] = (name, ver)
        elif obj == cb and op == 0:
            return reg, g


def _bind(c, reg, g, iface, version):
    if iface not in g:
        raise CaptureError(f"compositor has no {iface}")
    i = c.new_id()
    c.send(reg, 0, struct.pack("<I", g[iface][0]) + _s(iface) + struct.pack("<II", min(version, g[iface][1]), i))
    return i


def handle_of(address):
    """hyprctl's "0x55a7f545b3d0" → the export protocol's handle (the low 32 bits of the window pointer)."""
    return int(str(address), 16) & 0xFFFFFFFF


def capture_window(address, timeout=3.0):
    """The window's current frame as an H×W×3 RGB uint8 array (its own buffer size, cursor not drawn)."""
    c = _Conn(timeout)
    fd = -1
    try:
        reg, g = _globals(c)
        mgr = _bind(c, reg, g, EXPORT, 1)
        shm = _bind(c, reg, g, "wl_shm", 1)
        frame = c.new_id()
        c.send(mgr, 0, struct.pack("<IiI", frame, 0, handle_of(address)))   # capture_toplevel(frame, no cursor, handle)
        offers = []
        for obj, op, body in c.events():
            if obj != frame:
                continue
            if op == 0:                                                   # buffer(format, w, h, stride)
                offers.append(struct.unpack("<IIII", body[:16]))
            elif op == 4:
                raise CaptureError("the compositor refused (window gone or not capturable)")
            elif op == 6:                                                 # buffer_done
                break
        usable = [o for o in offers if o[0] in FORMATS]
        if not usable:
            raise CaptureError(f"no shared-memory format offered ({[hex(o[0]) for o in offers]})")
        fmt, w, h, stride = usable[0]
        size = stride * h
        fd = os.memfd_create("jarvis-frame", os.MFD_CLOEXEC)
        os.ftruncate(fd, size)
        pool, buf = c.new_id(), c.new_id()
        c.send(shm, 0, struct.pack("<Ii", pool, size), fd=fd)   # create_pool(id, fd, size)
        c.send(pool, 0, struct.pack("<IiiiiI", buf, 0, w, h, stride, fmt))                        # create_buffer
        c.send(frame, 0, struct.pack("<Ii", buf, 1))                                              # copy(buffer, ignore_damage)
        flags = 0
        for obj, op, body in c.events():
            if obj != frame:
                continue
            if op == 2:
                flags = struct.unpack("<I", body[:4])[0]
            elif op == 3:                                                 # ready
                break
            elif op == 4:
                raise CaptureError("copy failed")
        with mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ) as m:
            raw = np.frombuffer(m, dtype=np.uint8, count=size).reshape(h, stride)[:, :w * 4].reshape(h, w, 4).copy()
        order = FORMATS[fmt]
        img = raw[:, :, [order.index("R"), order.index("G"), order.index("B")]]
        if flags & 1:                                                     # y_invert
            img = img[::-1]
        for obj, op in ((frame, 1), (buf, 0), (pool, 1)):                 # destroy
            try:
                c.send(obj, op)
            except OSError:
                pass
        return np.ascontiguousarray(img)
    except OSError as e:
        raise CaptureError(f"{type(e).__name__}: {e}") from None
    finally:
        if fd >= 0:
            os.close(fd)
        c.close()
