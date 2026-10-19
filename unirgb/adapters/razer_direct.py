"""Razer Basilisk V3 Pro over raw HID feature reports, bypassing Synapse.

Protocol: unirgb/protocols/razer.py (openrazer-documented). All lighting writes use
NOSTORE, so the profile saved on the mouse (VARSTORE) is never overwritten.
Synapse may still send its own commands to the same interface; responses are
matched by command class/id and retried, but Synapse can re-apply its lighting.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Callable

from ..core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from ..core.models import (ApplyResult, Capabilities, Category, Color, Confirmation, Connection, DeviceInfo,
                           LightingState, Support, Zone)
from ..protocols import razer as rz

RAZER_VID = 0x1532
SUPPORTED = {0x00AA: "Razer Basilisk V3 Pro (wired)", 0x00AB: "Razer Basilisk V3 Pro (HyperSpeed)"}
COLS = 13
# Column order from OpenRGB's Basilisk V3 Pro table: scroll wheel, logo, 11-LED strip.
ZONES = {"scroll": [0], "logo": [1], "underglow": list(range(2, 13))}


def _default_open(info):
    from ..hostos.hid_io import HidDevice
    return HidDevice(info)


class RazerDirectAdapter(DeviceAdapter):
    name = "razer-hid"
    priority = 5   # the user asked for direct control: wins over the Chroma path when reachable
    control_path = "UniRGB -> HID feature report 0 (interface 0) -> HyperSpeed receiver -> mouse (Synapse bypassed)"

    def __init__(self, hid_provider: Callable[[], list] | None = None, open_device=_default_open,
                 process_provider: Callable[[], set] | None = None, baseline_dir: Path | None = None):
        self.baseline_dir = baseline_dir or Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UniRGB"
        self.hid_provider = hid_provider or (lambda: [])
        self.open_device = open_device
        self.process_provider = process_provider or (lambda: set())
        self._devs: dict[str, object] = {}     # device id -> open HidDevice
        self._transport: dict[str, rz.RazerTransport] = {}
        self._info: dict[str, object] = {}

    def health(self) -> AdapterHealth:
        return AdapterHealth(True, "direct HID")

    def _transport_for(self, dev_id: str) -> rz.RazerTransport:
        t = self._transport.get(dev_id)
        if t is None:
            d = self.open_device(self._info[dev_id])
            self._devs[dev_id] = d
            t = self._transport[dev_id] = rz.RazerTransport(d)
        return t

    def _drop(self, dev_id: str) -> None:
        d = self._devs.pop(dev_id, None)
        self._transport.pop(dev_id, None)
        if d is not None:
            try:
                d.close()
            except Exception:
                pass

    def discover(self) -> list[DiscoveredDevice]:
        out = []
        seen = set()
        synapse = "razerappengine.exe" in self.process_provider()
        for h in self.hid_provider():
            if h.vid != RAZER_VID or h.pid not in SUPPORTED or h.interface_number != 0 or (h.feature_len or 0) < 91:
                continue
            vidpid = f"{h.vid:04X}:{h.pid:04X}"
            dev_id = f"razer-hid:{vidpid}"
            if dev_id in seen:
                continue
            seen.add(dev_id)
            if dev_id not in self._info or self._info[dev_id].path != h.path:
                self._drop(dev_id)
            self._info[dev_id] = h
            evidence = [f"HID {vidpid} interface 0, feature report {h.feature_len} bytes"]
            conn, notes = Connection.CONNECTED, []
            try:
                fw = self._transport_for(dev_id).transact(rz.get_firmware())
                evidence.append(f"firmware v{fw['args'][0]}.{fw['args'][1]} read over HID (device answered)")
            except Exception as e:
                conn = Connection.UNAVAILABLE
                notes.append(f"The receiver answered, but the mouse did not ({e}). It is probably asleep or "
                             "switched off. Move it and press Rescan.")
            if synapse:
                notes.append("Razer Synapse is running and talks to the same interface. It can re-apply its own "
                             "lighting over UniRGB's. For exclusive control, quit Synapse.")
            notes += ["Lighting is written NOSTORE: the profile saved on the mouse is never changed. A sleep/wake, "
                      "a replug or Synapse brings the saved look back.",
                      "Zone columns follow OpenRGB's table (scroll 0, logo 1, strip 2-12). Not checked against the physical LEDs yet."]
            out.append(DiscoveredDevice(
                DeviceInfo(dev_id, SUPPORTED[h.pid], Category.MOUSE, self.name, vendor="Razer", model=SUPPORTED[h.pid],
                           vidpid=vidpid, physical_key=f"usb:{vidpid}", connection_path=self.control_path,
                           controlled_by=["UniRGB (direct)"] + (["Razer Synapse (also running)"] if synapse else []),
                           evidence=evidence),
                Capabilities(read_state=Support.SUPPORTED, color=Support.SUPPORTED,
                             brightness=Support.SUPPORTED, brightness_native=True, effects=["static", "off"],
                             zones=[Zone("scroll", "Scroll wheel"), Zone("logo", "Logo"),
                                    Zone("underglow", "Underglow strip", 11)],
                             zone_control=Support.EXPERIMENTAL, restore=Support.EXPERIMENTAL, notes=notes),
                conn))
        for gone in set(self._info) - seen:
            self._drop(gone)
            self._info.pop(gone, None)
        return out

    def apply(self, device_id: str, state: LightingState) -> ApplyResult:
        if device_id not in self._info:
            return ApplyResult(False, message="device not present")
        try:
            t = self._transport_for(device_id)
            if state.mode == "off":
                t.transact(rz.effect_none())
            elif state.zones:
                base = state.color or Color(0, 0, 0)
                cols = [base] * COLS
                for z, c in state.zones.items():
                    for i in ZONES[z]:
                        cols[i] = c
                t.transact(rz.set_custom_frame(0, 0, COLS - 1, b"".join(bytes((c.r, c.g, c.b)) for c in cols)))
                t.transact(rz.effect_custom_frame())
                t.transact(rz.set_brightness(round(state.brightness * 255 / 100)))
            else:
                c = state.color
                t.transact(rz.effect_static(c.r, c.g, c.b))
                t.transact(rz.set_brightness(round(state.brightness * 255 / 100)))
            live = t.transact(rz.get_brightness(store=rz.NOSTORE, led=rz.READBACK_LED))["args"][2]
        except Exception as e:
            self._drop(device_id)
            return ApplyResult(False, message=f"direct HID: {e}")
        want = round(state.brightness * 255 / 100)
        if state.mode != "off" and live != want:
            return ApplyResult(False, Confirmation.DEVICE_ACK,
                               f"mouse acknowledged, but brightness reads back {live}/255 instead of {want}", applied=state)
        return ApplyResult(True, Confirmation.DEVICE_ACK,
                           f"mouse acknowledged; brightness read back {round(live * 100 / 255)}%", applied=state)

    def read_state(self, device_id: str) -> LightingState | None:
        """Only brightness can be read back; colors have no documented read command."""
        try:
            r = self._transport_for(device_id).transact(rz.get_brightness(store=rz.NOSTORE, led=rz.READBACK_LED))
        except Exception:
            return None
        return LightingState(mode="static", brightness=round(r["args"][2] * 100 / 255))

    def restore(self, device_id: str) -> ApplyResult:
        """Partial: copies the saved (VARSTORE) brightness back to the live slot. The saved
        colors/effect have no documented reload command; they return on wake, replug or from Synapse."""
        if device_id not in self._info:
            return ApplyResult(False, message="device not present")
        try:
            t = self._transport_for(device_id)
            saved = t.transact(rz.get_brightness(store=rz.VARSTORE, led=rz.READBACK_LED))["args"][2]
            t.transact(rz.set_brightness(saved))
        except Exception as e:
            self._drop(device_id)
            return ApplyResult(False, message=f"restore failed: {e}")
        return ApplyResult(True, message=f"brightness restored to the saved {round(saved * 100 / 255)}%. Saved colors "
                                         "come back after the mouse sleeps and wakes, on replug, or when Synapse re-applies")

    # ---------- mouse settings (replaces Synapse's device page) ----------
    SETTING_KEYS = ("dpi", "stages", "active_stage", "poll_hz", "idle_s")

    def _read_settings(self, t) -> dict:
        x, y = rz.decode_dpi(t.transact(rz.get_dpi(rz.NOSTORE))["args"])
        active, stages = rz.decode_stages(t.transact(rz.get_dpi_stages())["args"])
        idle = t.transact(rz.get_idle_time())["args"]
        return {"dpi": [x, y], "stages": [list(s) for s in stages], "active_stage": active,
                "poll_hz": rz.POLL_RATES.get(t.transact(rz.get_poll_rate())["args"][0]),
                "battery_pct": round(t.transact(rz.get_battery())["args"][1] * 100 / 255),
                "charging": bool(t.transact(rz.get_charging())["args"][1]),
                "idle_s": (idle[0] << 8) | idle[1],
                "low_battery_pct": round(t.transact(rz.get_low_battery())["args"][0] * 100 / 255)}

    def _baseline_path(self, device_id: str) -> Path:
        return self.baseline_dir / f"{device_id.replace(':', '_')}_settings_baseline.json"

    def status(self, device_id: str) -> dict:
        if device_id not in self._info:
            return {}
        try:
            cur = self._read_settings(self._transport_for(device_id))
        except Exception as e:
            self._drop(device_id)
            return {"mouse": None, "error": f"mouse not answering ({e}); move it to wake it"}
        p = self._baseline_path(device_id)
        if not p.exists():   # the first values ever read are what Synapse had configured
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps({k: cur[k] for k in self.SETTING_KEYS}), encoding="utf-8")
        return {"mouse": cur, "poll_choices": sorted(rz.POLL_CODES), "has_baseline": True}

    def configure(self, device_id: str, settings: dict) -> ApplyResult:
        if device_id not in self._info:
            return ApplyResult(False, message="device not present")
        if settings.get("restore_baseline"):
            p = self._baseline_path(device_id)
            if not p.exists():
                return ApplyResult(False, message="no saved original settings")
            settings = json.loads(p.read_text(encoding="utf-8"))
        bad = set(settings) - set(self.SETTING_KEYS)
        if bad:
            return ApplyResult(False, message=f"unknown setting(s): {', '.join(sorted(bad))}")
        try:
            t = self._transport_for(device_id)
            if "stages" in settings or "active_stage" in settings:
                _, cur = rz.decode_stages(t.transact(rz.get_dpi_stages())["args"])
                stages = [(int(x), int(y)) for x, y in settings.get("stages", cur)]
                active = int(settings.get("active_stage", 1))
                t.transact(rz.set_dpi_stages(stages, active))
                got_active, got = rz.decode_stages(t.transact(rz.get_dpi_stages())["args"])
                want = [(rz._dpi(x), rz._dpi(y)) for x, y in stages]
                if got != want or got_active != active:
                    return ApplyResult(False, message=f"DPI stages read back as {got} (active {got_active})")
                settings = {"dpi": list(want[active - 1]), **settings}
            if "dpi" in settings:
                x, y = (int(v) for v in settings["dpi"])
                t.transact(rz.set_dpi(x, y))
                got = rz.decode_dpi(t.transact(rz.get_dpi(rz.NOSTORE))["args"])
                if got != (rz._dpi(x), rz._dpi(y)):
                    return ApplyResult(False, message=f"DPI read back as {got}")
            if "poll_hz" in settings:
                hz = int(settings["poll_hz"])
                t.transact(rz.set_poll_rate(hz))
                got = rz.POLL_RATES.get(t.transact(rz.get_poll_rate())["args"][0])
                if got != hz:
                    return ApplyResult(False, message=f"polling rate read back as {got}")
            if "idle_s" in settings:
                s = max(60, min(900, int(settings["idle_s"])))
                t.transact(rz.set_idle_time(s))
                a = t.transact(rz.get_idle_time())["args"]
                if ((a[0] << 8) | a[1]) != s:
                    return ApplyResult(False, message="sleep timer did not read back")
        except (ValueError, TypeError) as e:
            return ApplyResult(False, message=str(e))
        except Exception as e:
            self._drop(device_id)
            return ApplyResult(False, message=f"direct HID: {e}")
        return ApplyResult(True, Confirmation.HARDWARE_READBACK, "saved on the mouse and verified by read-back")

    def shutdown(self) -> None:
        for d in list(self._devs):
            self._drop(d)
