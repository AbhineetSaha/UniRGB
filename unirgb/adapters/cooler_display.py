"""Ant Esports ICE-Storm 360 pump-cap temperature display (USB HID 5131:2007).

UniRGB replaces the vendor app: a feeder thread sends the chosen temperature once a
second as a 65-byte output report (unirgb/protocols/antcooler.py). The cooler's pump
and fan ARGB run from the motherboard's ARGB headers, so their color is set through
the MSI Mystic Light entry, not here.
"""
from __future__ import annotations

import ctypes
import json
import logging
import os
import sys
import threading
import time
from pathlib import Path
from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import ApplyResult, Capabilities, Category, Connection, DeviceInfo, Support
from ..protocols import antcooler
from .. import sensors

log = logging.getLogger("unirgb.cooler")
VID, PID = 0x5131, 0x2007
# "confirmed": 5131:2007 is a generic USB chip (also used by USB relay boards and other displays),
# so nothing is sent until the user confirms in the UI that it is their cooler display.
DEFAULTS = {"enabled": True, "source": "auto", "fahrenheit": False, "anti_blink": "cap84", "confirmed": False}
SOURCES = ("auto", "cpu", "gpu")


def default_settings_path() -> Path:
    return Path(os.environ.get("APPDATA") or Path.home()) / "UniRGB" / "cooler.json"


def _default_open(info):
    from ..hostos.hid_io import HidDevice
    return HidDevice(info)


def _write_output(dev, data: bytes) -> None:
    """HID output report via WriteFile on the device handle."""
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    n = wintypes.DWORD()
    if not k32.WriteFile(dev._h, data, len(data), ctypes.byref(n), None) or n.value != len(data):
        raise OSError(ctypes.get_last_error(), "WriteFile to cooler display failed")


class CoolerDisplayAdapter(DeviceAdapter):
    name = "cooler"
    priority = 20
    control_path = "UniRGB feeder thread -> HID output report (5131:2007) -> pump-cap 7-segment display"

    def __init__(self, hid_provider: Callable[[], list] | None = None, open_device=_default_open,
                 write=_write_output, settings_path: Path | None = None, interval: float = 1.0,
                 cpu_reader=None, gpu_reader=sensors.read_nvidia):
        self.hid_provider = hid_provider or (lambda: [])
        self.open_device, self.write = open_device, write
        self.settings_path = settings_path or default_settings_path()
        self.interval = interval
        # LibreHardwareMonitor (open source) first, then the opt-in AMD helper file
        self.cpu_reader = cpu_reader or (lambda: sensors.read_lhm_cpu() or sensors.read_helper_file())
        self.gpu_reader = gpu_reader
        self.settings = dict(DEFAULTS)
        try:
            self.settings.update({k: v for k, v in json.loads(self.settings_path.read_text("utf-8")).items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass
        self._info = None
        self._dev = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._gpu_cache: sensors.Reading | None = None
        self.last = {"reading": None, "sent": None, "error": None, "at": None}

    # ---------- discovery ----------
    def health(self) -> AdapterHealth:
        return AdapterHealth(True, "direct HID")

    def discover(self) -> list[DiscoveredDevice]:
        match = [h for h in self.hid_provider() if h.vid == VID and h.pid == PID and (h.output_len or 0) >= 65]
        if not match:
            self._stop_feeder()
            self._info = None
            return []
        h = match[0]
        with self._lock:
            if self._info is None or self._info.path != h.path:
                self._close()
            self._info = h
        self._start_feeder()
        return [DiscoveredDevice(
            DeviceInfo("cooler:5131:2007", "AIO pump temperature display", Category.COOLER, self.name,
                       vendor="Ant Esports family (5131:2007)", model="7-segment pump-cap display", vidpid="5131:2007",
                       physical_key="usb:5131:2007", connection_path=self.control_path, controlled_by=["UniRGB (direct)"],
                       evidence=["HID 5131:2007, consumer page, 65-byte reports, no strings",
                                 "Protocol from the MIT-licensed Ant Esports controller (ICE-Infinity/ICE-Flow family), "
                                 "verified on an Ant Esports ICE-Storm 360 ARGB",
                                 "confirmed by you" if self.settings["confirmed"] else "NOT yet confirmed by you"]),
            Capabilities(display=Support.SUPPORTED,
                         notes=["CPU temperature comes from LibreHardwareMonitor (open source) with its Remote Web Server "
                                "on port 8085. If AMD Ryzen Master SDK is installed you can opt in to it instead. "
                                "Otherwise the GPU temperature is shown, labelled as such.",
                                "Pump and fan ARGB come from the motherboard ARGB headers: use the MSI Mystic Light entry.",
                                "5131:2007 is a generic USB chip also used by relay boards and other displays. "
                                "UniRGB sends nothing to it until you confirm it is your cooler display."]),
            Connection.CONNECTED)]

    # ---------- feeder ----------
    def _start_feeder(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="cooler-feeder", daemon=True)
        self._thread.start()

    def _stop_feeder(self) -> None:
        self._stop.set()

    def current_reading(self) -> sensors.Reading | None:
        src = self.settings["source"]
        if src in ("auto", "cpu"):
            r = self.cpu_reader()
            if r or src == "cpu":
                return r
        now = time.time()
        if self._gpu_cache is None or now - self._gpu_cache.at > 2.0:
            self._gpu_cache = self.gpu_reader() or self._gpu_cache
        return self._gpu_cache

    def _loop(self) -> None:
        while not self._stop.is_set():
            self.tick()
            self._stop.wait(self.interval)

    def tick(self) -> None:
        if not self.settings["enabled"]:
            return
        if not self.settings["confirmed"]:
            self.last.update(error="waiting for you to confirm this USB device is your cooler display")
            return
        r = self.current_reading()
        if r is None:
            self.last.update(error="no temperature source available", at=time.time())
            return
        pkt = antcooler.build_packet(r.celsius, self.settings["fahrenheit"], self.settings["anti_blink"])
        try:
            with self._lock:
                if self._info is None:
                    return
                if self._dev is None:
                    self._dev = self.open_device(self._info)
                self.write(self._dev, pkt)
            self.last.update(reading={"celsius": round(r.celsius, 1), "source": r.source, "label": r.label},
                             sent=pkt[2] & 0x7F, error=None, at=time.time())
        except Exception as e:
            with self._lock:
                self._close()
            self.last.update(error=str(e), at=time.time())

    # ---------- settings / status ----------
    def configure(self, device_id: str, settings: dict) -> ApplyResult:
        new = dict(self.settings)
        for k, v in settings.items():
            if k in ("enabled", "fahrenheit", "confirmed"):
                if not isinstance(v, bool):
                    return ApplyResult(False, message=f"{k} must be true/false")
            elif k == "source" and v not in SOURCES:
                return ApplyResult(False, message=f"source must be one of {SOURCES}")
            elif k == "anti_blink" and v not in antcooler.ANTI_BLINK:
                return ApplyResult(False, message=f"anti_blink must be one of {antcooler.ANTI_BLINK}")
            elif k not in DEFAULTS:
                return ApplyResult(False, message=f"unknown setting {k}")
            new[k] = v
        was_enabled = self.settings["enabled"]
        self.settings = new
        try:
            self.settings_path.parent.mkdir(parents=True, exist_ok=True)
            self.settings_path.write_text(json.dumps(new), encoding="utf-8")
        except OSError as e:
            log.warning("could not save cooler settings: %s", e)
        if was_enabled and not new["enabled"]:
            self._send_blank()
        else:
            self.tick()
        return ApplyResult(True, message="display settings saved")

    def _send_blank(self) -> None:
        try:
            with self._lock:
                if self._info and self._dev is None:
                    self._dev = self.open_device(self._info)
                if self._dev:
                    self.write(self._dev, antcooler.build_blank())
        except Exception:
            pass

    def status(self, device_id: str) -> dict:
        helper = sensors.read_helper_file()
        lhm = sensors.read_lhm()
        return {"settings": dict(self.settings), "last": dict(self.last),
                "lhm": {"running": lhm is not None, "fans": (lhm or {}).get("fans", [])},
                "cpu_helper": {"running": helper is not None,
                               "amd_cli_installed": sensors.AMD_CLI.exists()}}

    def start_cpu_helper(self) -> ApplyResult:
        """Launch the elevated helper. Windows shows a UAC prompt; nothing runs elevated without it."""
        if sys.platform != "win32":
            return ApplyResult(False, message="Windows only")
        exe = Path(sys.executable)
        pyw = exe.with_name("pythonw.exe")
        root = Path(__file__).resolve().parents[2]
        args = f'-m unirgb.cpu_temp_helper --parent {os.getpid()}'
        rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(pyw if pyw.exists() else exe), args, str(root), 0)
        if rc <= 32:
            return ApplyResult(False, message="UAC prompt was declined or the helper could not start")
        return ApplyResult(True, message="CPU sensor helper started; the display switches to CPU within a few seconds")

    def _close(self) -> None:
        if self._dev is not None:
            try:
                self._dev.close()
            finally:
                self._dev = None

    def shutdown(self) -> None:
        self._stop.set()
        with self._lock:
            self._close()
