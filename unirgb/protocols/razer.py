"""Razer HID control protocol (as documented by the openrazer project's driver).

90-byte report, sent as feature report 0 on the device's interface 0:
  0 status | 1 transaction id | 2-3 remaining packets (BE) | 4 protocol type
  5 data size | 6 command class | 7 command id | 8-87 arguments | 88 crc | 89 reserved
crc = XOR of bytes 2..87.
"""
from __future__ import annotations

import struct
import time

REPORT_LEN = 90
STATUS = {0x00: "new", 0x01: "busy", 0x02: "ok", 0x03: "failure", 0x04: "timeout", 0x05: "not supported"}
NOSTORE, VARSTORE = 0x00, 0x01
ZERO_LED = 0x00
SCROLL_LED, LOGO_LED = 0x01, 0x04
# Basilisk V3 Pro fw 2.50: get-brightness with ZERO_LED answers "failure"; LOGO/SCROLL answer.
READBACK_LED = LOGO_LED


class RazerProtocolError(Exception):
    pass


def crc(report: bytes) -> int:
    c = 0
    for b in report[2:88]:
        c ^= b
    return c


def build(command_class: int, command_id: int, data_size: int, args: bytes = b"", transaction_id: int = 0x1F) -> bytes:
    if len(args) > 80:
        raise ValueError("arguments exceed 80 bytes")
    r = bytearray(REPORT_LEN)
    r[1] = transaction_id
    r[5] = data_size
    r[6] = command_class
    r[7] = command_id
    r[8:8 + len(args)] = args
    r[88] = crc(r)
    return bytes(r)


def parse(resp: bytes) -> dict:
    if len(resp) < REPORT_LEN:
        raise RazerProtocolError("short response")
    return {"status": resp[0], "transaction_id": resp[1], "remaining": struct.unpack(">H", resp[2:4])[0],
            "data_size": resp[5], "class": resp[6], "id": resp[7], "args": resp[8:88], "crc_ok": resp[88] == crc(resp)}


# ---------- command builders (class, id, size per openrazer razerchromacommon.c) ----------
def get_firmware():           return build(0x00, 0x81, 0x02)
def get_serial():             return build(0x00, 0x82, 0x16)
def get_battery():            return build(0x07, 0x80, 0x02)
def get_brightness(store=VARSTORE, led=ZERO_LED):
    return build(0x0F, 0x84, 0x03, bytes([store, led]))
def set_brightness(value: int, store=NOSTORE, led=ZERO_LED):
    return build(0x0F, 0x04, 0x03, bytes([store, led, value & 0xFF]))
def effect_none(store=NOSTORE, led=ZERO_LED):
    return build(0x0F, 0x02, 0x06, bytes([store, led, 0x00]))
def effect_static(r: int, g: int, b: int, store=NOSTORE, led=ZERO_LED):
    return build(0x0F, 0x02, 0x09, bytes([store, led, 0x01, 0x00, 0x00, 0x01, r, g, b]))
def effect_custom_frame():
    return build(0x0F, 0x02, 0x0C, bytes([0x00, 0x00, 0x08]))
def set_custom_frame(row: int, start: int, stop: int, rgb: bytes):
    if len(rgb) != (stop - start + 1) * 3:
        raise ValueError("rgb length does not match column span")
    return build(0x0F, 0x03, 0x47, bytes([0x00, 0x00, row, start, stop]) + rgb)


# ---------- device settings (class/id/size per openrazer; layouts verified on the Basilisk V3 Pro) ----------
POLL_CODES = {1000: 0x01, 500: 0x02, 125: 0x08}
POLL_RATES = {v: k for k, v in POLL_CODES.items()}
DPI_MIN, DPI_MAX = 100, 30000


def _dpi(v: int) -> int:
    return max(DPI_MIN, min(DPI_MAX, int(v)))


def get_dpi(store=NOSTORE):
    return build(0x04, 0x85, 0x07, bytes([store]))
def set_dpi(x: int, y: int, store=NOSTORE):
    x, y = _dpi(x), _dpi(y)
    return build(0x04, 0x05, 0x07, bytes([store, x >> 8, x & 255, y >> 8, y & 255, 0, 0]))
def get_dpi_stages(store=VARSTORE):
    return build(0x04, 0x86, 0x26, bytes([store]))
def set_dpi_stages(stages: list[tuple[int, int]], active: int, store=VARSTORE):
    """Up to 5 (x, y) stages. Each entry is 7 bytes: index, x BE, y BE, 0, 0 (verified by read-back)."""
    if not 1 <= len(stages) <= 5 or not 1 <= active <= len(stages):
        raise ValueError("1-5 DPI stages and an active stage within range are required")
    body = bytearray([store, active, len(stages)])
    for i, (x, y) in enumerate(stages, 1):
        x, y = _dpi(x), _dpi(y)
        body += bytes([i, x >> 8, x & 255, y >> 8, y & 255, 0, 0])
    return build(0x04, 0x06, 0x26, bytes(body))
def get_poll_rate():
    return build(0x00, 0x85, 0x01)
def set_poll_rate(hz: int):
    if hz not in POLL_CODES:
        raise ValueError(f"polling rate must be one of {sorted(POLL_CODES)}")
    return build(0x00, 0x05, 0x01, bytes([POLL_CODES[hz]]))
def get_charging():
    return build(0x07, 0x84, 0x02)
def get_idle_time():
    return build(0x07, 0x83, 0x02)
def set_idle_time(seconds: int):
    s = max(60, min(900, int(seconds)))
    return build(0x07, 0x03, 0x02, bytes([s >> 8, s & 255]))
def get_low_battery():
    return build(0x07, 0x81, 0x01)


def decode_dpi(args) -> tuple[int, int]:
    return (args[1] << 8) | args[2], (args[3] << 8) | args[4]


def decode_stages(args) -> tuple[int, list[tuple[int, int]]]:
    n = args[2]
    return args[1], [((args[4 + 7 * i] << 8) | args[5 + 7 * i], (args[6 + 7 * i] << 8) | args[7 + 7 * i]) for i in range(n)]


class RazerTransport:
    """Request/response over feature reports with the waits openrazer uses for receivers."""

    def __init__(self, dev, wait_s: float = 0.06, retries: int = 5):
        self.dev, self.wait_s, self.retries = dev, wait_s, retries

    def transact(self, request: bytes) -> dict:
        last = None
        for _ in range(self.retries):
            self.dev.set_feature(b"\x00" + request)
            time.sleep(self.wait_s)
            raw = self.dev.get_feature(0x00)[1:1 + REPORT_LEN]
            resp = parse(raw)
            last = resp
            if resp["class"] != request[6] or resp["id"] != request[7]:
                time.sleep(0.01)    # answer to someone else's command (e.g. Synapse); retry
                continue
            if resp["status"] == 0x02:
                return resp
            if resp["status"] == 0x01:
                time.sleep(0.01)
                continue
            raise RazerProtocolError(f"device answered {STATUS.get(resp['status'], resp['status'])}")
        raise RazerProtocolError(f"no matching response after {self.retries} tries (last status "
                                 f"{STATUS.get(last['status'], last['status']) if last else 'none'})")
