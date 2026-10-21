"""The privileged hardware helper: `UniRGB.exe --hardware-helper`, started by the scheduled task.

It answers a fixed list of requests over the local pipe and nothing else:
  ping         -> {"ok": true, "version": ...}
  cpu_temp     -> {"ok": true, "celsius": ..., "label": ...}   (AMD Zen, read-only)
  ram_list     -> {"ok": true, "sticks": [{"address", "name", "leds"}], "problem": ...}
  ram_set      {"address": 0x71, "color": "#rrggbb"} -> {"ok": ...}   (direct colors, never saved to the stick)
  ram_release  {"address": 0x71} -> {"ok": ...}   (the stick goes back to its stored effect)
  stop         -> {"ok": true}, then the helper exits (UniRGB quitting)
RAM requests go through unirgb_smbus, whose fences limit them to verified ENE controllers and their color,
direct-mode and apply registers. The helper loads PawnIO modules only from its own folder, takes no arguments
that change what it does, and exits after IDLE_S without requests, so it never outlives UniRGB.
"""
from __future__ import annotations

import ctypes
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("unirgb.helper")
IDLE_S = 60.0
OPS = ("ping", "cpu_temp", "ram_list", "ram_set", "ram_release", "stop")
TCTL_SMN = 0x59800   # SMU::THM::THM_TCON_CUR_TMP on Zen (Linux k10temp driver, facts only)
_HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


def decode_tctl(raw: int) -> float:
    """CUR_TEMP is bits 31:21 in 0.125 degree steps; bit 19 selects the -49 degree range."""
    t = ((raw >> 21) & 0x7FF) * 0.125
    return t - 49.0 if raw & (1 << 19) else t


class Handler:
    def __init__(self, read_smn, version: str, ram_factory=None):
        self._read_smn, self._version = read_smn, version
        self._ram_factory, self._ram = ram_factory, None
        self.last = time.monotonic()
        self.stopping = False

    def _ram_service(self):
        if self._ram is None:
            if self._ram_factory is None:
                raise OSError("RAM lighting is not available in this helper")
            self._ram = self._ram_factory()
            self._ram.scan()
        return self._ram

    def __call__(self, req: dict) -> dict:
        self.last = time.monotonic()
        op = req.get("op")
        if op not in OPS:
            return {"ok": False, "error": "unknown request"}
        if op == "ping":
            return {"ok": True, "version": self._version}
        if op == "stop":
            self.stopping = True   # pipe.serve returns after sending this reply
            return {"ok": True}
        try:
            if op == "cpu_temp":
                if self._read_smn is None:
                    return {"ok": False, "error": "CPU temperature is not available on this CPU"}
                return {"ok": True, "celsius": round(decode_tctl(self._read_smn(TCTL_SMN)), 1), "label": "CPU (Tctl)"}
            ram = self._ram_service()
            if op == "ram_list":
                return ram.listing()
            addr = req.get("address")
            if not isinstance(addr, int) or isinstance(addr, bool):
                return {"ok": False, "error": "address must be an integer"}
            if op == "ram_release":
                return {"ok": ram.release(addr)}
            color = req.get("color")
            if not isinstance(color, str) or not _HEX.match(color):
                return {"ok": False, "error": "color must be #rrggbb"}
            return {"ok": ram.set_color(addr, tuple(int(color[i:i + 2], 16) for i in (1, 3, 5)))}
        except ValueError as e:   # a fence refused the request
            return {"ok": False, "error": str(e)}
        except (OSError, TimeoutError) as e:
            return {"ok": False, "error": str(e)}


def main(argv: list[str]) -> int:
    from . import system_setup
    from .app import VERSION
    from .hostos import pawnio, pipe
    modules = Path(sys.executable).parent / "modules"   # own folder only
    # Checked before logging: the log lives in the admin-only helper folder that setup creates.
    if sys.platform != "win32" or not ctypes.windll.shell32.IsUserAnAdmin() or not modules.is_dir():
        return 2
    logging.basicConfig(filename=str(system_setup.helper_dir() / "helper.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    dev, read_smn = None, None
    try:
        dev = pawnio.PawnIO((modules / "AMDFamily17.bin").read_bytes())
        lock = pawnio.NamedMutex(pawnio.PCI_MUTEX)

        def read_smn(offset: int) -> int:
            with lock:
                return dev.execute("ioctl_read_smn", [offset], 1)[0]
    except OSError as e:   # not an AMD Zen CPU, or the module is missing: RAM can still work
        log.warning("CPU temperature unavailable: %s", e)

    ram_pawn = []

    def ram_factory():
        from unirgb_smbus.bus import PawnIO as SmbusPawnIO, SmbusMutex
        from unirgb_smbus.service import MODULE_NAME, RamService
        p = SmbusPawnIO()
        p.load((modules / MODULE_NAME).read_bytes())
        ram_pawn.append(p)
        return RamService(p, SmbusMutex())

    handler = Handler(read_smn, VERSION, ram_factory)

    def watchdog():
        while time.monotonic() - handler.last < IDLE_S:
            time.sleep(5)
        log.info("idle for %ds, exiting", IDLE_S)
        os._exit(0)   # the pipe thread may be blocked in ConnectNamedPipe

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        pipe.serve(system_setup.current_user_sid(), handler, should_stop=lambda: handler.stopping)
    except OSError as e:   # e.g. another program already owns the pipe name
        log.error("pipe failed: %s", e)
        return 1
    finally:
        for p in [dev, *ram_pawn]:
            if p is not None:
                p.close()
    return 0
