"""Read-only Windows system facts: service status (SCM, query rights only) and a
CIM hardware summary. Nothing here changes system state."""
from __future__ import annotations

import ctypes
import json
import subprocess
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"

_STATES = {1: "stopped", 2: "start-pending", 3: "stop-pending", 4: "running",
           5: "continue-pending", 6: "pause-pending", 7: "paused"}


def service_state(name: str) -> str:
    """'running' | 'stopped' | ... | 'not-installed' | 'unknown'."""
    if not IS_WINDOWS:
        return "unknown"

    class SERVICE_STATUS(ctypes.Structure):
        _fields_ = [(n, wintypes.DWORD) for n in ("dwServiceType", "dwCurrentState", "dwControlsAccepted",
                    "dwWin32ExitCode", "dwServiceSpecificExitCode", "dwCheckPoint", "dwWaitHint")]

    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.OpenSCManagerW.restype = wintypes.HANDLE
    adv.OpenSCManagerW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD]
    adv.OpenServiceW.restype = wintypes.HANDLE
    adv.OpenServiceW.argtypes = [wintypes.HANDLE, wintypes.LPCWSTR, wintypes.DWORD]
    adv.QueryServiceStatus.argtypes = [wintypes.HANDLE, ctypes.POINTER(SERVICE_STATUS)]
    adv.CloseServiceHandle.argtypes = [wintypes.HANDLE]
    SC_MANAGER_CONNECT, SERVICE_QUERY_STATUS, ERROR_SERVICE_DOES_NOT_EXIST = 0x1, 0x4, 1060

    scm = adv.OpenSCManagerW(None, None, SC_MANAGER_CONNECT)
    if not scm:
        return "unknown"
    try:
        svc = adv.OpenServiceW(scm, name, SERVICE_QUERY_STATUS)
        if not svc:
            return "not-installed" if ctypes.get_last_error() == ERROR_SERVICE_DOES_NOT_EXIST else "unknown"
        try:
            st = SERVICE_STATUS()
            if not adv.QueryServiceStatus(svc, ctypes.byref(st)):
                return "unknown"
            return _STATES.get(st.dwCurrentState, "unknown")
        finally:
            adv.CloseServiceHandle(svc)
    finally:
        adv.CloseServiceHandle(scm)


_CIM_SCRIPT = r"""
$ErrorActionPreference='SilentlyContinue'
[pscustomobject]@{
 board = Get-CimInstance Win32_BaseBoard | Select-Object Manufacturer,Product
 bios  = Get-CimInstance Win32_BIOS | Select-Object SMBIOSBIOSVersion
 gpus  = @(Get-CimInstance Win32_VideoController | Select-Object Name,PNPDeviceID,DriverVersion)
 dimms = @(Get-CimInstance Win32_PhysicalMemory | Select-Object Manufacturer,PartNumber,Capacity,Speed,DeviceLocator)
} | ConvertTo-Json -Depth 4 -Compress
"""

_cim_cache: dict | None = None


def hardware_summary(refresh: bool = False, timeout: float = 20.0) -> dict:
    """Board/GPU/DIMM facts via CIM. Cached; returns {} if unavailable."""
    global _cim_cache
    if _cim_cache is not None and not refresh:
        return _cim_cache
    if not IS_WINDOWS:
        return {}
    try:
        out = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", _CIM_SCRIPT],
                             capture_output=True, text=True, timeout=timeout,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(out.stdout or "{}")
    except (OSError, subprocess.SubprocessError, ValueError):
        data = {}
    for k in ("gpus", "dimms"):   # ConvertTo-Json unwraps single-element arrays
        if isinstance(data.get(k), dict):
            data[k] = [data[k]]
    _cim_cache = data
    return data


def running_processes() -> set[str]:
    """Lower-case executable names of running processes (Toolhelp snapshot, read-only)."""
    if not IS_WINDOWS:
        return set()

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD), ("th32ProcessID", wintypes.DWORD),
                    ("th32DefaultHeapID", ctypes.c_void_p), ("th32ModuleID", wintypes.DWORD),
                    ("cntThreads", wintypes.DWORD), ("th32ParentProcessID", wintypes.DWORD),
                    ("pcPriClassBase", ctypes.c_long), ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)
    if snap in (None, wintypes.HANDLE(-1).value):
        return set()
    names = set()
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            names.add(e.szExeFile.lower())
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return names
