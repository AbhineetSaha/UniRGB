"""RAM lighting (ENE DRAM controllers) through UniRGB's elevated hardware helper.

This adapter never touches the SMBus itself: it sends ram_list / ram_set / ram_release requests over the helper's
pipe, and the helper's RAM code (unirgb_smbus) enforces the fences. Colors are direct (live) only and never saved to
the sticks; restore and quit hand each stick back to its own stored effect.
"""
from __future__ import annotations

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Color, Confirmation, Connection, DeviceInfo,
                           LightingState, Support)


def _default_request(req: dict) -> dict | None:
    from ..hostos import pipe
    return pipe.request(req, timeout_s=3.0)


class RamEneAdapter(DeviceAdapter):
    name = "ram"
    priority = 5
    control_path = "UniRGB -> hardware helper (pipe) -> PawnIO SMBus module -> ENE DRAM controller"

    def __init__(self, enabled=lambda: False, start_helper=lambda: None, request=_default_request):
        self.enabled, self.start_helper, self.request = enabled, start_helper, request
        self._sticks: dict[str, int] = {}     # device id -> SMBus address
        self._direct: set[str] = set()
        self._problem = ""

    def health(self) -> AdapterHealth:
        if not self.enabled():
            return AdapterHealth(False, "RAM lighting is off in Settings")
        return AdapterHealth(not self._problem, self._problem or "through the hardware helper")

    def discover(self) -> list[DiscoveredDevice]:
        if not self.enabled():
            self._sticks, self._problem = {}, ""
            return []
        r = self.request({"op": "ram_list"})
        if r is None:   # helper not running yet: start it, keep what we had until it answers
            self.start_helper()
            self._problem = "waiting for the hardware helper"
            return [self._device(i, a, Connection.UNAVAILABLE) for i, a in self._sticks.items()]
        if not r.get("ok"):
            self._problem = r.get("error", "the helper refused the request")
            return []
        self._problem = r.get("problem", "")
        self._sticks = {f"ram:0x{s['address']:02X}": s["address"] for s in r.get("sticks", [])}
        names = {f"ram:0x{s['address']:02X}": s.get("name", "") for s in r.get("sticks", [])}
        return [self._device(i, a, Connection.CONNECTED, names[i]) for i, a in self._sticks.items()]

    def _device(self, dev_id: str, addr: int, conn: Connection, controller: str = "") -> DiscoveredDevice:
        slot = sorted(self._sticks.values()).index(addr) + 1
        return DiscoveredDevice(
            DeviceInfo(dev_id, f"RAM stick {slot}", Category.MEMORY, self.name, vendor="ENE controller",
                       model=controller or "ENE DRAM controller", physical_key=f"smbus:0x{addr:02X}",
                       connection_path=self.control_path, controlled_by=["UniRGB (hardware helper)"],
                       evidence=[f"ENE controller at SMBus 0x{addr:02X}" + (f", identified as {controller}" if controller else ""),
                                 "verified name and LED count before any write"]),
            Capabilities(read_state=Support.UNSUPPORTED, color=Support.EXPERIMENTAL, brightness=Support.EXPERIMENTAL,
                         effects=["static", "off"], restore=Support.SUPPORTED,
                         notes=["Live colors only: nothing is saved to the stick, so its own effect returns on "
                                "restore, on quit, or after a full power-off.",
                                "Brightness is applied by scaling the color.",
                                "Needs RAM lighting turned on in Settings (one-time admin setup)."]),
            conn)

    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        addr = self._sticks.get(device_id)
        if addr is None:
            return ApplyResult(False, message="RAM stick not ready")
        c = Color(0, 0, 0) if state.mode == "off" or state.color is None else state.color.scaled(state.brightness)
        r = self.request({"op": "ram_set", "address": addr, "color": c.hex()})
        if not r or not r.get("ok"):
            return ApplyResult(False, message=(r or {}).get("error", "the hardware helper did not answer"))
        self._direct.add(device_id)
        return ApplyResult(True, applied=state, confirmation=Confirmation.DEVICE_ACK,
                           message="the stick acknowledged every byte")

    def restore(self, device_id: str) -> ApplyResult:
        addr = self._sticks.get(device_id)
        if addr is None:
            return ApplyResult(False, message="RAM stick not ready")
        r = self.request({"op": "ram_release", "address": addr})
        self._direct.discard(device_id)
        if not r or not r.get("ok"):
            return ApplyResult(False, message=(r or {}).get("error", "the hardware helper did not answer"))
        return ApplyResult(True, message="the stick is back on its own stored effect")

    def shutdown(self) -> None:
        for dev_id in list(self._direct):
            try:
                self.restore(dev_id)
            except Exception:
                pass
