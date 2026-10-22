"""Kreo Hive RGB keyboard (Evision V2) over raw HID, replacing Kreo KB Hub for lighting.

Only live "dynamic colors" are used: nothing is written to the keyboard's stored
profiles. A keepalive re-sends the colors every 150 ms; when UniRGB stops (or crashes) the
keyboard returns to its stored effect within ~200 ms by itself. restore() ends direct mode.
"""
from __future__ import annotations

import logging
import threading
from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Color, Confirmation, Connection, DeviceInfo,
                           LightingState, Support)
from ..protocols import evision_v2 as ev

log = logging.getLogger("unirgb.kreo")
VID, PID = 0x320F, 0x5055
KEEPALIVE_S = 0.15


def _default_open(info):
    from ..hostos.hid_io import HidReportDevice
    return HidReportDevice(info)


class KreoDirectAdapter(DeviceAdapter):
    name = "kreo-hid"
    priority = 5
    control_path = "UniRGB -> HID report 4 on vendor collection FF1C:0092 -> keyboard MCU (Kreo KB Hub not needed)"

    def __init__(self, hid_provider: Callable[[], list] | None = None, open_device=_default_open,
                 keepalive_s: float = KEEPALIVE_S):
        self.hid_provider = hid_provider or (lambda: [])
        self.open_device = open_device
        self.keepalive_s = keepalive_s
        self._info = None
        self._dev = None
        self._t: ev.EvisionTransport | None = None
        self._map_size = 0
        self._buffer: bytes | None = None      # colors currently being streamed (None = stored effect)
        self._lock = threading.Lock()          # one request/response at a time (worker vs keepalive)
        self._stop = threading.Event()
        self._ka: threading.Thread | None = None
        self.keepalive_errors = 0

    def health(self) -> AdapterHealth:
        return AdapterHealth(True, "direct HID")

    def _transport(self) -> ev.EvisionTransport:
        if self._t is None:
            self._dev = self.open_device(self._info)
            self._t = ev.EvisionTransport(self._dev)
        return self._t

    def _close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            except Exception:
                pass
        self._dev, self._t = None, None

    def discover(self) -> list[DiscoveredDevice]:
        match = [h for h in self.hid_provider()
                 if h.vid == VID and h.pid == PID and h.usage_page == 0xFF1C and (h.output_len or 0) >= 64]
        if not match:
            with self._lock:
                self._stop_keepalive()
                self._close()
                self._info = None
            return []
        h = match[0]
        evidence = ["HID 320F:5055 'Evision / Kreo Hive RGB', vendor collection FF1C:0092, 64-byte reports"]
        conn = Connection.CONNECTED
        with self._lock:
            if self._info is None or self._info.path != h.path:
                self._close()
            self._info = h
            try:
                caps = self._transport().capabilities()
                self._map_size = caps["map_size"]
                evidence.append(f"Evision V2 capabilities read (AA 55 signature, {self._map_size} LED slots)")
            except Exception as e:
                self._close()
                conn = Connection.ERROR
                evidence.append(f"capabilities read failed: {e}")
        return [DiscoveredDevice(
            DeviceInfo("kreo-hid:320F:5055", (h.product or "Evision V2 keyboard") + " keyboard"
                       if h.product and "keyboard" not in h.product.lower() else (h.product or "Evision V2 keyboard"),
                       Category.KEYBOARD, self.name, vendor="Kreo" if (h.product or "").lower().startswith("kreo") else h.manufacturer,
                       model=(h.product or "") + " (Evision V2)", vidpid="320F:5055", physical_key="usb:320F:5055",
                       connection_path=self.control_path, controlled_by=["UniRGB (direct)"], evidence=evidence),
            Capabilities(read_state=Support.UNSUPPORTED, color=Support.EXPERIMENTAL, brightness=Support.EXPERIMENTAL,
                         effects=["static", "off"], restore=Support.SUPPORTED,
                         notes=["Whole-keyboard color. Per-key mapping for the Kreo layout is not known yet.",
                                "Live colors only: the keyboard's stored profiles are never written. When UniRGB "
                                "stops, the keyboard goes back to its own effect within about 0.2 s.",
                                "Brightness is applied by scaling the color."]),
            conn)]

    # ---------- keepalive ----------
    def _start_keepalive(self) -> None:
        if self._ka and self._ka.is_alive():
            return
        self._stop.clear()
        self._ka = threading.Thread(target=self._keepalive, name="kreo-keepalive", daemon=True)
        self._ka.start()

    def _stop_keepalive(self) -> None:
        self._stop.set()

    def _keepalive(self) -> None:
        while not self._stop.wait(self.keepalive_s):
            with self._lock:
                if self._buffer is None or self._info is None:
                    return
                try:
                    # the whole buffer: after a missed refresh the keyboard drops back to its stored effect,
                    # and re-sending only the first chunk left the other keys showing that effect
                    self._transport().send_dynamic(self._buffer)
                    self.keepalive_errors = 0
                except Exception as e:
                    self.keepalive_errors += 1
                    self._close()
                    if self.keepalive_errors >= 10:
                        log.warning("keyboard stopped answering; giving it back to its stored effect: %s", e)
                        self._buffer = None
                        return

    # ---------- control ----------
    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        if self._info is None or not self._map_size:
            return ApplyResult(False, message="keyboard not ready")
        c = Color(0, 0, 0) if state.mode == "off" or state.color is None else state.color.scaled(state.brightness)
        buf = bytes((c.r, c.g, c.b)) * self._map_size
        with self._lock:
            try:
                self._transport().send_dynamic(buf)
            except Exception as e:
                self._close()
                return ApplyResult(False, message=f"direct HID: {e}")
            self._buffer = buf
        self._start_keepalive()
        return ApplyResult(True, Confirmation.DEVICE_ACK, "keyboard acknowledged every packet", applied=state)

    def restore(self, device_id: str) -> ApplyResult:
        with self._lock:
            self._buffer = None
            self._stop_keepalive()
            if self._info is None:
                return ApplyResult(False, message="keyboard not present")
            try:
                self._transport().end()
            except Exception as e:
                self._close()
                return ApplyResult(False, message=f"could not end direct mode ({e}); it ends by itself within 0.2 s")
        return ApplyResult(True, message="keyboard is back on its own stored lighting")

    def shutdown(self) -> None:
        try:
            self.restore("kreo-hid:320F:5055")
        except Exception:
            pass
        with self._lock:
            self._close()
