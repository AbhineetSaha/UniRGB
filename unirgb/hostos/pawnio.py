"""Minimal binding to the PawnIO driver (user API in C:\\Program Files\\PawnIO\\PawnIOLib.h) and the
system-wide mutexes that hardware tools share. Used only by the elevated hardware helper.

PawnIO itself is GPL-2.0; its modules (loaded from UniRGB's helper folder) are LGPL-2.1-or-later:
https://github.com/namazso/PawnIO, https://github.com/namazso/PawnIO.Modules
"""
from __future__ import annotations

import ctypes
from pathlib import Path

PAWNIO_DLL = Path(r"C:\Program Files\PawnIO\PawnIOLib.dll")
PCI_MUTEX = "Global\\Access_PCI"   # held by LibreHardwareMonitor, HWiNFO, OpenRGB, ... around PCI config access
_U64 = (1 << 64) - 1


class PawnIO:
    """One executor with one loaded module. Needs administrator rights."""

    def __init__(self, module: bytes, dll: Path = PAWNIO_DLL):
        self._lib = ctypes.WinDLL(str(dll))
        for fn in ("pawnio_open", "pawnio_load", "pawnio_execute", "pawnio_close"):
            getattr(self._lib, fn).restype = ctypes.c_long
        self._lib.pawnio_open.argtypes = [ctypes.POINTER(ctypes.c_void_p)]
        self._lib.pawnio_load.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_size_t]
        self._lib.pawnio_execute.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t,
            ctypes.POINTER(ctypes.c_uint64), ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
        self._lib.pawnio_close.argtypes = [ctypes.c_void_p]
        self._h = ctypes.c_void_p()
        self._check(self._lib.pawnio_open(ctypes.byref(self._h)), "pawnio_open")
        self._check(self._lib.pawnio_load(self._h, module, len(module)), "pawnio_load")

    @staticmethod
    def _check(hr: int, what: str) -> None:
        if hr < 0:
            raise OSError(hr & 0xFFFFFFFF, f"{what} failed (HRESULT 0x{hr & 0xFFFFFFFF:08X})")

    def execute(self, name: str, args: list[int], out_size: int) -> list[int]:
        inp = (ctypes.c_uint64 * max(len(args), 1))(*[a & _U64 for a in args])
        out = (ctypes.c_uint64 * max(out_size, 1))()
        n = ctypes.c_size_t()
        self._check(self._lib.pawnio_execute(self._h, name.encode(), inp, len(args), out, out_size,
                                             ctypes.byref(n)), name)
        return list(out[:n.value])

    def close(self) -> None:
        if self._h:
            self._lib.pawnio_close(self._h)
            self._h = ctypes.c_void_p()


class NamedMutex:
    """A system-wide named mutex as a context manager."""

    WAIT_ABANDONED = 0x80   # the previous owner died; we own it now

    def __init__(self, name: str, timeout_ms: int = 1000):
        from ctypes import wintypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateMutexW.restype = wintypes.HANDLE
        self._k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self._k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self._h = self._k32.CreateMutexW(None, False, name)
        if not self._h:
            raise ctypes.WinError(ctypes.get_last_error())
        self._timeout, self.name = timeout_ms, name

    def __enter__(self):
        if self._k32.WaitForSingleObject(self._h, self._timeout) not in (0, self.WAIT_ABANDONED):
            raise TimeoutError(f"another program holds {self.name}")
        return self

    def __exit__(self, *exc):
        self._k32.ReleaseMutex(self._h)
