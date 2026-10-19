"""MSI Mystic Light 761 controller over raw HID, bypassing MSI Center.

Safety rules in this adapter:
* Writes are refused while MSI Center's lighting processes run. They stream colors
  to the same controller, so the two writers would fight.
* Before the first write, the controller's own setup (GET 0x50) is saved to
  %LOCALAPPDATA%\\UniRGB\\msi761_baseline.bin. restore() writes exactly those bytes back.
* Only the setup layout OpenRGB ships as tested for this board is sent.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Color, Confirmation, Connection, DeviceInfo,
                           LightingState, Support, Zone)
from ..protocols import msi761

MSI_VID, MSI_PID = 0x0DB0, 0x0076
MSI_LIGHTING_PROCESSES = {"mystic_light_service.exe", "ledkeeper2.exe", "lightkeeperservice.exe"}
TESTED_BOARDS = {"MS-7E70"}   # OpenRGB board table: X870E GAMING PLUS WIFI / PRO X870E-P WIFI


def default_baseline() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UniRGB" / "msi761_baseline.bin"


def _default_open(info):
    from ..hostos.hid_io import HidDevice
    return HidDevice(info)


class MsiDirectAdapter(DeviceAdapter):
    name = "msi-hid"
    priority = 5
    control_path = "UniRGB -> HID feature reports 0x50/0x51 -> Mystic Light MCU (MSI Center bypassed)"

    def __init__(self, hid_provider: Callable[[], list] | None = None, open_device=_default_open,
                 process_provider: Callable[[], set] | None = None, board_provider: Callable[[], str] | None = None,
                 baseline_path: Path | None = None):
        self.hid_provider = hid_provider or (lambda: [])
        self.open_device = open_device
        self.process_provider = process_provider or (lambda: set())
        self.board_provider = board_provider or (lambda: "")
        self.baseline_path = baseline_path or default_baseline()
        self._dev = None
        self._info = None
        self._led_counts: dict[str, int] = {}
        self._direct_active = False

    def health(self) -> AdapterHealth:
        return AdapterHealth(True, "direct HID")

    def _open(self):
        if self._dev is None:
            self._dev = self.open_device(self._info)
        return self._dev

    def _close(self):
        if self._dev is not None:
            try:
                self._dev.close()
            finally:
                self._dev = None

    def _blockers(self) -> list[str]:
        running = sorted(MSI_LIGHTING_PROCESSES & self.process_provider())
        return running

    def discover(self) -> list[DiscoveredDevice]:
        match = [h for h in self.hid_provider()
                 if h.vid == MSI_VID and h.pid == MSI_PID and h.usage_page == 0xFF00 and (h.feature_len or 0) >= 761]
        if not match:
            self._close()
            self._info = None
            return []
        h = match[0]
        if self._info is None or self._info.path != h.path:
            self._close()
        self._info = h
        board = self.board_provider() or ""
        evidence = [f"HID 0DB0:0076 page FF00, feature report {h.feature_len} bytes", f"board: {board or 'unknown'}"]
        try:
            setup = self._open().get_feature(0x50)
            self._led_counts = msi761.led_counts_from(setup)
            active = msi761.decode_setup(setup)
            evidence.append("setup read over HID (GET 0x50): " +
                            ", ".join(f"{k} mode {v['mode']} x{v['led_count']}" for k, v in active.items()))
            if not self._direct_active:
                self._save_baseline(setup)
        except Exception as e:
            self._close()
            return [self._record(h, board, evidence + [f"setup read failed: {e}"], Connection.ERROR, blocked="read failed")]
        blockers = self._blockers()
        tested = any(b in board for b in TESTED_BOARDS)
        reason = None
        if not tested:
            reason = f"board '{board}' is not in OpenRGB's tested list for this protocol"
        elif blockers:
            reason = "MSI Center lighting is running (" + ", ".join(blockers) + ")"
        return [self._record(h, board, evidence, Connection.CONNECTED, blocked=reason)]

    def _record(self, h, board, evidence, conn, blocked: str | None) -> DiscoveredDevice:
        zones = [Zone(z, name, max(1, self._led_counts.get(z, 0) or 1), Support.EXPERIMENTAL)
                 for z, (_i, _a, _b, name) in msi761.DIRECT_ZONES.items()]
        # colors: accepted by the controller and direct mode confirmed by setup read-back (2026-10-19)
        write = Support.BLOCKED if blocked else Support.SUPPORTED
        notes = []
        if blocked:
            notes.append(f"Writes blocked: {blocked}. Stop MSI Center's lighting (see docs/direct-control.md) and press Rescan.")
        notes += ["Direct mode drives the four addressable headers (JARGB_V2_1-3, EZ Conn). The 12 V JRGB1 header "
                  "is switched off in this mode, as in OpenRGB's tested layout. DIMM lighting is not on this USB "
                  "controller (MSI drives it over SMBus), so it keeps its last effect. UniRGB never writes to RAM.",
                  f"LED counts are taken from MSI's own setup: {self._led_counts or 'unknown'}.",
                  "Restore writes back the controller setup saved before UniRGB's first write. Restarting "
                  "MSI Center also re-applies its lighting.",
                  "Brightness is applied by scaling colors; direct packets carry raw RGB."]
        return DiscoveredDevice(
            DeviceInfo("msi-hid:0DB0:0076", "MSI Mystic Light (direct)", Category.MOTHERBOARD, self.name, vendor="MSI",
                       model=board or h.product, vidpid="0DB0:0076", physical_key="usb:0DB0:0076",
                       connection_path=self.control_path, controlled_by=["UniRGB (direct)"], evidence=evidence),
            Capabilities(read_state=Support.UNSUPPORTED, color=write, brightness=write, effects=["static", "off"],
                         zones=zones, zone_control=Support.BLOCKED if blocked else Support.EXPERIMENTAL, restore=Support.EXPERIMENTAL if self._has_baseline() else Support.UNSUPPORTED,
                         notes=notes),
            conn)

    # ---------- baseline ----------
    def _has_baseline(self) -> bool:
        return self.baseline_path.exists()

    def _save_baseline(self, setup: bytes) -> None:
        # keep the first baseline ever captured: a later read could already be UniRGB's own setup
        if self.baseline_path.exists():
            return
        self.baseline_path.parent.mkdir(parents=True, exist_ok=True)
        self.baseline_path.write_bytes(setup[:msi761.SETUP_LEN])

    # ---------- control ----------
    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        if self._info is None:
            return ApplyResult(False, message="controller not present")
        blockers = self._blockers()
        if blockers:
            return ApplyResult(False, message="MSI Center lighting is running (" + ", ".join(blockers) + "); stop it first")
        if not self._has_baseline():
            return ApplyResult(False, message="no saved baseline; refusing to write without a way back")
        try:
            dev = self._open()
            counts = {z: (self._led_counts.get(z) or 0x78) for z in msi761.DIRECT_ZONES}
            if not self._direct_active:
                dev.set_feature(msi761.build_direct_setup(counts))
                self._direct_active = True
            off = state.mode == "off"
            for z in msi761.DIRECT_ZONES:
                c = Color(0, 0, 0) if off else state.zones.get(z, state.color or Color(0, 0, 0)).scaled(state.brightness)
                dev.set_feature(msi761.build_zone_packet(z, [(c.r, c.g, c.b)] * counts[z], counts[z]))
        except Exception as e:
            self._close()
            return ApplyResult(False, message=f"direct HID: {e}")
        return ApplyResult(True, Confirmation.DEVICE_ACK, "controller accepted the feature reports", applied=state)

    def restore(self, device_id: str) -> ApplyResult:
        if self._info is None or not self._has_baseline():
            return ApplyResult(False, message="no saved baseline to restore")
        try:
            self._open().set_feature(self.baseline_path.read_bytes())
            self._direct_active = False
        except Exception as e:
            self._close()
            return ApplyResult(False, message=f"restore failed: {e}")
        return ApplyResult(True, message="MSI setup restored from baseline; start MSI Center to resume its effects")

    def shutdown(self) -> None:
        self._close()
