"""The privileged hardware helper: `UniRGB.exe --hardware-helper`, started by the scheduled task.

It answers a fixed list of requests over the local pipe and nothing else:
  ping      -> {"ok": true, "version": ...}
  cpu_temp  -> {"ok": true, "celsius": ..., "label": ...}   (AMD Zen, read-only)
It loads PawnIO modules only from its own folder, takes no arguments that change what it does,
and exits after IDLE_S without requests, so it never outlives UniRGB.
"""
from __future__ import annotations

import ctypes
import logging
import os
import sys
import threading
import time
from pathlib import Path

log = logging.getLogger("unirgb.helper")
IDLE_S = 60.0
OPS = ("ping", "cpu_temp")
TCTL_SMN = 0x59800   # SMU::THM::THM_TCON_CUR_TMP on Zen (Linux k10temp driver, facts only)


def decode_tctl(raw: int) -> float:
    """CUR_TEMP is bits 31:21 in 0.125 degree steps; bit 19 selects the -49 degree range."""
    t = ((raw >> 21) & 0x7FF) * 0.125
    return t - 49.0 if raw & (1 << 19) else t


class Handler:
    def __init__(self, read_smn, version: str):
        self._read_smn, self._version = read_smn, version
        self.last = time.monotonic()

    def __call__(self, req: dict) -> dict:
        self.last = time.monotonic()
        op = req.get("op")
        if op not in OPS:
            return {"ok": False, "error": "unknown request"}
        if op == "ping":
            return {"ok": True, "version": self._version}
        try:
            return {"ok": True, "celsius": round(decode_tctl(self._read_smn(TCTL_SMN)), 1), "label": "CPU (Tctl)"}
        except (OSError, TimeoutError) as e:
            return {"ok": False, "error": str(e)}


def main(argv: list[str]) -> int:
    from . import system_setup
    from .app import VERSION
    from .hostos import pawnio, pipe
    module = Path(sys.executable).parent / "modules" / "AMDFamily17.bin"   # own folder only
    # Checked before logging: the log lives in the admin-only helper folder that setup creates.
    if sys.platform != "win32" or not ctypes.windll.shell32.IsUserAnAdmin() or not module.is_file():
        return 2
    logging.basicConfig(filename=str(system_setup.helper_dir() / "helper.log"), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        dev = pawnio.PawnIO(module.read_bytes())
    except OSError as e:
        log.error("cannot load %s: %s", module, e)
        return 1
    lock = pawnio.NamedMutex(pawnio.PCI_MUTEX)

    def read_smn(offset: int) -> int:
        with lock:
            return dev.execute("ioctl_read_smn", [offset], 1)[0]

    handler = Handler(read_smn, VERSION)

    def watchdog():
        while time.monotonic() - handler.last < IDLE_S:
            time.sleep(5)
        log.info("idle for %ds, exiting", IDLE_S)
        os._exit(0)   # the pipe thread may be blocked in ConnectNamedPipe

    threading.Thread(target=watchdog, daemon=True).start()
    try:
        pipe.serve(system_setup.current_user_sid(), handler)
    except OSError as e:   # e.g. another program already owns the pipe name
        log.error("pipe failed: %s", e)
        return 1
    finally:
        dev.close()
    return 0
