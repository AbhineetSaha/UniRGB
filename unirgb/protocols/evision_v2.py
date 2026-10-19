"""Evision "V2" keyboard protocol (vendor collection FF1C:0092, report id 4, 64-byte reports).

Facts from OpenRGB's EVisionV2KeyboardController, confirmed on the Kreo Hive RGB
(320F:5055) with read-only commands on 2026-10-19 (checksum/command/offset echoed, status 0,
capabilities start with AA 55):

  request  [0]=0x04 [1..2]=checksum LE (sum of bytes 3..63) [3]=cmd [4]=size [5..6]=offset LE [7]=0 [8..]=data
  response echoes [0..6]; [7]=status (0 = ok); [8..] data (size in [4])

UniRGB uses only:
  0x03 READ_CAPABILITIES, 0x05 READ_CONFIG          (reads)
  0x12 SEND_DYNAMIC_COLORS, 0x13 END_DYNAMIC_COLORS  (live colors, never stored)
Direct colors must be refreshed at least every 200 ms or the keyboard falls back to its
stored effect, so a stopped or crashed UniRGB cannot leave the keyboard changed.
The profile/flash commands (0x01/0x02/0x06/0x0B) are deliberately not implemented.
"""
from __future__ import annotations

REPORT_ID = 0x04
PACKET = 64
CHUNK = PACKET - 8
READ_CAPABILITIES, READ_CONFIG = 0x03, 0x05
SEND_DYNAMIC_COLORS, END_DYNAMIC_COLORS = 0x12, 0x13
ALLOWED = {READ_CAPABILITIES, READ_CONFIG, SEND_DYNAMIC_COLORS, END_DYNAMIC_COLORS}
BLANK_SPACE = 6   # unused key slot; a 1-byte write there refreshes direct mode


class EvisionError(Exception):
    pass


def build(cmd: int, offset: int = 0, size: int = 0, data: bytes = b"") -> bytes:
    if cmd not in ALLOWED:
        raise EvisionError(f"command 0x{cmd:02x} is not allowed (no stored-profile writes)")
    if len(data) > CHUNK or size > CHUNK:
        raise EvisionError("payload too large for one packet")
    b = bytearray(PACKET)
    b[0], b[3], b[4], b[5], b[6] = REPORT_ID, cmd, size, offset & 0xFF, (offset >> 8) & 0xFF
    b[8:8 + len(data)] = data
    ck = sum(b[3:]) & 0xFFFF
    b[1], b[2] = ck & 0xFF, ck >> 8
    return bytes(b)


def check(request: bytes, response: bytes) -> bytes:
    """Validate an answer; returns its data bytes."""
    r = response
    if len(r) < 8 or r[0] != REPORT_ID or r[1:4] != request[1:4] or r[5:7] != request[5:7]:
        raise EvisionError("keyboard answer did not echo the request")
    if r[7] != 0:
        raise EvisionError(f"keyboard answered status {r[7]}")
    return r[8:8 + min(r[4], CHUNK)]


class EvisionTransport:
    def __init__(self, dev, timeout_ms: int = 500):
        self.dev, self.timeout_ms = dev, timeout_ms

    def query(self, cmd: int, offset: int = 0, size: int = 0, data: bytes = b"") -> bytes:
        req = build(cmd, offset, size, data)
        self.dev.write(req)
        for _ in range(5):
            resp = self.dev.read(self.timeout_ms)
            if resp and resp[0] == REPORT_ID:
                return check(req, resp)
        raise EvisionError("no answer from keyboard")

    def capabilities(self) -> dict:
        caps = self.query(READ_CAPABILITIES, 0, 7)
        if caps[:2] != b"\xAA\x55":
            raise EvisionError("capabilities signature missing")
        return {"map_size": caps[5], "macros_size": caps[6] * 0x80}

    def send_dynamic(self, buffer: bytes) -> None:
        for off in range(0, len(buffer), CHUNK):
            part = buffer[off:off + CHUNK]
            self.query(SEND_DYNAMIC_COLORS, off, len(part), part)

    def refresh(self) -> None:
        self.query(SEND_DYNAMIC_COLORS, BLANK_SPACE * 3, 1, b"\x00")

    def end(self) -> None:
        self.query(END_DYNAMIC_COLORS)
