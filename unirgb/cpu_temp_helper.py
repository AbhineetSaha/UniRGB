"""Elevated CPU-temperature helper: python -m unirgb.cpu_temp_helper --parent <pid>

Runs AMD's signed Ryzen Master CLI read-only call in a loop and atomically writes
{"celsius": .., "at": ..} to %LOCALAPPDATA%\\UniRGB\\cpu_temp.json. It exits on its own
when the UniRGB process (--parent) ends, so no elevated process is left behind.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import sys
import time
from ctypes import wintypes

from . import sensors
from .sensors import helper_file, read_amd_cli


def pid_alive(pid: int) -> bool:
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    h = k32.OpenProcess(0x1000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259   # STILL_ACTIVE
    finally:
        k32.CloseHandle(h)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--parent", type=int, required=True)
    ap.add_argument("--interval", type=float, default=2.0)
    args = ap.parse_args(argv)
    out = helper_file()
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".error").unlink(missing_ok=True)
    failures = 0
    while pid_alive(args.parent):
        t = read_amd_cli()
        if t is None:
            failures += 1
            if failures >= 5:   # not elevated or SDK broken: stop instead of spinning
                out.with_suffix(".error").write_text("AMD Ryzen Master CLI returned no temperature 5 times. Last output:\n"
                                                     + sensors.last_cli_output[:2000], encoding="utf-8")
                return 1
        else:
            failures = 0
            tmp = out.with_suffix(".tmp")
            tmp.write_text(json.dumps({"celsius": t, "at": time.time(), "pid": os.getpid()}), encoding="utf-8")
            os.replace(tmp, out)
        time.sleep(args.interval)
    return 0


if __name__ == "__main__":
    sys.exit(main())
