"""Renders the UniRGB logo to unirgb/ui/logo.ico: a "U" (Uni) drawn as one
red -> green -> blue stroke (RGB) on a dark rounded tile.

Standard library only. Run: python tools/make_icon.py
"""
import math
import struct
import zlib
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "unirgb" / "ui" / "logo.ico"
SIZES = (16, 24, 32, 48, 64, 128, 256)
SS = 3   # supersampling per axis, for smooth edges
BG = (14, 16, 20)
HALF_W = 0.065                                  # half the stroke width
LX, RX, TOP, CY, R = 0.30, 0.70, 0.22, 0.56, 0.20   # U geometry in the unit square
STOPS = [(0.0, (255, 59, 48)), (0.5, (52, 199, 89)), (1.0, (10, 132, 255))]
SEG, ARC = CY - TOP, math.pi * R
TOTAL = 2 * SEG + ARC


def colour(t: float):
    for (t0, c0), (t1, c1) in zip(STOPS, STOPS[1:]):
        if t <= t1:
            k = (t - t0) / (t1 - t0)
            return tuple(round(a + (b - a) * k) for a, b in zip(c0, c1))
    return STOPS[-1][1]


def nearest_on_u(x: float, y: float):
    """(distance to the U's centre line, position along it from 0 to 1)."""
    yy = min(max(y, TOP), CY)
    best = min((math.hypot(x - LX, y - yy), (yy - TOP) / TOTAL),
               (math.hypot(x - RX, y - yy), (TOTAL - (yy - TOP)) / TOTAL))
    if y >= CY:   # bottom half circle
        a = math.atan2(y - CY, x - 0.5)
        best = min(best, (abs(math.hypot(x - 0.5, y - CY) - R), (SEG + (math.pi - a) * R) / TOTAL))
    return best


def pixel(fx: float, fy: float):
    """Colour at a point in the unit square, or None outside the rounded tile."""
    r = 0.22   # corner radius
    qx, qy = abs(fx - 0.5) - (0.5 - r), abs(fy - 0.5) - (0.5 - r)
    if math.hypot(max(qx, 0), max(qy, 0)) > r:
        return None
    d, t = nearest_on_u(fx, fy)
    return colour(t) if d <= HALF_W else BG


def render(n: int) -> bytes:
    rows = []
    for y in range(n):
        row = bytearray([0])   # PNG filter byte: none
        for x in range(n):
            acc, cover = [0, 0, 0], 0
            for sy in range(SS):
                for sx in range(SS):
                    c = pixel((x + (sx + 0.5) / SS) / n, (y + (sy + 0.5) / SS) / n)
                    if c:
                        cover += 1
                        acc = [a + b for a, b in zip(acc, c)]
            row += bytes([a // cover for a in acc] if cover else [0, 0, 0]) + bytes([255 * cover // (SS * SS)])
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def main():
    pngs = [render(n) for n in SIZES]
    head = struct.pack("<HHH", 0, 1, len(pngs))
    offset, entries = 6 + 16 * len(pngs), b""
    for n, png in zip(SIZES, pngs):
        entries += struct.pack("<BBBBHHII", n % 256, n % 256, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    OUT.write_bytes(head + entries + b"".join(pngs))
    print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
