"""MSI Mystic Light "761-byte" motherboard protocol (USB 0DB0:0076, page FF00).

Facts as implemented by OpenRGB's MSIMotherboard761Controller, which lists the
X870E GAMING PLUS WIFI (MS-7E70) as a tested board with zone-based direct mode:

* Feature report 0x50 (290 bytes used): a 1-byte id followed by 18 rows of 16 bytes.
  Row order: JARGB1, JARGB2, JARGB3, JAF, JPIPE1-5, JRGB1, JRGB2, ONBOARD1-6, ALL.
  Row byte 15 (0-based 14) is a flag byte and row byte 16 is the zone's LED count.
  GET 0x50 returns the controller's current setup; SET 0x50 writes it.
* Feature report 0x51: per-zone direct colors:
  [0x51, 0x09, hdr0, hdr1, 0x00, 0x00, led_count, R,G,B x 240]
  hdr0/hdr1: JARGB1 04/00, JARGB2 04/01, JARGB3 04/02, JAF (EZ Conn) 08/00.
Windows needs every buffer padded to the 761-byte feature length.
"""
from __future__ import annotations

SETUP_LEN = 290
ROW_NAMES = ["JARGB1", "JARGB2", "JARGB3", "JAF", "JPIPE1", "JPIPE2", "JPIPE3", "JPIPE4", "JPIPE5",
             "JRGB1", "JRGB2", "ONBOARD1", "ONBOARD2", "ONBOARD3", "ONBOARD4", "ONBOARD5", "ONBOARD6", "ALL"]
MAX_LEDS = 240

# zone id -> (row index in setup, hdr0, hdr1, display name)
DIRECT_ZONES = {
    "jargb1": (0, 0x04, 0x00, "JARGB_V2_1 header"),
    "jargb2": (1, 0x04, 0x01, "JARGB_V2_2 header"),
    "jargb3": (2, 0x04, 0x02, "JARGB_V2_3 header"),
    "jaf":    (3, 0x08, 0x00, "EZ Conn (JAF) header"),
}

# OpenRGB's tested setup rows for direct mode (from SignalRGB): active ARGB/JAF row.
_ACTIVE_ROW = bytes([0x09, 0xFF, 0x00, 0x00, 0x00, 0xFF, 0x00, 0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0x03, 0x15, 0x78])


def row(setup: bytes, idx: int) -> bytes:
    return setup[1 + 16 * idx: 1 + 16 * (idx + 1)]


def decode_setup(setup: bytes) -> dict[str, dict]:
    """Human-readable view of a GET 0x50 answer."""
    if len(setup) < SETUP_LEN or setup[0] != 0x50:
        raise ValueError("not a 0x50 setup report")
    out = {}
    for i, name in enumerate(ROW_NAMES):
        r = row(setup, i)
        if any(r):
            out[name] = {"mode": r[0], "color": r[1:4].hex(), "flags": r[14], "led_count": r[15], "raw": r.hex()}
    return out


def led_counts_from(setup: bytes) -> dict[str, int]:
    """LED counts per direct zone as configured by MSI Center (0 when the row is unused)."""
    return {z: row(setup, idx)[15] for z, (idx, *_rest) in DIRECT_ZONES.items()}


def build_direct_setup(led_counts: dict[str, int]) -> bytes:
    """Setup report that puts the four direct zones into direct mode, rows 4.. off (as OpenRGB does)."""
    buf = bytearray(SETUP_LEN)
    buf[0] = 0x50
    for zone, (idx, *_rest) in DIRECT_ZONES.items():
        r = bytearray(_ACTIVE_ROW)
        r[15] = max(1, min(MAX_LEDS, led_counts.get(zone, 0x78)))
        buf[1 + 16 * idx: 1 + 16 * (idx + 1)] = r
    return bytes(buf)


def build_zone_packet(zone: str, colors: list[tuple[int, int, int]], led_count: int) -> bytes:
    idx, hdr0, hdr1, _ = DIRECT_ZONES[zone]
    n = max(1, min(MAX_LEDS, led_count))
    body = bytearray(MAX_LEDS * 3)
    for i, (r, g, b) in enumerate(colors[:n]):
        body[3 * i: 3 * i + 3] = bytes((r, g, b))
    return bytes([0x51, 0x09, hdr0, hdr1, 0x00, 0x00, n]) + bytes(body)
