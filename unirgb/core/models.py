"""Hardware-agnostic device and lighting models.

Two states are tracked per device and never conflated:
  * desired   – what the user asked for (owned by the app)
  * confirmed – what an adapter can vouch for, tagged with HOW it knows
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field, asdict
from enum import Enum


class Category(str, Enum):
    MOUSE = "mouse"
    KEYBOARD = "keyboard"
    MOTHERBOARD = "motherboard"
    MEMORY = "memory"
    GPU = "gpu"
    AUDIO = "audio"
    LIGHTING_LINK = "lighting-link"
    COOLER = "cooler"
    OTHER = "other"


class Support(str, Enum):
    """Evidence level for one capability on one device."""
    SUPPORTED = "supported"        # implemented and exercised against this device/API
    EXPERIMENTAL = "experimental"  # implemented, API accepts it, physical effect unverified
    UNSUPPORTED = "unsupported"    # the control path has no such operation
    BLOCKED = "blocked"            # possible in principle, deliberately not done (safety/conflict)
    UNTESTED = "untested"          # implemented, never exercised against real hardware


class Confirmation(str, Enum):
    HARDWARE_READBACK = "hardware-readback"  # value read back from the device
    API_ACCEPTED = "api-accepted"            # vendor API returned success; LEDs not observed
    DEVICE_ACK = "device-ack"                # the device itself acknowledged the command; LEDs not observed
    NONE = "none"


class Connection(str, Enum):
    CONNECTED = "connected"
    UNAVAILABLE = "unavailable"   # control path down (service stopped, server absent)
    ASLEEP = "asleep"             # wireless device sleeping; it comes back when it wakes
    ERROR = "error"
    MONITOR_ONLY = "monitor-only"


_HEX = re.compile(r"^#?([0-9a-fA-F]{6})$")


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int

    def __post_init__(self):
        for v in (self.r, self.g, self.b):
            if not isinstance(v, int) or not 0 <= v <= 255:
                raise ValueError(f"color channel out of range: {v!r}")

    @classmethod
    def parse(cls, value) -> "Color":
        if isinstance(value, Color):
            return value
        if isinstance(value, str):
            m = _HEX.match(value.strip())
            if not m:
                raise ValueError(f"invalid hex color: {value!r}")
            n = int(m.group(1), 16)
            return cls((n >> 16) & 255, (n >> 8) & 255, n & 255)
        if isinstance(value, dict):
            return cls(int(value["r"]), int(value["g"]), int(value["b"]))
        if isinstance(value, (list, tuple)) and len(value) == 3:
            return cls(*(int(v) for v in value))
        raise ValueError(f"unsupported color value: {value!r}")

    def hex(self) -> str:
        return f"#{self.r:02x}{self.g:02x}{self.b:02x}"

    def scaled(self, brightness: int) -> "Color":
        """Software brightness (0-100) for paths without native brightness."""
        k = max(0, min(100, brightness)) / 100.0
        return Color(round(self.r * k), round(self.g * k), round(self.b * k))


@dataclass
class LightingState:
    """Normalized lighting request/state. `zones` overrides `color` per zone id."""
    mode: str = "static"            # one of Capabilities.effects
    color: Color | None = None
    brightness: int = 100           # 0-100
    zones: dict[str, Color] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"mode": self.mode, "color": self.color.hex() if self.color else None,
                "brightness": self.brightness, "zones": {k: c.hex() for k, c in self.zones.items()}}

    @classmethod
    def from_dict(cls, d: dict) -> "LightingState":
        if not isinstance(d, dict):
            raise ValueError("lighting state must be an object")
        is_int = lambda v: isinstance(v, int) and not isinstance(v, bool)
        b = d.get("brightness", 100)
        if not is_int(b) or not 0 <= b <= 100:
            raise ValueError("brightness must be an integer 0-100")
        zones = d.get("zones")
        zones = {} if zones is None else zones
        if not isinstance(zones, dict):
            raise ValueError("zones must be an object")
        return cls(mode=str(d.get("mode", "static")),
                   color=Color.parse(d["color"]) if d.get("color") else None,
                   brightness=b, zones={str(k): Color.parse(v) for k, v in zones.items()})


@dataclass
class Zone:
    id: str
    name: str
    led_count: int = 1
    support: Support = Support.EXPERIMENTAL


@dataclass
class Capabilities:
    discovery: Support = Support.SUPPORTED
    read_state: Support = Support.UNSUPPORTED
    color: Support = Support.UNSUPPORTED
    brightness: Support = Support.UNSUPPORTED
    brightness_native: bool = False   # False => brightness is applied by scaling colors
    effects: list[str] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    zone_control: Support = Support.UNSUPPORTED
    fan_control: Support = Support.UNSUPPORTED
    display: Support = Support.UNSUPPORTED   # e.g. a temperature readout fed by UniRGB
    restore: Support = Support.UNSUPPORTED
    notes: list[str] = field(default_factory=list)

    @property
    def writable(self) -> bool:
        return self.color in (Support.SUPPORTED, Support.EXPERIMENTAL, Support.UNTESTED)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["writable"] = self.writable
        return d


@dataclass
class DeviceInfo:
    id: str                    # stable: "<adapter>:<local id>"
    name: str
    category: Category
    adapter: str
    vendor: str | None = None
    model: str | None = None
    vidpid: str | None = None
    physical_key: str | None = None   # identifies the same hardware across adapters
    connection_path: str | None = None
    controlled_by: list[str] = field(default_factory=list)  # vendor apps/services involved
    evidence: list[str] = field(default_factory=list)


@dataclass
class ApplyResult:
    ok: bool
    confirmation: Confirmation = Confirmation.NONE
    message: str = ""
    applied: LightingState | None = None
    released: list[str] = field(default_factory=list)  # restore(): sibling devices also released


class UnsupportedOperation(Exception):
    pass


class AdapterUnavailable(Exception):
    pass


@dataclass
class DeviceRecord:
    """Registry entry: everything the UI needs for one device."""
    info: DeviceInfo
    caps: Capabilities
    connection: Connection = Connection.CONNECTED
    desired: LightingState | None = None
    confirmed: LightingState | None = None
    confirmation: Confirmation = Confirmation.NONE
    last_error: str | None = None
    shadowed_by: str | None = None    # another adapter owns writes for this hardware
    updated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        info = asdict(self.info)
        info["category"] = self.info.category.value
        return {"info": info, "caps": self.caps.to_dict(), "connection": self.connection.value,
                "desired": self.desired.to_dict() if self.desired else None,
                "confirmed": self.confirmed.to_dict() if self.confirmed else None,
                "confirmation": self.confirmation.value, "last_error": self.last_error,
                "shadowed_by": self.shadowed_by, "updated_at": self.updated_at}
