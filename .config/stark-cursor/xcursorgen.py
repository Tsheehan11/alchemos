#!/usr/bin/env python3
# Drop-in for xcursorgen (xorg-xcursorgen), used by build.sh when that isn't installed.
#   xcursorgen.py <config> <output>
# Config lines are xcursorgen's: "<nominal-size> <xhot> <yhot> <png> [<delay-ms>]",
# PNG paths relative to the config file's directory.
import os
import struct
import sys

from PIL import Image

IMAGE_TYPE = 0xFFFD0002


def chunk(size, xhot, yhot, png, delay):
    img = Image.open(png).convert("RGBA")
    w, h = img.size
    # XCursor wants premultiplied ARGB, little-endian
    rgba = img.tobytes()
    px = bytearray(len(rgba))
    for i in range(0, len(rgba), 4):
        r, g, b, a = rgba[i:i + 4]
        px[i:i + 4] = struct.pack("<I", (a << 24) | (r * a // 255 << 16) | (g * a // 255 << 8) | (b * a // 255))
    head = struct.pack("<9I", 36, IMAGE_TYPE, size, 1, w, h, min(xhot, w - 1), min(yhot, h - 1), delay)
    return size, head + bytes(px)


def main():
    if len(sys.argv) != 3:
        sys.exit("usage: xcursorgen.py <config> <output>")
    conf, out = sys.argv[1:]
    base = os.path.dirname(os.path.abspath(conf))
    chunks = []
    with open(conf) as f:
        for line in f:
            p = line.split()
            if len(p) < 4 or p[0].startswith("#"):
                continue
            delay = int(p[4]) if len(p) > 4 else 0
            chunks.append(chunk(int(p[0]), int(p[1]), int(p[2]), os.path.join(base, p[3]), delay))
    pos = 16 + 12 * len(chunks)
    toc, body = b"", b""
    for size, data in chunks:
        toc += struct.pack("<3I", IMAGE_TYPE, size, pos + len(body))
        body += data
    with open(out, "wb") as f:
        f.write(b"Xcur" + struct.pack("<3I", 16, 0x10000, len(chunks)) + toc + body)


main()
