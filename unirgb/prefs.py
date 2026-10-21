"""Choices made at first start: which optional features need the PawnIO driver.

Stored as prefs.json next to the scenes file (%APPDATA%\\UniRGB). Lighting needs none of this;
the privileged one-time setup only ever happens for a feature the user ticked here.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

FIELDS = ("setup_done", "cpu_temperature", "ram_lighting")
# RAM lighting stays unavailable until UniRGB's own helper can write (today only a read-only probe exists).
AVAILABLE = {"cpu_temperature": True, "ram_lighting": True}


@dataclass
class Prefs:
    setup_done: bool = False
    cpu_temperature: bool = False
    ram_lighting: bool = False

    @property
    def needs_driver(self) -> bool:
        return self.cpu_temperature or self.ram_lighting


class PrefsStore:
    def __init__(self, path: Path):
        self.path = path
        self.prefs = self._load()

    def _load(self) -> Prefs:
        try:
            d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return Prefs()   # missing or unreadable: ask again on this start
        if not isinstance(d, dict):
            return Prefs()
        return Prefs(**{k: d[k] for k in FIELDS if isinstance(d.get(k), bool)})

    def update(self, changes) -> Prefs:
        """Validate and persist. Rejects unknown keys, non-booleans and unavailable features."""
        if not isinstance(changes, dict):
            raise ValueError("expected a JSON object")
        unknown = sorted(set(changes) - set(FIELDS))
        if unknown:
            raise ValueError(f"unknown preference: {', '.join(unknown)}")
        if not all(isinstance(v, bool) for v in changes.values()):
            raise ValueError("preferences must be true or false")
        for k, v in changes.items():
            if v and AVAILABLE.get(k) is False:
                raise ValueError(f"{k.replace('_', ' ')} is not available yet")
        new = Prefs(**{**asdict(self.prefs), **changes})
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(asdict(new), indent=2), encoding="utf-8")
        os.replace(tmp, self.path)   # atomic: a crash never leaves half a file
        self.prefs = new
        return new

    def to_dict(self) -> dict:
        return {**asdict(self.prefs), "needs_driver": self.prefs.needs_driver, "available": dict(AVAILABLE)}
