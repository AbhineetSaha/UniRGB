"""Read an ENE DRAM controller's name and configuration table. Changes no lighting.

ENE registers are 16-bit, reached through a pointer: an SMBus word write to command 0x00 sets the pointer
(register address byte-swapped), then a byte read from command 0x81 returns that register's value.
Source of these facts: OpenRGB ENESMBusInterface_i2c_smbus.cpp and ENESMBusController.h (facts only).
PawnIO's ioctl_smbus_xfer takes [address, 0 = write, command, 3 = word data, data] and sends data's low byte first.

That pointer write is the only write in this package, and it is fenced in four ways:
- only command 0x00 (the pointer). The value-write command 0x01 and block writes do not exist here;
- only registers in READ_WINDOWS (device name, configuration table);
- only addresses that answered the ENE signature in this run (and so are inside 0x70-0x77, never an SPD hub
  at 0x50-0x57 or a power controller at 0x48-0x4F);
- the pointer write and its read happen under one hold of the shared SMBus lock, so no other tool interleaves.
"""
from __future__ import annotations

from .bus import ENE_DRAM_ADDRESSES, PROTO_BYTE_DATA, READ

POINTER_CMD = 0x00          # sets the 16-bit register pointer
VALUE_CMD = 0x81            # reads the byte at the pointer
_POINTER_WRITE = 0          # I2C_SMBUS_WRITE, used only for the pointer
_PROTO_WORD_DATA = 3
NAME_REG, NAME_LEN = 0x1000, 16
CONFIG_REG, CONFIG_LEN = 0x1C00, 64
READ_WINDOWS = (range(NAME_REG, NAME_REG + NAME_LEN), range(CONFIG_REG, CONFIG_REG + CONFIG_LEN))
LED_COUNT_OFFSETS = (0x02, 0x03)   # OpenRGB: 0x02 on most versions, 0x03 on some (0107, 1110)


class EneReader:
    def __init__(self, executor, lock, confirmed: set[int]):
        if not confirmed <= set(ENE_DRAM_ADDRESSES):
            raise ValueError("confirmed addresses must be ENE DRAM addresses")
        self._ex, self._lock, self._confirmed = executor, lock, frozenset(confirmed)

    def read_register(self, addr: int, reg: int) -> int | None:
        if addr not in self._confirmed:
            raise ValueError(f"0x{addr:02X} did not answer as an ENE controller in this run")
        if not any(reg in w for w in READ_WINDOWS):
            raise ValueError(f"register 0x{reg:04X} is outside the read-only windows")
        swapped = ((reg << 8) & 0xFF00) | (reg >> 8)
        with self._lock:
            try:
                self._ex.execute("ioctl_smbus_xfer", [addr, _POINTER_WRITE, POINTER_CMD, _PROTO_WORD_DATA, swapped], 0)
                return self._ex.execute("ioctl_smbus_xfer", [addr, READ, VALUE_CMD, PROTO_BYTE_DATA], 1)[0] & 0xFF
            except OSError:
                return None

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
