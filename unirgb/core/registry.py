"""Thread-safe device registry with cross-adapter ownership resolution."""
from __future__ import annotations

import copy
import threading
import time

from .adapter import DiscoveredDevice
from .models import Connection, DeviceRecord


class DeviceRegistry:
    def __init__(self):
        self._lock = threading.RLock()
        self._records: dict[str, DeviceRecord] = {}
        self._priorities: dict[str, int] = {}

    def replace_adapter_devices(self, adapter: str, priority: int, found: list[DiscoveredDevice]) -> None:
        """Swap in a fresh discovery result for one adapter, keeping user state."""
        with self._lock:
            self._priorities[adapter] = priority
            old = {k: v for k, v in self._records.items() if v.info.adapter == adapter}
            seen = set()
            for d in found:
                rec = old.get(d.info.id)
                if rec:
                    rec.info, rec.caps, rec.connection = d.info, d.caps, d.connection
                    if d.connection != Connection.CONNECTED:
                        rec.confirmed = None   # e.g. a sleeping mouse loses live colors
                    rec.updated_at = time.time()
                else:
                    self._records[d.info.id] = DeviceRecord(d.info, d.caps, d.connection)
                seen.add(d.info.id)
            for k, rec in old.items():
                if k not in seen:   # keep the record so the UI can show "disconnected"
                    rec.connection = Connection.UNAVAILABLE
                    rec.confirmed = None
            self._resolve_ownership()

    def mark_adapter(self, adapter: str, connection: Connection, error: str | None) -> None:
        with self._lock:
            for rec in self._records.values():
                if rec.info.adapter == adapter:
                    rec.connection = connection
                    rec.last_error = error

    def _resolve_ownership(self) -> None:
        groups: dict[str, list[DeviceRecord]] = {}
        for rec in self._records.values():
            rec.shadowed_by = None
            if rec.info.physical_key and rec.connection != Connection.UNAVAILABLE:
                groups.setdefault(rec.info.physical_key, []).append(rec)
        for recs in groups.values():
            if len(recs) < 2:
                continue
            # writable beats monitor-only, then adapter priority, then id for determinism
            recs.sort(key=lambda r: (not r.caps.writable, self._priorities.get(r.info.adapter, 999), r.info.id))
            owner = recs[0]
            for r in recs[1:]:
                r.shadowed_by = owner.info.id

    def get(self, device_id: str) -> DeviceRecord | None:
        with self._lock:
            return self._records.get(device_id)

    def update(self, device_id: str, **fields) -> None:
        with self._lock:
            rec = self._records.get(device_id)
            if rec:
                for k, v in fields.items():
                    setattr(rec, k, v)
                rec.updated_at = time.time()

    def snapshot(self) -> list[DeviceRecord]:
        """Deep copies, safe to serialise outside the lock."""
        with self._lock:
            return [copy.deepcopy(r) for r in sorted(self._records.values(), key=lambda r: (r.info.category.value, r.info.name))]

    def ids_for_adapter(self, adapter: str) -> list[str]:
        with self._lock:
            return [k for k, r in self._records.items() if r.info.adapter == adapter]
