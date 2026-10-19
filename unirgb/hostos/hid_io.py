"""Direct HID feature-report I/O on Windows (hid.dll via ctypes).

Unlike windows_hid.py (query-only), this module sends feature reports and must
only be used by adapters that implement a known protocol. Buffers are padded to
the collection's FeatureReportByteLength, as Windows requires (byte 0 = report id).
"""
from __future__ import annotations

import ctypes
import sys
import threading
from ctypes import wintypes

from .windows_hid import enumerate_hid, HidInterface

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    _hid = ctypes.WinDLL("hid", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                 wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _hid.HidD_SetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    _hid.HidD_GetFeature.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    GENERIC_READ, GENERIC_WRITE = 0x80000000, 0x40000000
    FILE_SHARE_RW, OPEN_EXISTING = 0x3, 3
    INVALID_HANDLE = wintypes.HANDLE(-1).value


class HidIOError(OSError):
    pass


class HidDevice:
    """One open HID top-level collection. Thread-safe per instance."""

    def __init__(self, info: HidInterface):
        if not IS_WINDOWS:
            raise HidIOError("direct HID is only implemented on Windows")
        self.info = info
        self.feature_len = info.feature_len or 0
        self._lock = threading.Lock()
        # Mice/keyboards are opened exclusively for input by Windows, so read/write
        # access is refused; a query-only (0) handle still carries feature reports.
        self.access = "rw"
        h = _k32.CreateFileW(info.path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
        if h in (INVALID_HANDLE, None):
            self.access = "query"
            h = _k32.CreateFileW(info.path, 0, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)
        if h in (INVALID_HANDLE, None):
            raise HidIOError(ctypes.get_last_error(), f"cannot open {info.vidpid}")
        self._h = h

    def _buf(self, data: bytes) -> ctypes.Array:
        if len(data) > self.feature_len:
            raise HidIOError(f"report of {len(data)} bytes exceeds feature length {self.feature_len}")
        return ctypes.create_string_buffer(bytes(data) + b"\x00" * (self.feature_len - len(data)), self.feature_len)

    def set_feature(self, data: bytes) -> None:
        """data[0] is the report id (0 when the device uses none)."""
        with self._lock:
            buf = self._buf(data)
            if not _hid.HidD_SetFeature(self._h, buf, self.feature_len):
                raise HidIOError(ctypes.get_last_error(), "HidD_SetFeature failed")

    def get_feature(self, report_id: int) -> bytes:
        with self._lock:
            buf = self._buf(bytes([report_id]))
            if not _hid.HidD_GetFeature(self._h, buf, self.feature_len):
                raise HidIOError(ctypes.get_last_error(), "HidD_GetFeature failed")
            return buf.raw

    def close(self) -> None:
        with self._lock:
            if self._h:
                _k32.CloseHandle(self._h)
                self._h = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class HidReportDevice:
    """Output/input report I/O (WriteFile/ReadFile) with a read timeout, for request/response protocols."""

    def __init__(self, info: HidInterface):
        if not IS_WINDOWS:
            raise HidIOError("direct HID is only implemented on Windows")
        self.info = info
        self.out_len, self.in_len = info.output_len or 0, info.input_len or 0
        self._lock = threading.Lock()
        k32 = _k32
        k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
        k32.CreateEventW.restype = wintypes.HANDLE
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        k32.GetOverlappedResult.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD), wintypes.BOOL]
        k32.CancelIo.argtypes = [wintypes.HANDLE]
        FILE_FLAG_OVERLAPPED = 0x40000000
        h = k32.CreateFileW(info.path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_RW, None, OPEN_EXISTING, FILE_FLAG_OVERLAPPED, None)
        if h in (INVALID_HANDLE, None):
            raise HidIOError(ctypes.get_last_error(), f"cannot open {info.vidpid} for read/write")
        self._h = h

    class _OVERLAPPED(ctypes.Structure):
        _fields_ = [("Internal", ctypes.c_void_p), ("InternalHigh", ctypes.c_void_p), ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD), ("hEvent", wintypes.HANDLE)]

    def _io(self, fn, buf, length: int, timeout_ms: int) -> int:
        ov = self._OVERLAPPED()
        ov.hEvent = _k32.CreateEventW(None, True, False, None)
        try:
            n = wintypes.DWORD()
            if not fn(self._h, buf, length, ctypes.byref(n), ctypes.byref(ov)):
                if ctypes.get_last_error() != 997:   # ERROR_IO_PENDING
                    raise HidIOError(ctypes.get_last_error(), "HID I/O failed")
                if _k32.WaitForSingleObject(ov.hEvent, timeout_ms) != 0:
                    _k32.CancelIo(self._h)
                    raise TimeoutError("HID device did not answer in time")
                if not _k32.GetOverlappedResult(self._h, ctypes.byref(ov), ctypes.byref(n), False):
                    raise HidIOError(ctypes.get_last_error(), "HID I/O failed")
            return n.value
        finally:
            _k32.CloseHandle(ov.hEvent)

    def write(self, data: bytes, timeout_ms: int = 1000) -> None:
        with self._lock:
            buf = ctypes.create_string_buffer(bytes(data) + b"\x00" * (self.out_len - len(data)), self.out_len)
            self._io(_k32.WriteFile, buf, self.out_len, timeout_ms)

    def read(self, timeout_ms: int = 1000) -> bytes:
        with self._lock:
            buf = ctypes.create_string_buffer(self.in_len)
            n = self._io(_k32.ReadFile, buf, self.in_len, timeout_ms)
            return buf.raw[:n]

    def close(self) -> None:
        with self._lock:
            if self._h:
                _k32.CloseHandle(self._h)
                self._h = None


def find(vid: int, pid: int | None = None, usage_page: int | None = None, usage: int | None = None,
         interface: int | None = None, min_feature: int = 1, interfaces: list | None = None) -> list[HidInterface]:
    out = []
    for i in (interfaces if interfaces is not None else enumerate_hid()):
        if i.vid != vid or (pid is not None and i.pid != pid):
            continue
        if usage_page is not None and i.usage_page != usage_page:
            continue
        if usage is not None and i.usage != usage:
            continue
        if interface is not None and i.interface_number != interface:
            continue
        if (i.feature_len or 0) < min_feature:
            continue
        out.append(i)
    return out
