"""MSI Mystic Light: read-only monitor.

Evidence on this machine:
  * HID 0DB0:0076 "MSI / MYSTIC LIGHT", vendor usage page FF00, 761-byte feature report
  * Mystic_Light_Service + LEDKeeper2/LightKeeperService (MSI Center) are running and
    own the controller
  * MSI's own log lists the zones it drives (ResetItem lines)

Writes are BLOCKED on purpose: there is no official MSI SDK on this machine
(MysticLight_SDK.dll is absent), and sending the community-documented 761-byte
feature report ourselves would race MSI Center's service, which writes to the same
controller. See docs/reverse-engineering-findings.md.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import Capabilities, Category, Connection, DeviceInfo, Support, Zone
from ..hostos.windows_system import service_state

MSI_VID = 0x0DB0
MSI_CENTER = Path(r"C:\Program Files (x86)\MSI\MSI Center")
LOG_PATH = MSI_CENTER / "Log" / "MysticLight_Test" / "MysticLight.txt"
_RESET_ITEM = re.compile(r"ResetItem\s*:\s*(\d+)\s*\(([^)]+)\)")


def parse_zones(log_text: str) -> list[str]:
    """Zone names from the most recent Mystic Light start-up in the log."""
    zones: list[str] = []
    for line in log_text.splitlines():
        m = _RESET_ITEM.search(line)
        if not m:
            continue
        idx, name = int(m.group(1)), m.group(2).strip()
        if idx == 0:
            zones = []          # a new start-up block begins at item 0
        if name.upper() != "SELECT ALL":
            zones.append(name)
    return zones


class MysticLightMonitor(DeviceAdapter):
    name = "msi"
    priority = 50
    control_path = "MSI Center UI -> MSI.CentralServer (local TCP) -> Mystic_Light_Service -> HID 0DB0 feature reports"

    def __init__(self, hid_provider: Callable[[], list] | None = None, log_path: Path = LOG_PATH,
                 service_query: Callable[[str], str] = service_state):
        self.hid_provider = hid_provider or (lambda: [])
        self.log_path = log_path
        self.service_query = service_query

    def health(self) -> AdapterHealth:
        st = self.service_query("Mystic_Light_Service")
        return AdapterHealth(st == "running", f"Mystic_Light_Service: {st}", {"service": st})

    def _zones(self) -> list[str]:
        try:
            # the log is a few hundred KB; only the tail holds the latest start-up
            data = self.log_path.read_bytes()[-64_000:].decode("utf-8", "replace")
        except OSError:
            return []
        return parse_zones(data)

    def discover(self) -> list[DiscoveredDevice]:
        ctrls = {}
        for h in self.hid_provider():
            if h.vid == MSI_VID and (h.usage_page or 0) >= 0xFF00:
                ctrls.setdefault(h.vidpid, h)
        svc = self.service_query("Mystic_Light_Service")
        zones = self._zones()
        out = []
        for vidpid, h in ctrls.items():
            evidence = [f"HID {vidpid} '{h.manufacturer} / {h.product}', usage page {h.usage_page:04X}, "
                        f"feature report {h.feature_len} bytes",
                        f"Mystic_Light_Service is {svc}"]
            if zones:
                evidence.append(f"MSI log lists zones: {', '.join(zones)}")
            out.append(DiscoveredDevice(
                DeviceInfo(f"msi:mystic:{vidpid}", "MSI Mystic Light controller", Category.MOTHERBOARD, self.name,
                           vendor="MSI", model=h.product, vidpid=vidpid, physical_key=f"usb:{vidpid}",
                           connection_path=self.control_path,
                           controlled_by=["MSI Center", "Mystic_Light_Service", "LEDKeeper2", "LightKeeperService"],
                           evidence=evidence),
                Capabilities(read_state=Support.BLOCKED, color=Support.BLOCKED, brightness=Support.BLOCKED,
                             zones=[Zone(z.lower().replace(" ", "_"), z, support=Support.BLOCKED) for z in zones],
                             zone_control=Support.BLOCKED, restore=Support.UNSUPPORTED,
                             notes=["Monitor only. MSI Center's service holds and writes this controller.",
                                    "To control it from UniRGB today, turn on Razer Chroma sync in MSI Center "
                                    "and use the Chroma Connect entry (experimental), or run the OpenRGB SDK "
                                    "server with MSI Center's lighting disabled.",
                                    f"Feature report size {h.feature_len} matches the controller family OpenRGB "
                                    "calls 'Mystic Light 761'. OpenRGB 1.0 detected it on this PC on 2026-10-06."]),
                Connection.MONITOR_ONLY))
        return out
