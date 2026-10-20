"""Routes commands to adapters with isolation, serialisation, coalescing and timeouts.

* One single-thread executor per adapter: writes to one control path are
  serialised (no concurrent access to a device), while adapters run in parallel.
* Latest-wins coalescing: if a write for a device is still queued, a newer
  request replaces it instead of queueing behind it (slider drags stay cheap).
* Exceptions and hangs in an adapter are contained: callers get an error result
  after a timeout; a circuit breaker pauses an adapter after repeated failures.
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass

from .adapter import AdapterHealth, DeviceAdapter
from .models import ApplyResult, Confirmation, Connection, LightingState, Support
from .registry import DeviceRegistry

log = logging.getLogger("unirgb.orchestrator")

WRITE_OK = (Support.SUPPORTED, Support.EXPERIMENTAL, Support.UNTESTED)


def validate(state: LightingState, rec) -> str | None:
    """Return an error string if `state` is not allowed by the device's capabilities."""
    caps = rec.caps
    if not caps.writable:
        return "device is read-only (no verified control path)"
    if state.mode not in caps.effects:
        return f"effect '{state.mode}' not supported; available: {', '.join(caps.effects) or 'none'}"
    if state.mode == "static" and state.color is None and not state.zones:
        return "static mode needs a color or zone colors"
    if state.brightness != 100 and caps.brightness not in WRITE_OK:
        return "brightness control not supported on this device"
    if state.zones:
        if caps.zone_control not in WRITE_OK:
            return "per-zone control not supported on this device"
        known = {z.id for z in caps.zones}
        bad = [z for z in state.zones if z not in known]
        if bad:
            return f"unknown zone(s): {', '.join(bad)}"
    return None


@dataclass
class _Breaker:
    failures: int = 0
    open_until: float = 0.0


class Orchestrator:
    FAIL_THRESHOLD = 3
    COOLDOWN_S = 10.0

    def __init__(self, adapters: list[DeviceAdapter], registry: DeviceRegistry | None = None,
                 op_timeout: float = 5.0, discover_timeout: float = 10.0):
        names = [a.name for a in adapters]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate adapter names: {names}")
        self.adapters = {a.name: a for a in adapters}
        self.registry = registry or DeviceRegistry()
        self.op_timeout = op_timeout
        self.discover_timeout = discover_timeout
        self._exec = {a.name: ThreadPoolExecutor(1, thread_name_prefix=f"adapter-{a.name}") for a in adapters}
        self._pending: dict[str, tuple[LightingState, Future]] = {}
        self._plock = threading.Lock()
        self._breakers = {a.name: _Breaker() for a in adapters}
        self._health: dict[str, AdapterHealth] = {}
        self._closed = False
        self.on_change = None   # callback(device_id, LightingState | None) after a confirmed apply/restore

    # ---------- discovery ----------
    def discover_all(self) -> dict[str, AdapterHealth]:
        futs = {n: self._exec[n].submit(self._discover_one, a) for n, a in self.adapters.items()}
        for n, f in futs.items():
            try:
                f.result(timeout=self.discover_timeout)
            except FutureTimeout:
                self._health[n] = AdapterHealth(False, "discovery timed out")
                self.registry.mark_adapter(n, Connection.ERROR, "discovery timed out")
            except Exception as e:  # already recorded in _discover_one; belt and braces
                self._health[n] = AdapterHealth(False, f"discovery failed: {e}")
        return dict(self._health)

    def _discover_one(self, adapter: DeviceAdapter) -> None:
        try:
            health = adapter.health()
            found = adapter.discover()
            self._health[adapter.name] = health
            self.registry.replace_adapter_devices(adapter.name, adapter.priority, found)
        except Exception as e:
            log.exception("discovery failed for %s", adapter.name)
            self._health[adapter.name] = AdapterHealth(False, f"discovery failed: {e}")
            self.registry.mark_adapter(adapter.name, Connection.ERROR, str(e))

    def health(self) -> dict[str, AdapterHealth]:
        return dict(self._health)

    # ---------- writes ----------
    def apply(self, device_id: str, state: LightingState, wait: bool = True) -> ApplyResult:
        rec = self.registry.get(device_id)
        if rec is None:
            return ApplyResult(False, message="unknown device")
        if rec.shadowed_by:
            return ApplyResult(False, message=f"controlled through {rec.shadowed_by}; use that entry")
        if rec.connection not in (Connection.CONNECTED,):
            return ApplyResult(False, message=f"device is {rec.connection.value}")
        err = validate(state, rec)
        if err:
            return ApplyResult(False, message=err)
        adapter = self.adapters[rec.info.adapter]
        br = self._breakers[adapter.name]
        if br.open_until > time.monotonic():
            return ApplyResult(False, message=f"{adapter.name} paused after repeated failures; retry in a few seconds")
        self.registry.update(device_id, desired=state)

        with self._plock:
            pending = self._pending.get(device_id)
            if pending is not None:
                # a write is queued but not started: replace its payload (latest wins)
                self._pending[device_id] = (state, pending[1])
                fut = pending[1]
            else:
                fut = Future()
                self._pending[device_id] = (state, fut)
                self._exec[adapter.name].submit(self._run_apply, adapter, device_id)
        if not wait:
            return ApplyResult(True, message="queued")
        try:
            return fut.result(timeout=self.op_timeout)
        except FutureTimeout:
            return ApplyResult(False, message=f"timed out after {self.op_timeout:.0f}s (adapter still working)")

    def _run_apply(self, adapter: DeviceAdapter, device_id: str) -> None:
        with self._plock:
            state, fut = self._pending.pop(device_id)
        try:
            res = adapter.apply(device_id, state)
        except Exception as e:
            log.exception("apply failed on %s", device_id)
            res = ApplyResult(False, message=f"adapter error: {e}")
        self._record(adapter.name, device_id, res)
        fut.set_result(res)

    def restore(self, device_id: str) -> ApplyResult:
        rec = self.registry.get(device_id)
        if rec is None:
            return ApplyResult(False, message="unknown device")
        adapter = self.adapters[rec.info.adapter]
        fut = self._exec[adapter.name].submit(self._safe, adapter.restore, device_id)
        try:
            res = fut.result(timeout=self.op_timeout)
        except FutureTimeout:
            return ApplyResult(False, message="restore timed out")
        if res.ok:
            # adapters may release sibling devices that share one session
            for rid in {device_id, *res.released}:
                self.registry.update(rid, desired=None, confirmed=None,
                                     confirmation=Confirmation.NONE, last_error=None)
                if self.on_change:
                    self.on_change(rid, None)
        else:
            self.registry.update(device_id, last_error=res.message)
        return res

    def configure(self, device_id: str, settings: dict) -> ApplyResult:
        rec = self.registry.get(device_id)
        if rec is None:
            return ApplyResult(False, message="unknown device")
        adapter = self.adapters[rec.info.adapter]
        fut = self._exec[adapter.name].submit(self._safe, adapter.configure, device_id, settings)
        try:
            return fut.result(timeout=self.op_timeout)
        except FutureTimeout:
            return ApplyResult(False, message="configure timed out")

    def status(self, device_id: str) -> dict:
        rec = self.registry.get(device_id)
        if rec is None:
            return {}
        try:
            return self.adapters[rec.info.adapter].status(device_id)
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def _safe(fn, *a) -> ApplyResult:
        try:
            return fn(*a)
        except Exception as e:
            return ApplyResult(False, message=f"adapter error: {e}")

    def _record(self, adapter: str, device_id: str, res: ApplyResult) -> None:
        br = self._breakers[adapter]
        if res.ok:
            br.failures = 0
            self.registry.update(device_id, confirmed=res.applied, confirmation=res.confirmation, last_error=None)
            if self.on_change and res.applied is not None:
                self.on_change(device_id, res.applied)
        else:
            br.failures += 1
            if br.failures >= self.FAIL_THRESHOLD:
                br.open_until = time.monotonic() + self.COOLDOWN_S
                br.failures = 0
            self.registry.update(device_id, last_error=res.message)

    # ---------- lifecycle ----------
    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        for n, a in self.adapters.items():
            try:
                self._exec[n].submit(a.shutdown).result(timeout=self.op_timeout)
            except Exception:
                log.warning("adapter %s did not shut down cleanly", n)
            self._exec[n].shutdown(wait=False, cancel_futures=True)
