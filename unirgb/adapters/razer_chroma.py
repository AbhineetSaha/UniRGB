"""Razer devices through Razer's documented Chroma SDK REST API.

Path: UniRGB -> HTTP localhost:54235 (RzSDKServer, part of Synapse 4) -> Synapse
device stack -> device. We never talk to the mouse's HID interfaces ourselves, so
Synapse keeps ownership and there is no write contention with it.

Session semantics (Razer Chroma REST docs):
  POST /razer/chromasdk            -> {"sessionid", "uri"} (per-session port)
  PUT  {uri}/heartbeat             -> documented as required every 15 s (see journal note)
  PUT  {uri}/mouse|chromalink|...  -> {"result": 0} on success
  DELETE {uri}                     -> ends the session; Synapse resumes its own lighting
The REST API has no "get current lighting" call, so confirmed state is only
ever "api-accepted", never a hardware read-back.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Color, Confirmation, DeviceInfo,
                           LightingState, Support, Zone)

log = logging.getLogger("unirgb.razer")

# HTTP.sys URL reservation is for host "localhost": requests addressed to 127.0.0.1 get
# "400 Invalid Hostname" (observed on this machine), so the hostname must stay "localhost".
DEFAULT_BASE = "http://localhost:54235/razer/chromasdk"
RAZER_VID = 0x1532
HEARTBEAT_S = 5.0


def default_journal() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UniRGB" / "chroma_session.json"

APP_INFO = {
    "title": "UniRGB Control Center",
    "description": "Unified local device and RGB control",
    "author": {"name": "UniRGB", "contact": "local"},
    "device_supported": ["mouse", "chromalink"],
    "category": "application",
}

# Chroma mouse custom grid is 9 rows x 7 columns (RZLED2 layout from the Chroma SDK).
MOUSE_ROWS, MOUSE_COLS = 9, 7
MOUSE_ZONES: dict[str, list[tuple[int, int]]] = {
    "scroll": [(2, 3)],
    "logo": [(7, 3)],
    "underglow": [(r, 0) for r in range(1, 8)] + [(r, 6) for r in range(1, 8)] + [(8, c) for c in range(1, 6)],
}

RESULT_CODES = {0: "success", 5: "access denied", 6: "invalid handle", 87: "invalid parameter",
                1167: "device not connected", 1168: "element not found", 4319: "not supported",
                -1: "failed"}


def bgr(c: Color) -> int:
    """Chroma encodes colors as 0x00BBGGRR."""
    return (c.b << 16) | (c.g << 8) | c.r


class ChromaError(Exception):
    pass


class RazerChromaAdapter(DeviceAdapter):
    name = "razer"
    priority = 10   # official vendor path beats generic/direct-HID paths
    control_path = "Chroma SDK REST (localhost:54235, HTTP.sys) -> Razer Synapse -> device"

    def __init__(self, hid_provider: Callable[[], list] | None = None, base_url: str = DEFAULT_BASE,
                 timeout: float = 2.0, heartbeat_s: float = HEARTBEAT_S, journal: Path | None = None):
        self.base_url = base_url
        # Chroma SDK 4.00.03 on this machine kept an abandoned session alive well past the
        # documented 15 s heartbeat timeout, so a crash would leave our colors in place. We
        # journal the live session and delete a stale one on the next start.
        self.journal = journal if journal is not None else default_journal()
        self._recovered = False
        self.timeout = timeout
        self.heartbeat_s = heartbeat_s
        self.hid_provider = hid_provider or (lambda: [])
        self._session_uri: str | None = None
        self._slock = threading.Lock()   # guards session between worker and heartbeat thread
        self._hb_stop = threading.Event()
        self._hb_thread: threading.Thread | None = None
        self._version: dict | None = None
        self._devices: dict[str, str] = {}   # device id -> chroma endpoint

    # ---------- HTTP ----------
    def _http(self, method: str, url: str, body: dict | None = None, timeout: float | None = None) -> dict:
        # HTTP.sys answers 411 to a PUT/POST without Content-Length; http.client adds
        # "Content-Length: 0" for body-less PUT/POST itself (verified against RzSDKServer).
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            raise ChromaError(f"HTTP {e.code} from {method} {url}") from e
        except (urllib.error.URLError, OSError) as e:
            raise ChromaError(f"cannot reach Chroma SDK: {getattr(e, 'reason', e)}") from e
        try:
            return json.loads(raw) if raw else {}
        except ValueError as e:
            raise ChromaError("Chroma SDK returned non-JSON response") from e

    # ---------- discovery ----------
    def health(self) -> AdapterHealth:
        try:
            v = self._http("GET", self.base_url, timeout=0.5)   # "localhost" tries IPv6 then IPv4; keep scans fast when Synapse is off
            self._version = v
            return AdapterHealth(True, f"Chroma SDK {v.get('version', '?')} reachable", {"version": v})
        except ChromaError as e:
            self._version = None
            return AdapterHealth(False, str(e))

    def recover_stale_session(self) -> str | None:
        """Delete a session left behind by a previous crashed run. Returns its uri."""
        self._recovered = True
        try:
            uri = json.loads(self.journal.read_text(encoding="utf-8")).get("uri")
        except (OSError, ValueError):
            return None
        if uri and uri != self._session_uri:
            try:
                self._http("DELETE", uri)
                log.info("deleted stale Chroma session %s from a previous run", uri)
            except ChromaError:
                pass   # already gone
        self._journal_write(None)
        return uri

    def _journal_write(self, uri: str | None) -> None:
        try:
            if uri:
                self.journal.parent.mkdir(parents=True, exist_ok=True)
                self.journal.write_text(json.dumps({"uri": uri, "pid": os.getpid()}), encoding="utf-8")
            else:
                self.journal.unlink(missing_ok=True)
        except OSError as e:
            log.warning("chroma session journal: %s", e)

    def discover(self) -> list[DiscoveredDevice]:
        if self._version is None and not self.health().available:
            self._devices = {}
            return []
        if not self._recovered:
            self.recover_stale_session()
        out: list[DiscoveredDevice] = []
        self._devices = {}
        mice = {}
        for h in self.hid_provider():
            if h.vid == RAZER_VID and h.usage_page == 0x01 and h.usage == 0x02:
                mice.setdefault(f"{h.vid:04X}:{h.pid:04X}", h)
        for vidpid, h in mice.items():
            dev_id = f"razer:mouse:{vidpid}"
            self._devices[dev_id] = "mouse"
            name = h.product or f"Razer mouse {vidpid}"
            out.append(DiscoveredDevice(
                DeviceInfo(dev_id, name, Category.MOUSE, self.name, vendor="Razer", model=name, vidpid=vidpid,
                           physical_key=f"usb:{vidpid}", connection_path=self.control_path,
                           controlled_by=["Razer Synapse 4", "Razer Chroma SDK Server"],
                           evidence=[f"HID {vidpid} '{name}' present (usage 01:02)",
                                     f"Chroma SDK {self._version.get('version')} answered GET"]),
                Capabilities(
                    read_state=Support.UNSUPPORTED, color=Support.SUPPORTED,
                    brightness=Support.SUPPORTED, brightness_native=False,
                    effects=["static", "off"],
                    zones=[Zone("scroll", "Scroll wheel"), Zone("logo", "Logo"),
                           Zone("underglow", "Underglow strip", led_count=len(MOUSE_ZONES["underglow"]))],
                    zone_control=Support.EXPERIMENTAL, restore=Support.SUPPORTED,
                    notes=["Chroma's mouse endpoint is a generic 9x7 grid. Zone placement on this "
                           "particular mouse is taken from Razer's RZLED2 layout and has not been checked "
                           "against the physical LEDs.",
                           "Brightness is applied by scaling colors; the Chroma API has no brightness call.",
                           "Chroma has no read-back call. The confirmed state means Synapse accepted the "
                           "command, not that anyone looked at the LEDs.",
                           "Restore ends the Chroma session, which returns every Razer device to its Synapse profile."])))
        # ChromaLink fans out to Chroma Connect partners (e.g. MSI Mystic Light "Razer Sync").
        dev_id = "razer:chromalink"
        self._devices[dev_id] = "chromalink"
        out.append(DiscoveredDevice(
            DeviceInfo(dev_id, "Chroma Connect (ChromaLink)", Category.LIGHTING_LINK, self.name, vendor="Razer",
                       physical_key=None, connection_path=self.control_path,
                       controlled_by=["Razer Chroma SDK Server", "partner apps, e.g. MSI Center Razer Sync"],
                       evidence=["ChromaLink is a Chroma SDK device class that partner software can subscribe to",
                                 "MSI Mystic Light log shows '-Razer Sync Init' at startup"]),
            Capabilities(read_state=Support.UNSUPPORTED, color=Support.EXPERIMENTAL,
                         brightness=Support.EXPERIMENTAL, effects=["static", "off"],
                         restore=Support.SUPPORTED,
                         notes=["Which physical lights follow ChromaLink depends on partner apps. MSI Center "
                                "follows it only when Mystic Light is set to sync with Razer Chroma.",
                                "Experimental: the API accepts the command, but no physical effect has been verified."])))
        return out

    # ---------- session ----------
    def _ensure_session(self) -> str:
        with self._slock:
            if self._session_uri:
                return self._session_uri
            resp = self._http("POST", self.base_url, APP_INFO)
            uri = resp.get("uri")
            if not uri:
                raise ChromaError(f"session not created: {resp}")
            self._session_uri = uri
            self._journal_write(uri)
            log.info("Chroma session %s", resp.get("sessionid"))
        self._start_heartbeat()
        return self._session_uri

    def _start_heartbeat(self) -> None:
        if self._hb_thread and self._hb_thread.is_alive():
            if not self._hb_stop.is_set():
                return
            self._hb_thread.join(timeout=self.timeout + 1)   # old loop is exiting after a restore
        self._hb_stop.clear()
        self._hb_thread = threading.Thread(target=self._heartbeat_loop, name="chroma-heartbeat", daemon=True)
        self._hb_thread.start()

    def _heartbeat_loop(self) -> None:
        while not self._hb_stop.wait(self.heartbeat_s):
            with self._slock:
                uri = self._session_uri
            if not uri:
                return
            try:
                self._http("PUT", uri + "/heartbeat")
            except ChromaError as e:
                log.warning("heartbeat failed, session dropped: %s", e)
                self._abandon(uri)
                return

    def _abandon(self, uri: str) -> None:
        """Forget a session that stopped answering; delete it in case it still exists."""
        with self._slock:
            if self._session_uri != uri:
                return
            self._session_uri = None
        try:
            self._http("DELETE", uri)
        except ChromaError:
            pass
        self._journal_write(None)

    def _put_effect(self, endpoint: str, body: dict) -> None:
        for attempt in (1, 2):
            uri = self._ensure_session()
            try:
                resp = self._http("PUT", f"{uri}/{endpoint}", body)
            except ChromaError:
                # session port vanishes when Synapse restarts: recreate once
                self._abandon(uri)
                if attempt == 2:
                    raise
                continue
            code = resp.get("result", -1)
            if code != 0:
                raise ChromaError(f"Chroma result {code} ({RESULT_CODES.get(code, 'unknown')})")
            return

    # ---------- control ----------
    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        endpoint = self._devices.get(device_id)
        if endpoint is None:
            return ApplyResult(False, message="device not present in Chroma discovery")
        try:
            if state.mode == "off":
                body = {"effect": "CHROMA_NONE"}
            elif endpoint == "mouse" and state.zones:
                body = {"effect": "CHROMA_CUSTOM2", "param": self._mouse_grid(state)}
            else:
                body = {"effect": "CHROMA_STATIC", "param": {"color": bgr(state.color.scaled(state.brightness))}}
            self._put_effect(endpoint, body)
        except ChromaError as e:
            return ApplyResult(False, message=str(e))
        return ApplyResult(True, Confirmation.API_ACCEPTED, "accepted by Chroma SDK", applied=state)

    @staticmethod
    def _mouse_grid(state: LightingState) -> list[list[int]]:
        base = bgr(state.color.scaled(state.brightness)) if state.color else 0
        grid = [[base] * MOUSE_COLS for _ in range(MOUSE_ROWS)]
        for zone, color in state.zones.items():
            v = bgr(color.scaled(state.brightness))
            for r, c in MOUSE_ZONES[zone]:
                grid[r][c] = v
        return grid

    def restore(self, device_id: str) -> ApplyResult:
        released = [d for d in self._devices if d != device_id]
        self._end_session()
        return ApplyResult(True, message="Chroma session ended; Synapse resumed its own lighting on all Razer devices",
                           released=released)

    def _end_session(self) -> None:
        self._hb_stop.set()
        with self._slock:
            uri, self._session_uri = self._session_uri, None
        if uri:
            try:
                self._http("DELETE", uri)
                self._journal_write(None)
            except ChromaError as e:
                log.info("session delete failed; journal kept for cleanup on next start: %s", e)

    def shutdown(self) -> None:
        try:
            self._end_session()
        except Exception:
            pass
