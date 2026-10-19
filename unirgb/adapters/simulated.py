"""Simulated devices for development and tests. Loaded only with --simulate; every
device name starts with "[SIM]" so it can never be mistaken for real hardware."""
from __future__ import annotations

import copy
import time

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Confirmation, DeviceInfo, LightingState,
                           Support, Zone)


class SimulatedAdapter(DeviceAdapter):
    name = "sim"
    priority = 900
    control_path = "in-process simulation (no hardware)"

    def __init__(self, delay: float = 0.0):
        self.delay = delay
        self.state: dict[str, LightingState] = {}
        self.fail_next = 0          # fault injection: number of upcoming applies to fail
        self.raise_next = False     # fault injection: raise instead of returning an error
        self.connected = True
        self.apply_log: list[tuple[str, LightingState]] = []

    def health(self) -> AdapterHealth:
        return AdapterHealth(self.connected, "simulation" if self.connected else "simulated disconnect")

    def discover(self) -> list[DiscoveredDevice]:
        if not self.connected:
            return []
        caps = lambda zones: Capabilities(
            read_state=Support.SUPPORTED, color=Support.SUPPORTED, brightness=Support.SUPPORTED,
            brightness_native=True, effects=["static", "off"], zones=zones,
            zone_control=Support.SUPPORTED if zones else Support.UNSUPPORTED, restore=Support.SUPPORTED,
            notes=["SIMULATED device. Results do not reflect any real hardware."])
        return [
            DiscoveredDevice(DeviceInfo("sim:strip", "[SIM] ARGB strip", Category.OTHER, self.name,
                                        vendor="Simulated", physical_key="sim:strip"),
                             caps([Zone("a", "Segment A", 10, Support.SUPPORTED), Zone("b", "Segment B", 10, Support.SUPPORTED)])),
            DiscoveredDevice(DeviceInfo("sim:fan", "[SIM] Case fan ring", Category.OTHER, self.name,
                                        vendor="Simulated", physical_key="sim:fan"), caps([])),
        ]

    def read_state(self, device_id: str) -> LightingState | None:
        return copy.deepcopy(self.state.get(device_id))

    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        if self.delay:
            time.sleep(self.delay)
        if self.raise_next:
            self.raise_next = False
            raise RuntimeError("simulated adapter crash")
        if self.fail_next:
            self.fail_next -= 1
            return ApplyResult(False, message="simulated failure")
        self.state[device_id] = copy.deepcopy(state)
        self.apply_log.append((device_id, copy.deepcopy(state)))
        return ApplyResult(True, Confirmation.HARDWARE_READBACK, "simulated read-back", applied=self.read_state(device_id))

    def restore(self, device_id: str) -> ApplyResult:
        self.state.pop(device_id, None)
        return ApplyResult(True, message="simulated restore")
