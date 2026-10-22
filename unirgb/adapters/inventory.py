"""Read-only inventory of everything else: HID devices, GPUs, DIMMs.

Every device here is monitor-only. When a control adapter exposes the same
hardware (same physical_key), the registry marks the inventory entry as shadowed.
"""
from __future__ import annotations

from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import Capabilities, Category, Connection, DeviceInfo, Support

# What we know about specific hardware on this machine and why writes stay off.
KNOWN = {
    "320F:5055": dict(category=Category.KEYBOARD, controlled_by=["Kreo KB Hub (OemDrv.exe)"],
                      notes=["Evision V2 keyboard. Lighting is handled by the 'kreo-hid' adapter."]),
    "31B2:0011": dict(category=Category.AUDIO, notes=["USB microphone (DCMT). HID consumer-control interface only, no lighting."]),
    "5131:2007": dict(category=Category.OTHER, name="Generic HID device 5131:2007",
                      notes=["Generic USB chip used by AIO pump displays (handled by the 'cooler' adapter once you "
                             "confirm it), but also by USB relay boards and other gadgets."]),
    "1532:00AB": dict(category=Category.MOUSE, controlled_by=["Razer Synapse 4"],
                      notes=["Basilisk V3 Pro through its HyperSpeed receiver (00AA is the wired PID)."]),
}

USAGE_CATEGORY = {(0x01, 0x06): Category.KEYBOARD, (0x01, 0x02): Category.MOUSE}


def _hid_devices(interfaces) -> dict[str, list]:
    groups: dict[str, list] = {}
    for h in interfaces:
        if h.vid == 0:
            continue
        groups.setdefault(h.vidpid, []).append(h)
    return groups


class InventoryAdapter(DeviceAdapter):
    name = "inventory"
    priority = 200
    control_path = "Windows HID class driver (query-only handles) + CIM"

    def __init__(self, hid_provider: Callable[[], list] | None = None, cim_provider: Callable[[], dict] | None = None):
        self.hid_provider = hid_provider or (lambda: [])
        self.cim_provider = cim_provider or (lambda: {})

    def health(self) -> AdapterHealth:
        return AdapterHealth(True, "read-only inventory")

    def discover(self) -> list[DiscoveredDevice]:
        out = []
        for vidpid, ifaces in sorted(_hid_devices(self.hid_provider()).items()):
            named = next((i for i in ifaces if i.product), None)
            known = KNOWN.get(vidpid, {})
            cat = known.get("category")
            if cat is None:
                cat = next((USAGE_CATEGORY[(i.usage_page, i.usage)] for i in ifaces
                            if (i.usage_page, i.usage) in USAGE_CATEGORY), Category.OTHER)
            name = known.get("name") or (named.product if named else f"Unknown HID device {vidpid}")
            vendor_cols = [f"{i.usage_page:04X}:{i.usage:04X}" for i in ifaces if (i.usage_page or 0) >= 0xFF00]
            evidence = [f"{len(ifaces)} HID collection(s); usages: " +
                        ", ".join(sorted({f'{i.usage_page:04X}:{i.usage:04X}' for i in ifaces if i.usage_page is not None}))]
            if vendor_cols:
                evidence.append("vendor-defined collections: " + ", ".join(vendor_cols))
            out.append(DiscoveredDevice(
                DeviceInfo(f"inventory:hid:{vidpid}", name, cat, self.name,
                           vendor=named.manufacturer if named else None, model=name, vidpid=vidpid,
                           physical_key=f"usb:{vidpid}", connection_path="USB HID",
                           controlled_by=list(known.get("controlled_by", [])), evidence=evidence),
                Capabilities(color=Support.BLOCKED if vendor_cols else Support.UNSUPPORTED,
                             notes=list(known.get("notes", ["Detected via HID; no control path identified."]))),
                Connection.MONITOR_ONLY))

        cim = self.cim_provider() or {}
        for g in cim.get("gpus") or []:
            pnp = (g.get("PNPDeviceID") or "")
            if not pnp.startswith("PCI\\"):
                continue   # skip virtual display adapters (e.g. Parsec)
            name = g.get("Name") or "GPU"
            sub = pnp.split("SUBSYS_")[1][:8] if "SUBSYS_" in pnp else ""
            board_vendor = {"1458": "Gigabyte", "1462": "MSI"}.get(sub[4:8].upper(), None) if sub else None
            notes = []
            if "NVIDIA" in name.upper():
                notes.append("Board lighting on add-in cards sits behind an I2C controller on the GPU's bus. "
                             "UniRGB does not write raw I2C. Use the card vendor's tool, or OpenRGB if it supports your exact model.")
            else:
                notes.append("Integrated graphics. No lighting.")
            out.append(DiscoveredDevice(
                DeviceInfo(f"inventory:gpu:{pnp.split(chr(92))[1] if chr(92) in pnp else name}", name, Category.GPU,
                           self.name, vendor=board_vendor, model=name, physical_key=f"pci:{pnp}",
                           connection_path="PCIe", evidence=[f"PNP {pnp}", f"driver {g.get('DriverVersion')}"]),
                Capabilities(color=Support.BLOCKED if "NVIDIA" in name.upper() else Support.UNSUPPORTED, notes=notes),
                Connection.MONITOR_ONLY))

        dimms = cim.get("dimms") or []
        if dimms:
            parts = sorted({(d.get("PartNumber") or "?").strip() for d in dimms})
            total = sum(int(d.get("Capacity") or 0) for d in dimms) // 2**30
            out.append(DiscoveredDevice(
                DeviceInfo("inventory:dram", f"DDR5 memory ({len(dimms)}x, {total} GB)", Category.MEMORY, self.name,
                           vendor="G.Skill" if any(p.startswith("F5-") for p in parts) else None,
                           model=", ".join(parts), physical_key="smbus:dram", connection_path="SMBus (SPD/RGB hub)",
                           controlled_by=["MSI Mystic Light (zone 'DDR5 DIMM')"],
                           evidence=[f"CIM part numbers: {', '.join(parts)}",
                                     "MSI Mystic Light log lists a 'DDR5 DIMM' zone"]),
                Capabilities(color=Support.BLOCKED,
                             notes=["This entry only lists the installed memory.",
                                    "To control RAM lighting, turn on RAM lighting in Settings: each stick with a "
                                    "supported ENE controller then appears as its own entry."]),
                Connection.MONITOR_ONLY))
        return out
