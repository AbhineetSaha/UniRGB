"""Composition root: wires adapters, orchestrator, scenes and the local HTTP UI."""
from __future__ import annotations

import json
import logging
import os
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
from .core.models import Connection, LightingState
from .core.orchestrator import Orchestrator
from .core.scenes import SceneStore
from . import sensors, system_setup
from .hostos import windows_hid, windows_system
from .prefs import PrefsStore

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
        self._helper_started = float("-inf")
        self.hid = hid_cache or HidCache()
        if adapters is None:
            adapters = [RazerChromaAdapter(self.hid.get), OpenRGBAdapter(port=openrgb_port),
                        MysticLightMonitor(self.hid.get), InventoryAdapter(self.hid.get, windows_system.hardware_summary)]
            if direct:
                procs = windows_system.running_processes
                board = lambda: ((windows_system.hardware_summary().get("board") or {}).get("Product") or "")
                cpu = lambda: (sensors.read_hw_helper(self._start_helper) or sensors.read_lhm_cpu()
                               or sensors.read_helper_file())
                adapters = [CoolerDisplayAdapter(self.hid.get, cpu_reader=cpu), KreoDirectAdapter(self.hid.get), RazerDirectAdapter(self.hid.get, process_provider=procs),
                            MsiDirectAdapter(self.hid.get, process_provider=procs, board_provider=board)] + adapters
            if simulate:
                adapters.append(SimulatedAdapter())
        self.orch = Orchestrator(adapters)
        self.scenes = SceneStore(scenes_path)
        self.last_path = self.scenes.path.parent / "last_state.json"
        self.prefs = PrefsStore(self.scenes.path.parent / "prefs.json")
        self._saved_lock = threading.Lock()
        self._saved = self._load_saved()
        self.orch.on_change = self._remember
        self.rescan_interval = rescan_interval
        self._stop = threading.Event()
        self.quit_requested = threading.Event()
        self._scan_lock = threading.Lock()
        self.last_scan: float = 0.0
        self.last_scan_ms: float = 0.0

    def _start_helper(self) -> None:
        """Start the privileged helper through its task: only if the user enabled it, at most every 30 s."""
        now = time.monotonic()
        if self.prefs.prefs.cpu_temperature and now - self._helper_started > 30:
            self._helper_started = now
            if system_setup.driver_state() != "not-installed":   # without it the helper only fails; Settings offers setup
                system_setup.start_helper()

    def rescan(self, full: bool = False) -> None:
        with self._scan_lock:
            t0 = time.perf_counter()
            self.hid.refresh()
            if full:
                windows_system.hardware_summary(refresh=True)
            self.orch.discover_all()
            self._reapply_saved()
            self.last_scan = time.time()
            self.last_scan_ms = (time.perf_counter() - t0) * 1000

    def _load_saved(self) -> dict:
        try:
            return {k: LightingState.from_dict(v) for k, v in json.loads(self.last_path.read_text("utf-8")).items()}
        except (OSError, ValueError, TypeError, AttributeError):
            return {}

    def _remember(self, device_id: str, state) -> None:
        with self._saved_lock:
            if state is None:
                self._saved.pop(device_id, None)
            else:
                self._saved[device_id] = state
            data = json.dumps({k: v.to_dict() for k, v in self._saved.items()})
            try:
                self.last_path.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.last_path.with_suffix(".tmp")
                tmp.write_text(data, encoding="utf-8")
                os.replace(tmp, self.last_path)
            except OSError as e:
                log.warning("could not save last lighting state: %s", e)

    def _reapply_saved(self) -> None:
        """Give each device back its last confirmed lighting once it is online and writable."""
        with self._saved_lock:
            saved = dict(self._saved)
        for dev, st in saved.items():
            rec = self.orch.registry.get(dev)
            # skip devices already showing it, and never override a newer request the user made
            if (rec and rec.connection == Connection.CONNECTED and rec.caps.writable and not rec.shadowed_by
                    and rec.confirmed is None and rec.desired in (None, st)):
                self.orch.apply(dev, st, wait=False)

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
