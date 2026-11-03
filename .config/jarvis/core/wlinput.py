"""
Pointer input for Jarvis's window control (stage 4): a virtual pointer through wlroots'
zwlr_virtual_pointer_v1, spoken straight over the Wayland socket with the same stdlib client as
core/wlcap.py. No uinput group, no root daemon (ydotool would need both), nothing to install.
Keyboard input is wtype (zwp_virtual_keyboard_v1), driven from core/control.py.

    with Pointer() as p:
        p.move(812, 430)          # layout (logical) coordinates, as hyprctl reports them
        p.click()                 # left; p.click("right"), p.click(count=2)
        p.scroll(3)               # wheel notches, + = down; p.scroll(-2, horizontal=True)

Hyprland maps absolute motion onto the bounding box of all monitors (logical pixels), so the box is
worked out from `hyprctl monitors -j`; core/control.py checks `hyprctl cursorpos` after every move.
"""
import json
import struct
import subprocess
import time

from . import wlcap

MGR = "zwlr_virtual_pointer_manager_v1"
BUTTONS = {"left": 0x110, "right": 0x111, "middle": 0x112}
# zwlr_virtual_pointer_v1 requests
MOTION_ABS, BUTTON, AXIS, FRAME, AXIS_SOURCE, AXIS_STOP, AXIS_DISCRETE, DESTROY = 1, 2, 3, 4, 5, 6, 7, 8
NOTCH = 15.0            # wheel step in surface pixels (what a mouse wheel sends on Hyprland)


class InputError(Exception):
    pass


def layout_box(mons=None):
    """(x0, y0, x1, y1) of all monitors in logical pixels (size / scale, swapped when rotated)."""
    if mons is None:
        mons = json.loads(subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, timeout=3).stdout or "[]")
    if not mons:
        raise InputError("no monitors")
    xs0, ys0, xs1, ys1 = [], [], [], []
    for m in mons:
        s = m.get("scale") or 1
        w, h = m["width"] / s, m["height"] / s
        if m.get("transform", 0) % 2:
            w, h = h, w
        xs0.append(m["x"]); ys0.append(m["y"]); xs1.append(m["x"] + w); ys1.append(m["y"] + h)
    return min(xs0), min(ys0), max(xs1), max(ys1)


class Pointer:
    def __init__(self, timeout=3.0):
        self.c = wlcap._Conn(timeout)
        try:
            reg, g = wlcap._globals(self.c)
            mgr = wlcap._bind(self.c, reg, g, MGR, 1)
        except wlcap.CaptureError as e:
            self.c.close()
            raise InputError(str(e)) from None
        self.ptr = self.c.new_id()
        self.c.send(mgr, 0, struct.pack("<II", 0, self.ptr))     # create_virtual_pointer(seat = default)
        self.t0 = time.monotonic()
        self.box = layout_box()

    def _ms(self):
        return int((time.monotonic() - self.t0) * 1000) & 0xFFFFFFFF

    def _send(self, op, payload=b""):
        try:
            self.c.send(self.ptr, op, payload)
        except OSError as e:
            raise InputError(f"pointer: {e}") from None

    def move(self, x, y):
        x0, y0, x1, y1 = self.box
        w, h = int(round(x1 - x0)), int(round(y1 - y0))
        px = min(max(int(round(x - x0)), 0), w - 1)
        py = min(max(int(round(y - y0)), 0), h - 1)
        self._send(MOTION_ABS, struct.pack("<IIIII", self._ms(), px, py, w, h))
        self._send(FRAME)

    def button(self, which="left", pressed=True):
        self._send(BUTTON, struct.pack("<III", self._ms(), BUTTONS[which], 1 if pressed else 0))
        self._send(FRAME)

    def click(self, which="left", count=1):
        for i in range(count):
            self.button(which, True)
            time.sleep(0.04)
            self.button(which, False)
            if i + 1 < count:
                time.sleep(0.08)

    def scroll(self, notches, horizontal=False):
        """One wheel notch per event, 30 ms apart (axis_discrete + its pixel value, source wheel)."""
        axis = 1 if horizontal else 0
        step = 1 if notches > 0 else -1
        for _ in range(abs(int(notches))):
            self._send(AXIS_SOURCE, struct.pack("<I", 0))
            self._send(AXIS_DISCRETE, struct.pack("<IIii", self._ms(), axis, int(step * NOTCH * 256), step))
            self._send(FRAME)
            time.sleep(0.03)

    def close(self):
        try:
            self.c.send(self.ptr, DESTROY)
            # a round trip, so the compositor has handled everything before the socket goes
            cb = self.c.new_id()
            self.c.send(1, 0, struct.pack("<I", cb))
            self.c.deadline = time.monotonic() + 1.0
            for obj, op, _ in self.c.events():
                if obj == cb:
                    break
        except Exception:
            pass
        self.c.close()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def cursor():
    """Where the cursor is now, in layout coordinates (hyprctl cursorpos: "812, 430")."""
    out = subprocess.run(["hyprctl", "cursorpos"], capture_output=True, text=True, timeout=2).stdout
    try:
        x, y = (float(v) for v in out.strip().split(","))
        return x, y
    except ValueError:
        raise InputError(f"cursorpos: {out.strip()[:60]}") from None
