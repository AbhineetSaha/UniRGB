"""Read-only SMBus access through PawnIO's SmbusPIIX4 module (AMD chipsets).

Sources:
- PawnIO user API: C:\\Program Files\\PawnIO\\PawnIOLib.h (pawnio_open/load/execute/close).
- SmbusPIIX4 module, LGPL-2.1-or-later, loaded from the user's install, never bundled:
  https://github.com/namazso/PawnIO.Modules/blob/main/SmbusPIIX4.p
  ioctl_smbus_xfer in = [address, read_write, command, protocol], out[0] = byte read.
- Address facts for ENE DRAM controllers: OpenRGB's ENESMBusControllerDetect.cpp (facts only).

There is no write path: every transfer is a READ, and only ENE_DRAM_ADDRESSES can be reached.
A "read byte data" transaction still sends a command byte, which moves the target's register
pointer; that is why the address range is a hard allowlist away from SPD hubs and PMICs.
"""
from __future__ import annotations

import ctypes
from pathlib import Path

READ = 1                     # I2C_SMBUS_READ; this package has no WRITE
PROTO_BYTE = 1               # I2C_SMBUS_BYTE (receive byte)
PROTO_BYTE_DATA = 2          # I2C_SMBUS_BYTE_DATA
# ENE DRAM RGB controllers on DDR5. DDR5 SPD hubs sit at 0x50-0x57 and PMICs at 0x48-0x4F,
# so neither can ever be addressed from here.
ENE_DRAM_ADDRESSES = range(0x70, 0x78)
# Shared with LibreHardwareMonitor, HWiNFO, OpenRGB and firmware: hold it for every transfer.
SMBUS_MUTEX = "Global\\Access_SMBUS.HTP.Method"
PAWNIO_DLL = Path(r"C:\Program Files\PawnIO\PawnIOLib.dll")
PIIX4_MODULE = Path(r"C:\Program Files\OpenRGB\SmbusPIIX4.bin")
AMD_VENDOR = 0x1022
_U64 = (1 << 64) - 1


class PawnIO:
    """Thin ctypes binding over PawnIOLib.dll. Needs administrator rights."""

    def __init__(self, dll: Path = PAWNIO_DLL):
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

    @staticmethod
    def _check(hr: int, what: str) -> None:
        if hr < 0:
            raise OSError(hr & 0xFFFFFFFF, f"{what} failed (HRESULT 0x{hr & 0xFFFFFFFF:08X})")

    def load(self, blob: bytes) -> None:
        self._check(self._lib.pawnio_load(self._h, blob, len(blob)), "pawnio_load")

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


class SmbusMutex:
    """The system-wide SMBus lock, as a context manager."""

    WAIT_ABANDONED = 0x80   # previous owner died; we still own it now

    def __init__(self, timeout_ms: int = 1000):
        from ctypes import wintypes
        self._k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32.CreateMutexW.restype = wintypes.HANDLE
        self._k32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        self._k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._k32.ReleaseMutex.argtypes = [wintypes.HANDLE]
        self._h = self._k32.CreateMutexW(None, False, SMBUS_MUTEX)
        if not self._h:
            raise ctypes.WinError(ctypes.get_last_error())
        self._timeout = timeout_ms

    def __enter__(self):
        r = self._k32.WaitForSingleObject(self._h, self._timeout)
        if r not in (0, self.WAIT_ABANDONED):
            raise TimeoutError("another program holds the SMBus lock")
        return self

    def __exit__(self, *exc):
        self._k32.ReleaseMutex(self._h)


class ReadOnlySmbus:
    """Read transactions on allowlisted addresses only. There is deliberately no write method."""

    def __init__(self, executor, lock):
        self._ex, self._lock = executor, lock

    def _read(self, addr: int, command: int, proto: int) -> int | None:
        if addr not in ENE_DRAM_ADDRESSES:
            raise ValueError(f"address 0x{addr:02X} is outside the ENE DRAM allowlist")
        with self._lock:
            try:
                return self._ex.execute("ioctl_smbus_xfer", [addr, READ, command, proto], 1)[0] & 0xFF
            except OSError:
                return None   # no device acknowledged the address

    def read_byte(self, addr: int) -> int | None:
        return self._read(addr, 0, PROTO_BYTE)

    def read_byte_data(self, addr: int, reg: int) -> int | None:
        return self._read(addr, reg & 0xFF, PROTO_BYTE_DATA)

    def identity(self) -> dict:
        _name, base, ids = self._ex.execute("ioctl_identity", [], 3)
        return {"smbus_base": base, "pci_vendor": ids & 0xFFFF, "pci_device": (ids >> 16) & 0xFFFF,
                "subsys_vendor": (ids >> 32) & 0xFFFF, "subsys_device": (ids >> 48) & 0xFFFF}

    def current_port(self) -> int:
        return self._ex.execute("ioctl_piix4_port_sel", [-1], 1)[0]   # -1: read only, no change
