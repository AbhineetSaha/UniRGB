"""OpenRGB SDK client (OpenRGB's documented network protocol, default 127.0.0.1:6742).

Used only when the user runs OpenRGB with its SDK server enabled. UniRGB never
starts OpenRGB itself. OpenRGB writes to hardware directly (HID, SMBus), so it
can fight vendor services for the same controller. Every device it exposes is
labelled with that risk, and the Chroma path wins for Razer hardware.

Status: protocol tested only against tests/fake_openrgb.py. No OpenRGB server
was running on the development machine, so every capability is UNTESTED.
"""
from __future__ import annotations

import re
import socket
import struct
import threading

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Color, Confirmation, DeviceInfo,
                           LightingState, Support, Zone)

MAGIC = b"ORGB"
HDR = struct.Struct("<4sIII")
PKT_CONTROLLER_COUNT = 0
PKT_CONTROLLER_DATA = 1
PKT_PROTOCOL_VERSION = 40
PKT_SET_CLIENT_NAME = 50
PKT_UPDATELEDS = 1050
PKT_SETCUSTOMMODE = 1100
CLIENT_PROTOCOL = 3   # we parse up to v3; the server answers with min(ours, its own)

DEVICE_TYPES = {0: Category.MOTHERBOARD, 1: Category.MEMORY, 2: Category.GPU, 5: Category.KEYBOARD,
                6: Category.MOUSE}
_VIDPID = re.compile(r"VID_([0-9A-F]{4}).*?PID_([0-9A-F]{4})", re.I)


class Reader:
    def __init__(self, data: bytes):
        self.d, self.o = data, 0

    def _take(self, fmt: str):
        s = struct.calcsize(fmt)
        if self.o + s > len(self.d):
            raise ValueError("truncated OpenRGB packet")
        v = struct.unpack_from(fmt, self.d, self.o)
        self.o += s
        return v[0] if len(v) == 1 else v

    def u16(self): return self._take("<H")
    def u32(self): return self._take("<I")
    def i32(self): return self._take("<i")

    def string(self) -> str:
        n = self.u16()
        if self.o + n > len(self.d):
            raise ValueError("truncated OpenRGB string")
        raw = self.d[self.o:self.o + n]
        self.o += n
        return raw.rstrip(b"\x00").decode("utf-8", "replace")


def parse_controller(data: bytes, proto: int) -> dict:
    r = Reader(data)
    r.u32()  # data_size
    c = {"type": r.i32(), "name": r.string()}
    c["vendor"] = r.string() if proto >= 1 else ""
    c["description"], c["version"], c["serial"], c["location"] = r.string(), r.string(), r.string(), r.string()
    n_modes = r.u16()
    c["active_mode"] = r.i32()
    modes = []
    for _ in range(n_modes):
        m = {"name": r.string(), "value": r.i32(), "flags": r.u32(), "speed_min": r.u32(), "speed_max": r.u32()}
        if proto >= 3:
            m["brightness_min"], m["brightness_max"] = r.u32(), r.u32()
        m["colors_min"], m["colors_max"], m["speed"] = r.u32(), r.u32(), r.u32()
        if proto >= 3:
            m["brightness"] = r.u32()
        m["direction"], m["color_mode"] = r.u32(), r.u32()
        m["colors"] = [r.u32() for _ in range(r.u16())]
        modes.append(m)
    c["modes"] = modes
    zones = []
    for _ in range(r.u16()):
        z = {"name": r.string(), "type": r.i32(), "leds_min": r.u32(), "leds_max": r.u32(), "leds_count": r.u32()}
        if r.u16() > 0:   # matrix_len in bytes
            h, w = r.u32(), r.u32()
            [r.u32() for _ in range(h * w)]
        zones.append(z)
    c["zones"] = zones
    c["leds"] = [{"name": r.string(), "value": r.u32()} for _ in range(r.u16())]
    c["colors"] = [r.u32() for _ in range(r.u16())]
    return c


def rgb_u32(c: Color) -> int:
    return c.r | (c.g << 8) | (c.b << 16)


def u32_rgb(v: int) -> Color:
    return Color(v & 255, (v >> 8) & 255, (v >> 16) & 255)


class OpenRGBClient:
    def __init__(self, host="127.0.0.1", port=6742, timeout=2.0):
        self.host, self.port, self.timeout = host, port, timeout
        self.sock: socket.socket | None = None
        self.proto = 0

    def connect(self) -> None:
        self.sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
        self.send(0, PKT_SET_CLIENT_NAME, b"UniRGB\x00")
        self.send(0, PKT_PROTOCOL_VERSION, struct.pack("<I", CLIENT_PROTOCOL))
        try:
            _, payload = self.recv(PKT_PROTOCOL_VERSION)
            self.proto = min(CLIENT_PROTOCOL, struct.unpack("<I", payload[:4])[0])
        except socket.timeout:
            self.proto = 0   # protocol-0 servers do not answer this request

    def close(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            finally:
                self.sock = None

    def send(self, dev: int, pkt: int, payload: bytes = b"") -> None:
        self.sock.sendall(HDR.pack(MAGIC, dev, pkt, len(payload)) + payload)

    def _exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("OpenRGB closed the connection")
            buf += chunk
        return buf

    def recv(self, want_pkt: int) -> tuple[int, bytes]:
        while True:
            magic, dev, pkt, size = HDR.unpack(self._exact(HDR.size))
            if magic != MAGIC:
                raise ValueError("bad OpenRGB magic")
            payload = self._exact(size)
            if pkt == want_pkt:
                return dev, payload
            # skip unsolicited packets such as DEVICE_LIST_UPDATED

    def controller_count(self) -> int:
        self.send(0, PKT_CONTROLLER_COUNT)
        return struct.unpack("<I", self.recv(PKT_CONTROLLER_COUNT)[1][:4])[0]

    def controller(self, idx: int) -> dict:
        self.send(idx, PKT_CONTROLLER_DATA, struct.pack("<I", self.proto) if self.proto else b"")
        return parse_controller(self.recv(PKT_CONTROLLER_DATA)[1], self.proto)

    def set_leds(self, idx: int, colors: list[int]) -> None:
        self.send(idx, PKT_SETCUSTOMMODE)
        body = struct.pack("<H", len(colors)) + b"".join(struct.pack("<I", c) for c in colors)
        self.send(idx, PKT_UPDATELEDS, struct.pack("<I", 4 + len(body)) + body)


class OpenRGBAdapter(DeviceAdapter):
    name = "openrgb"
    priority = 30
    control_path = "OpenRGB SDK (TCP 127.0.0.1:6742) -> OpenRGB -> direct HID/SMBus"

    # By user decision (2026-10-19) UniRGB uses OpenRGB only for the RAM (device type 1).
    # Everything else already has a direct UniRGB adapter; letting OpenRGB drive it too
    # would put two writers on one controller.
    DEFAULT_TYPES = frozenset({1})

    def __init__(self, host="127.0.0.1", port=6742, timeout=2.0, allowed_types=DEFAULT_TYPES):
        self.host, self.port, self.timeout = host, port, timeout
        self.allowed_types = allowed_types   # None = expose every OpenRGB controller
        self._client: OpenRGBClient | None = None
        self._lock = threading.Lock()
        self._ctrl: dict[str, dict] = {}   # device id -> {"index", "zones": [(id, start, count)], "leds"}

    def _conn(self) -> OpenRGBClient:
        if self._client is None:
            c = OpenRGBClient(self.host, self.port, self.timeout)
            c.connect()
            self._client = c
        return self._client

    def _drop(self) -> None:
        if self._client:
            self._client.close()
        self._client = None

    def health(self) -> AdapterHealth:
        # Never probe with a bare connect/close: OpenRGB 1.1 logs "recv_select failed receiving
        # magic, closing listener" for that, and repeated probes wedged its server (observed
        # 2026-10-19). Reuse one handshaken connection and ask for the controller count instead.
        with self._lock:
            try:
                n = self._conn().controller_count()
                return AdapterHealth(True, f"OpenRGB SDK server on {self.host}:{self.port}, {n} controllers")
            except (OSError, ValueError, ConnectionError):
                self._drop()
                return AdapterHealth(False, f"no OpenRGB SDK server on {self.host}:{self.port} "
                                            "(start OpenRGB with --server to use it)")

    def discover(self) -> list[DiscoveredDevice]:
        out = []
        with self._lock:
            try:
                c = self._conn()
                ctrls = [c.controller(i) for i in range(c.controller_count())]
            except (OSError, ValueError, ConnectionError):
                self._drop()
                self._ctrl = {}
                return []
        self._ctrl = {}
        for idx, ctl in enumerate(ctrls):
            if self.allowed_types is not None and ctl["type"] not in self.allowed_types:
                continue   # keep OpenRGB's index numbering; skip hardware UniRGB drives itself
            m = _VIDPID.search(ctl["location"])
            vidpid = f"{m.group(1).upper()}:{m.group(2).upper()}" if m else None
            dev_id = f"openrgb:{idx}:{re.sub(r'[^a-z0-9]+', '-', ctl['name'].lower()).strip('-')}"
            zones, start = [], 0
            for zi, z in enumerate(ctl["zones"]):
                zones.append((f"z{zi}", z["name"], start, z["leds_count"]))
                start += z["leds_count"]
            self._ctrl[dev_id] = {"index": idx, "zones": zones, "leds": len(ctl["leds"]), "name": ctl["name"],
                                  "location": ctl["location"]}
            has_direct = any(md["name"].lower() in ("direct", "custom", "static") for md in ctl["modes"])
            notes = ["OpenRGB does the hardware writes (for RAM: over SMBus through the PawnIO driver). You chose "
                     "this path knowing a bad SMBus write can damage a module; UniRGB itself sends only colors to OpenRGB.",
                     "Keep MSI Center's lighting off: it also writes the DIMMs and the two would fight.",
                     "Untested until verified against your running OpenRGB server."]
            out.append(DiscoveredDevice(
                DeviceInfo(dev_id, ctl["name"], DEVICE_TYPES.get(ctl["type"], Category.OTHER), self.name,
                           vendor=ctl["vendor"] or None, model=ctl["description"] or ctl["name"], vidpid=vidpid,
                           physical_key=f"usb:{vidpid}" if vidpid else f"openrgb:{ctl['location']}",
                           connection_path=f"{self.control_path} ({ctl['location']})", controlled_by=["OpenRGB"],
                           evidence=[f"OpenRGB controller #{idx}, protocol v{self._client.proto if self._client else '?'}",
                                     f"{len(ctl['leds'])} LEDs, {len(ctl['zones'])} zones, modes: "
                                     + ", ".join(md['name'] for md in ctl['modes'])]),
                Capabilities(read_state=Support.UNTESTED, color=Support.UNTESTED if has_direct else Support.UNSUPPORTED,
                             brightness=Support.UNTESTED, effects=["static", "off"],
                             zones=[Zone(zid, zn, cnt, Support.UNTESTED) for zid, zn, _, cnt in zones],
                             zone_control=Support.UNTESTED, restore=Support.UNSUPPORTED, notes=notes)))
        return out

    def _colors_for(self, info: dict, state: LightingState) -> list[int]:
        base = Color(0, 0, 0) if state.mode == "off" or state.color is None else state.color.scaled(state.brightness)
        colors = [rgb_u32(base)] * info["leds"]
        if state.mode != "off":
            for zid, _, start, cnt in info["zones"]:
                if zid in state.zones:
                    v = rgb_u32(state.zones[zid].scaled(state.brightness))
                    colors[start:start + cnt] = [v] * cnt
        return colors

    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        info = self._ctrl.get(device_id)
        if info is None:
            return ApplyResult(False, message="controller not present in OpenRGB")
        with self._lock:
            try:
                c = self._conn()
                # OpenRGB addresses controllers by list position, which shifts when its device list changes
                now = c.controller(info["index"])
                if (now["name"], now["location"]) != (info["name"], info["location"]):
                    self._ctrl = {}
                    return ApplyResult(False, message="OpenRGB's device list changed; press Rescan")
                c.set_leds(info["index"], self._colors_for(info, state))
            except (OSError, ConnectionError, ValueError) as e:
                self._drop()
                return ApplyResult(False, message=f"OpenRGB: {e}")
        return ApplyResult(True, Confirmation.API_ACCEPTED, "sent to OpenRGB", applied=state)

    def read_state(self, device_id: str) -> LightingState | None:
        info = self._ctrl.get(device_id)
        if info is None:
            return None
        with self._lock:
            try:
                ctl = self._conn().controller(info["index"])
            except (OSError, ConnectionError, ValueError):
                self._drop()
                return None
        cols = ctl["colors"]
        if not cols:
            return None
        return LightingState(color=u32_rgb(cols[0]),
                             zones={zid: u32_rgb(cols[s]) for zid, _, s, n in info["zones"] if n and s < len(cols)})

    def shutdown(self) -> None:
        with self._lock:
            self._drop()
