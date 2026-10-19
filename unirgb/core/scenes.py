"""Scenes: named sets of per-device lighting states, persisted as JSON.

File format (version 1):
  {"version": 1, "scenes": {"<name>": {"devices": {"<device id>": <LightingState dict>}}}}
Writes are atomic (temp file + os.replace) and the previous file is kept as .bak.
"""
from __future__ import annotations

import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .models import ApplyResult, LightingState

FORMAT_VERSION = 1
_NAME = re.compile(r"^[\w .\-]{1,48}$")


def default_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    return Path(base) / "UniRGB" / "scenes.json"


class SceneStore:
    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path else default_path()
        self._lock = threading.Lock()
        self._scenes: dict[str, dict[str, LightingState]] = {}
        self.load_error: str | None = None
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            self._scenes = self.parse(self.path.read_text(encoding="utf-8"))
        except (ValueError, KeyError, OSError) as e:
            # never overwrite a file we could not read; surface it instead
            self.load_error = f"could not read {self.path.name}: {e}"
            self.path = self.path.with_name(self.path.stem + ".recovered.json")

    @staticmethod
    def parse(text: str) -> dict[str, dict[str, LightingState]]:
        doc = json.loads(text)
        if not isinstance(doc, dict) or doc.get("version") != FORMAT_VERSION:
            raise ValueError("unsupported scene file version")
        out = {}
        for name, sc in doc.get("scenes", {}).items():
            SceneStore.check_name(name)
            out[name] = {dev: LightingState.from_dict(st) for dev, st in sc["devices"].items()}
        return out

    def serialize(self) -> str:
        with self._lock:
            return json.dumps({"version": FORMAT_VERSION, "scenes": {
                n: {"devices": {d: s.to_dict() for d, s in devs.items()}} for n, devs in sorted(self._scenes.items())
            }}, indent=2)

    def _save(self) -> None:
        data = self.serialize()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(data, encoding="utf-8")
        if self.path.exists():
            bak = self.path.with_suffix(".json.bak")
            try:
                bak.write_bytes(self.path.read_bytes())
            except OSError:
                pass
        os.replace(tmp, self.path)

    @staticmethod
    def check_name(name: str) -> None:
        if not isinstance(name, str) or not _NAME.match(name):
            raise ValueError("scene name must be 1-48 chars: letters, digits, space, . _ -")

    def list(self) -> dict[str, dict[str, LightingState]]:
        with self._lock:
            return {n: dict(d) for n, d in self._scenes.items()}

    def put(self, name: str, devices: dict[str, LightingState]) -> None:
        self.check_name(name)
        if not devices:
            raise ValueError("a scene needs at least one device")
        with self._lock:
            self._scenes[name] = dict(devices)
        self._save()

    def delete(self, name: str) -> bool:
        with self._lock:
            existed = self._scenes.pop(name, None) is not None
        if existed:
            self._save()
        return existed

    def import_json(self, text: str) -> list[str]:
        incoming = self.parse(text)
        with self._lock:
            self._scenes.update(incoming)
        self._save()
        return sorted(incoming)

    def apply(self, name: str, orchestrator) -> dict[str, ApplyResult]:
        with self._lock:
            scene = dict(self._scenes.get(name) or {})
        if not scene:
            raise KeyError(name)
        # different adapters run in parallel; the orchestrator serialises per adapter
        with ThreadPoolExecutor(max(1, min(8, len(scene)))) as ex:
            futs = {dev: ex.submit(orchestrator.apply, dev, st) for dev, st in scene.items()}
            return {dev: f.result() for dev, f in futs.items()}
