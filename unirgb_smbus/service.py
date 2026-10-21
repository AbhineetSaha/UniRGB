"""RAM lighting for the hardware helper: find verified ENE sticks once, then set colors or hand them back.

Everything goes through ene.EneLighting's fences. On top of those:
- 0x77 is never used: ENE controllers all answer there until a tool remaps them, so one write would reach every
  stick at once, and reads would collide. UniRGB does not remap; it uses controllers already at 0x70-0x76.
- requests name a stick by address, and only sticks verified in this session are accepted.
"""
from __future__ import annotations

from .bus import AMD_VENDOR, ReadOnlySmbus
from .ene import LED_COUNT, EneLighting, EneReader
from .probe import probe

USABLE_ADDRESSES = range(0x70, 0x77)   # 0x77 excluded, see above
MODULE_NAME = "SmbusPIIX4.bin"


class RamService:
    def __init__(self, executor, lock):
        self._ex, self._lock = executor, lock
        self._lighting: EneLighting | None = None
        self.sticks: list[dict] = []
        self.problem = ""
        self._direct: set[int] = set()

    def scan(self) -> dict:
        bus = ReadOnlySmbus(self._ex, self._lock)
        if bus.identity()["pci_vendor"] != AMD_VENDOR:
            self.problem, self.sticks = "not an AMD SMBus controller", []
            return self.listing()
        found = probe(bus)
        confirmed = {f["address"] for f in found if f["ene"] and f["address"] in USABLE_ADDRESSES}
        self._lighting = EneLighting(EneReader(self._ex, self._lock, confirmed))
        self.sticks = []
        for addr in sorted(confirmed):
            info = self._lighting.verify(addr)
            if addr in self._lighting._verified:
                self.sticks.append({"address": addr, "name": info["name"], "leds": LED_COUNT})
        unremapped = any(f["address"] == 0x77 and f["ene"] for f in found)
        self.problem = "" if self.sticks else (
            "RAM controllers are still at their shared start-up address (0x77); UniRGB does not remap them"
            if unremapped else "no supported RAM lighting controllers found")
        return self.listing()

    def listing(self) -> dict:
        return {"ok": True, "sticks": self.sticks, "problem": self.problem}

    def _stick(self, addr) -> int:
        if not any(s["address"] == addr for s in self.sticks):
            raise ValueError("unknown stick")
        return addr

    def set_color(self, addr, rgb: tuple[int, int, int]) -> bool:
        addr = self._stick(addr)
        ok = self._lighting.set_colors(addr, [rgb] * LED_COUNT) and self._lighting.set_direct(addr, True)
        if ok:
            self._direct.add(addr)
        return ok

    def release(self, addr) -> bool:
        addr = self._stick(addr)
        self._direct.discard(addr)
        return self._lighting.set_direct(addr, False)

    def release_all(self) -> None:
        for addr in sorted(self._direct):
            try:
                self.release(addr)
            except Exception:
                pass
