"""ENE DRAM RGB controllers: identification, and direct colors for one verified controller version.

ENE registers are 16-bit, reached through a pointer: an SMBus word write to command 0x00 sets the pointer
(register address byte-swapped), then a byte read from command 0x81 returns that register's value, or a byte
write to command 0x01 sets it.
Sources (facts only): OpenRGB ENESMBusInterface_i2c_smbus.cpp, ENESMBusController.cpp/.h (register map of
AUDA0-E6K5-0101: direct colors at 0x8100 in red, blue, green order). PawnIO's ioctl_smbus_xfer takes
[address, 0 = write / 1 = read, command, protocol, data] and sends a word's low byte first.

Fences, each covered by tests/test_smbus.py:
- addresses: only ones that answered the ENE signature in this run (so inside 0x70-0x77, never an SPD hub at
  0x50-0x57 or a power controller at 0x48-0x4F);
- reads: only the name and configuration registers (READ_WINDOWS);
- writes: only after the controller identified as SUPPORTED_NAME with LED_COUNT LEDs in this run, and only the
  registers and values in WRITE_RULES. The "save to the controller" value (0xAA to 0x80A0) is not among them, so
  nothing UniRGB writes survives a power cycle;
- every pointer write and the transfer after it happen under one hold of the shared SMBus lock.
"""
from __future__ import annotations

import time

from .bus import ENE_DRAM_ADDRESSES, PROTO_BYTE_DATA, READ

POINTER_CMD = 0x00          # sets the 16-bit register pointer (word write)
VALUE_READ_CMD = 0x81       # reads the byte at the pointer
VALUE_WRITE_CMD = 0x01      # writes the byte at the pointer
_WRITE_DIR = 0              # I2C_SMBUS_WRITE
_PROTO_WORD_DATA = 3
NAME_REG, NAME_LEN = 0x1000, 16
CONFIG_REG, CONFIG_LEN = 0x1C00, 64
READ_WINDOWS = (range(NAME_REG, NAME_REG + NAME_LEN), range(CONFIG_REG, CONFIG_REG + CONFIG_LEN))
LED_COUNT_OFFSETS = (0x02, 0x03)   # OpenRGB: 0x02 on most versions, 0x03 on some (0107, 1110)

SUPPORTED_NAME, LED_COUNT = "AUDA0-E6K5-0101", 8
DIRECT_REG = 0x8020         # 1 = direct colors, 0 = the controller's own stored effect
APPLY_REG, APPLY_VAL = 0x80A0, 0x01   # 0x01 applies without saving; 0xAA would save, and is never allowed
COLORS_REG = 0x8100         # direct colors, 3 bytes per LED: red, blue, green
WRITE_RULES = {**{COLORS_REG + i: None for i in range(LED_COUNT * 3)},   # None: any byte
               DIRECT_REG: {0, 1}, APPLY_REG: {APPLY_VAL}}


class EneReader:
    def __init__(self, executor, lock, confirmed: set[int]):
        if not confirmed <= set(ENE_DRAM_ADDRESSES):
            raise ValueError("confirmed addresses must be ENE DRAM addresses")
        self._ex, self._lock, self._confirmed = executor, lock, frozenset(confirmed)

    def _transfer(self, addr: int, reg: int, then: list[int], out_size: int) -> list[int] | None:
        """Point at reg, then run one more transfer, both under one hold of the lock."""
        if addr not in self._confirmed:
            raise ValueError(f"0x{addr:02X} did not answer as an ENE controller in this run")
        swapped = ((reg << 8) & 0xFF00) | (reg >> 8)
        with self._lock:
            try:
                self._ex.execute("ioctl_smbus_xfer", [addr, _WRITE_DIR, POINTER_CMD, _PROTO_WORD_DATA, swapped], 0)
                return self._ex.execute("ioctl_smbus_xfer", [addr, *then], out_size)
            except OSError:
                return None

    def read_register(self, addr: int, reg: int) -> int | None:
        if not any(reg in w for w in READ_WINDOWS):
            raise ValueError(f"register 0x{reg:04X} is outside the read-only windows")
        out = self._transfer(addr, reg, [READ, VALUE_READ_CMD, PROTO_BYTE_DATA], 1)
        return None if out is None else out[0] & 0xFF

    def _read_range(self, addr: int, start: int, n: int) -> list[int] | None:
        out = []
        for reg in range(start, start + n):
            v = self.read_register(addr, reg)
            if v is None:
                return None   # stop at the first failure; never keep poking a device that stopped answering
            out.append(v)
        return out

    def identify(self, addr: int) -> dict | None:
        name = self._read_range(addr, NAME_REG, NAME_LEN)
        if name is None:
            return None
        config = self._read_range(addr, CONFIG_REG, CONFIG_LEN)
        text = bytes(name).split(b"\0", 1)[0].decode("ascii", "replace")
        return {"address": addr, "name": text, "config": config,
                "led_count_candidates": None if config is None else [config[o] for o in LED_COUNT_OFFSETS]}


class EneLighting:
    """Direct colors on controllers that identified as SUPPORTED_NAME with LED_COUNT LEDs in this run."""

    def __init__(self, reader: EneReader):
        self._r, self._verified = reader, set()

    def verify(self, addr: int) -> dict | None:
        self._verified.discard(addr)   # a failed re-check withdraws an earlier verification
        info = self._r.identify(addr)
        if info and info["name"] == SUPPORTED_NAME and info["led_count_candidates"] == [LED_COUNT, LED_COUNT]:
            self._verified.add(addr)
        return info

    def write_register(self, addr: int, reg: int, value: int) -> bool:
        if addr not in self._verified:
            raise ValueError(f"0x{addr:02X} has not been verified as {SUPPORTED_NAME} with {LED_COUNT} LEDs")
        allowed = WRITE_RULES.get(reg, ())
        if not 0 <= value <= 0xFF or (allowed is not None and value not in allowed):
            raise ValueError(f"writing 0x{value:02X} to register 0x{reg:04X} is not allowed")
        return self._r._transfer(addr, reg, [_WRITE_DIR, VALUE_WRITE_CMD, PROTO_BYTE_DATA, value], 0) is not None

    def set_direct(self, addr: int, on: bool) -> bool:
        return self.write_register(addr, DIRECT_REG, int(on)) and self.write_register(addr, APPLY_REG, APPLY_VAL)

    def set_colors(self, addr: int, colors: list[tuple[int, int, int]]) -> bool:
        if len(colors) != LED_COUNT:
            raise ValueError(f"expected {LED_COUNT} colors")
        for i, (r, g, b) in enumerate(colors):
            for off, v in enumerate((r, b, g)):   # the controller's byte order
                if not self.write_register(addr, COLORS_REG + 3 * i + off, v):
                    return False
        return True


def color_test(lighting: EneLighting, addr: int, color=(255, 0, 0), hold_s: float = 10.0, sleep=time.sleep) -> str:
    """Step 2: show one color for hold_s seconds, then hand the stick back to its stored effect."""
    info = lighting.verify(addr)
    if addr not in lighting._verified:
        return f"0x{addr:02X} is not a verified {SUPPORTED_NAME} with {LED_COUNT} LEDs ({info}); nothing written"
    shown = False
    try:
        shown = lighting.set_colors(addr, [color] * LED_COUNT) and lighting.set_direct(addr, True)
        if shown:
            sleep(hold_s)
    finally:
        handed_back = lighting.set_direct(addr, False)   # always, even after an error
    if not handed_back:
        return ("could not switch direct mode off: the controller stopped answering. Its stored effect returns "
                "after a full power-off, because nothing was saved to it")
    return "shown, then handed back" if shown else "the controller stopped answering; direct mode switched off again"
