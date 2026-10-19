"""Ant Esports AIO pump-cap 7-segment display (USB HID 5131:2007).

Wire format as implemented by the MIT-licensed neonvarun/AntEsports-Cooler-Controller
(ICE-Infinity / ICE-Flow family): one 65-byte HID *output* report
  [0] report id 0x00  [1] opcode 0x40  [2] temperature (0-100, bit 7 = Fahrenheit flag)
  [3..23] optional load/clock/fan/power/RAM/disk fields (big-endian), not shown by the 7-segment panel
Note: 5131:2007 is a generic chip reused by other vendors with different framing.
"""
from __future__ import annotations

REPORT_LEN = 65
OPCODE = 0x40
ANTI_BLINK = ("cap84", "compress", "raw")


def shape_temperature(temp_c: float, anti_blink: str = "cap84") -> int:
    """The stock firmware flashes at 85 C and above; cap or compress like the reference app."""
    t = max(0.0, min(110.0, temp_c))
    if anti_blink == "cap84" and t >= 85:
        t = 84
    elif anti_blink == "compress" and t > 75:
        t = 75 + (min(t, 100) - 75) * 9 / 25
    return int(round(t))


def build_packet(temp_c: float, fahrenheit: bool = False, anti_blink: str = "cap84") -> bytes:
    t = shape_temperature(temp_c, anti_blink)
    if fahrenheit:
        t = round(t * 9 / 5 + 32)
    pkt = bytearray(REPORT_LEN)
    pkt[1] = OPCODE
    pkt[2] = (min(100, t) & 0x7F) | (0x80 if fahrenheit else 0)
    return bytes(pkt)


def build_blank() -> bytes:
    pkt = bytearray(REPORT_LEN)
    pkt[1] = OPCODE
    return bytes(pkt)
