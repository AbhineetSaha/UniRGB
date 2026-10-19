"""Adapter contract. Every hardware integration implements this and nothing else.

The orchestrator calls adapters only from that adapter's own worker thread, so
implementations need no internal locking for calls made through it. Background
threads an adapter starts itself (e.g. heartbeats) must synchronise on their own.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .models import ApplyResult, Capabilities, Connection, DeviceInfo, LightingState


@dataclass
class DiscoveredDevice:
    info: DeviceInfo
    caps: Capabilities
    connection: Connection = Connection.CONNECTED


@dataclass
class AdapterHealth:
    available: bool
    detail: str = ""
    facts: dict = field(default_factory=dict)


class DeviceAdapter(ABC):
    #: short unique id, used as device-id prefix
    name: str = "adapter"
    #: lower number wins when two adapters expose the same physical device
    priority: int = 100
    #: human-readable description of the control path
    control_path: str = ""

    @abstractmethod
    def discover(self) -> list[DiscoveredDevice]:
        """Enumerate devices. Must be side-effect free on hardware."""

    @abstractmethod
    def health(self) -> AdapterHealth:
        """Cheap check whether the control path is up."""

    def read_state(self, device_id: str) -> LightingState | None:
        """Read current state from hardware; None when the path cannot read."""
        return None

    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        return ApplyResult(False, message=f"{self.name}: device is read-only")

    def restore(self, device_id: str) -> ApplyResult:
        """Hand the device back to its original owner / state."""
        return ApplyResult(False, message=f"{self.name}: restore not supported")

    def configure(self, device_id: str, settings: dict) -> ApplyResult:
        """Non-lighting device settings (e.g. a display's data source)."""
        return ApplyResult(False, message=f"{self.name}: nothing to configure")

    def status(self, device_id: str) -> dict:
        """Live, adapter-specific status for the UI. Must be cheap."""
        return {}

    def shutdown(self) -> None:
        """Release all sessions/handles. Must be idempotent and never raise."""
