"""Composition root: wires adapters, orchestrator, scenes and the local HTTP UI."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from .adapters.cooler_display import CoolerDisplayAdapter
from .adapters.inventory import InventoryAdapter
from .adapters.kreo_direct import KreoDirectAdapter
from .adapters.msi_direct import MsiDirectAdapter
from .adapters.msi_mystic import MysticLightMonitor
from .adapters.openrgb import OpenRGBAdapter
from .adapters.razer_chroma import RazerChromaAdapter
from .adapters.razer_direct import RazerDirectAdapter
from .adapters.simulated import SimulatedAdapter
from .core.orchestrator import Orchestrator
from .core.scenes import SceneStore
from .hostos import windows_hid, windows_system

log = logging.getLogger("unirgb")
VERSION = "0.1.0"


class HidCache:
    """One HID enumeration per discovery cycle, shared by every adapter."""

    def __init__(self, enumerate_fn=windows_hid.enumerate_hid):
        self._fn = enumerate_fn
        self._lock = threading.Lock()
        self._items: list = []
        self.error: str | None = None

    def refresh(self) -> None:
        try:
            items = self._fn()
            err = None
        except OSError as e:
            items, err = [], f"HID enumeration failed: {e}"
        with self._lock:
            self._items, self.error = items, err

    def get(self) -> list:
        with self._lock:
            return list(self._items)


class App:
    def __init__(self, simulate: bool = False, direct: bool = True, scenes_path: Path | None = None, openrgb_port: int = 6742,
                 adapters=None, hid_cache: HidCache | None = None, rescan_interval: float = 15.0):
        self.simulate = simulate
        self.hid = hid_cache or HidCache()
        if adapters is None:
            adapters = [RazerChromaAdapter(self.hid.get), OpenRGBAdapter(port=openrgb_port),
                        MysticLightMonitor(self.hid.get), InventoryAdapter(self.hid.get, windows_system.hardware_summary)]
            if direct:
                procs = windows_system.running_processes
                board = lambda: ((windows_system.hardware_summary().get("board") or {}).get("Product") or "")
                adapters = [CoolerDisplayAdapter(self.hid.get), KreoDirectAdapter(self.hid.get), RazerDirectAdapter(self.hid.get, process_provider=procs),
                            MsiDirectAdapter(self.hid.get, process_provider=procs, board_provider=board)] + adapters
            if simulate:
                adapters.append(SimulatedAdapter())
        self.orch = Orchestrator(adapters)
        self.scenes = SceneStore(scenes_path)
        self.rescan_interval = rescan_interval
        self._stop = threading.Event()
        self.quit_requested = threading.Event()
        self._scan_lock = threading.Lock()
        self.last_scan: float = 0.0
        self.last_scan_ms: float = 0.0

    def rescan(self, full: bool = False) -> None:
        with self._scan_lock:
            t0 = time.perf_counter()
            self.hid.refresh()
            if full:
                windows_system.hardware_summary(refresh=True)
            self.orch.discover_all()
            self.last_scan = time.time()
            self.last_scan_ms = (time.perf_counter() - t0) * 1000

    def start_background(self) -> None:
        def loop():
            while not self._stop.wait(self.rescan_interval):
                try:
                    self.rescan()
                except Exception:
                    log.exception("background rescan failed")
        threading.Thread(target=loop, name="rescan", daemon=True).start()

    def request_quit(self) -> None:
        self.quit_requested.set()

    def shutdown(self) -> None:
        self._stop.set()
        self.orch.shutdown()
