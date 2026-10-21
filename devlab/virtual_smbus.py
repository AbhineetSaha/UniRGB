"""A virtual AMD SMBus (PawnIO SmbusPIIX4 semantics) with ENE DRAM controllers and the chips that must never be touched.

It answers ioctl_smbus_xfer exactly as unirgb_smbus expects, records every transfer with its meaning, and
trips on anything outside the documented safe set: a transfer to an SPD hub (0x50-0x57) or power controller
(0x48-0x4F), the "save to controller" write, or a write to a register no supported tool writes.
Register facts: OpenRGB's ENE SMBus controller (see unirgb_smbus/ene.py).
"""
from __future__ import annotations

import time

WRITE, READ = 0, 1
PROTO_BYTE, PROTO_BYTE_DATA, PROTO_WORD_DATA = 1, 2, 3
NAME = b"AUDA0-E6K5-0101\0"
CONFIG = bytes.fromhex("01 01 08 08 00 00 00 00 00 00 00 08 00 00 00 00"    # as read from a real stick
                       "00 00 00 05 00 00 00 00 00 00 00 00 00 00 00 00"
                       "00 00 00 00 01 02 03 04 05 06 07 08 09 0A 0B 0C"
                       "0D 0E 0F 10 11 12 13 14 15 16 17 FF 00 00 FF 00")
DIRECT, MODE, APPLY, COLORS_DIRECT, COLORS_EFFECT = 0x8020, 0x8021, 0x80A0, 0x8100, 0x8160
FORBIDDEN = {range(0x48, 0x50): "PMIC (memory power controller)", range(0x50, 0x58): "SPD hub (memory settings)"}


class Tripwire(Exception):
    """A transfer that would be unsafe on real hardware. Never an OSError, so nothing swallows it."""


class VirtualEne:
    def __init__(self, effect=((255, 120, 0),) * 8):
        self.mem = {0x1000 + i: b for i, b in enumerate(NAME)}
        self.mem.update({0x1C00 + i: b for i, b in enumerate(CONFIG)})
        for i, (r, g, b) in enumerate(effect):   # the stick's stored effect: what it shows when not in direct mode
            self.mem.update({COLORS_EFFECT + 3 * i: r, COLORS_EFFECT + 3 * i + 1: b, COLORS_EFFECT + 3 * i + 2: g})
        self.pointer, self.direct_active, self.saved = None, False, False

    def leds(self) -> list[str]:
        base = COLORS_DIRECT if self.direct_active else COLORS_EFFECT
        return ["#%02x%02x%02x" % (self.mem.get(base + 3 * i, 0), self.mem.get(base + 3 * i + 2, 0),
                                   self.mem.get(base + 3 * i + 1, 0)) for i in range(8)]

    def xfer(self, rw: int, cmd: int, proto: int, data: list[int]) -> tuple[int | None, str]:
        """Returns (value read or None, meaning)."""
        if rw == READ and proto == PROTO_BYTE:
            return 0, "presence check"
        if rw == READ and proto == PROTO_BYTE_DATA and 0xA0 <= cmd <= 0xAF:
            return cmd - 0xA0, "signature read"
        if rw == READ and proto == PROTO_BYTE_DATA and cmd == 0x81:
            return self.mem.get(self.pointer, 0), f"read register 0x{self.pointer:04X}"
        if rw == WRITE and proto == PROTO_WORD_DATA and cmd == 0x00:
            self.pointer = ((data[0] & 0xFF) << 8) | (data[0] >> 8)
            return None, f"pointer -> 0x{self.pointer:04X}"
        if rw == WRITE and proto == PROTO_BYTE_DATA and cmd == 0x01:
            return None, self._write(self.pointer, data[0] & 0xFF)
        raise Tripwire(f"unexpected transaction rw={rw} command=0x{cmd:02X} protocol={proto}")

    def _write(self, reg: int, v: int) -> str:
        if reg == APPLY and v == 0xAA:
            self.saved = True
            raise Tripwire("SAVE to the controller's permanent memory (0xAA to 0x80A0)")
        if reg == APPLY and v == 0x01:
            self.direct_active = bool(self.mem.get(DIRECT, 0))
            return "apply (not saved)"
        if reg == DIRECT and v in (0, 1):
            self.mem[reg] = v
            return f"direct mode {'on' if v else 'off'} (takes effect on apply)"
        if COLORS_DIRECT <= reg < COLORS_DIRECT + 24:
            self.mem[reg] = v
            led, part = divmod(reg - COLORS_DIRECT, 3)
            return f"LED {led} {'RBG'[part]} = 0x{v:02X}"
        raise Tripwire(f"write 0x{v:02X} to undocumented register 0x{reg:04X}")


class VirtualPiix4:
    """Stands in for the PawnIO executor: execute(name, args, out_size)."""

    def __init__(self, controllers: dict[int, VirtualEne]):
        self.controllers = controllers
        self.trace: list[dict] = []
        self.busy_for = 0          # fault injection: the next N transfers fail as if the bus were busy

    def _log(self, addr, args, meaning, level="ok"):
        self.trace.append({"t": time.time(), "addr": f"0x{addr:02X}", "args": args, "meaning": meaning, "level": level})

    def execute(self, name: str, args: list[int], out_size: int) -> list[int]:
        if name == "ioctl_identity":
            return [0x5849495034, 0x0B00, 0x790B1022 | (0x7E701462 << 32)]
        if name == "ioctl_piix4_port_sel":
            return [0]
        addr, rw, cmd, proto, *data = args
        for rng, what in FORBIDDEN.items():
            if addr in rng:
                self._log(addr, args, f"TRIPWIRE: touched the {what}", "trip")
                raise Tripwire(f"transfer to 0x{addr:02X}, the {what}")
        if self.busy_for:
            self.busy_for -= 1
            self._log(addr, args, "bus busy (injected fault)", "fault")
            raise OSError(0xC00000B5, "bus busy")
        dev = self.controllers.get(addr)
        if dev is None:
            if rw == READ and proto == PROTO_BYTE:
                raise OSError(0xC0000001, "no ack")   # an empty address; probing these is normal
            self._log(addr, args, "no device answered", "fault")
            raise OSError(0xC0000001, "no ack")
        try:
            value, meaning = dev.xfer(rw, cmd, proto, data)
        except Tripwire as e:
            self._log(addr, args, f"TRIPWIRE: {e}", "trip")
            raise
        self._log(addr, args, meaning)
        return [] if value is None else [value]
