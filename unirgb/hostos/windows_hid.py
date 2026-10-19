"""Read-only HID enumeration for Windows via SetupAPI + hid.dll (ctypes, no deps).

Safety contract: devices are opened with desired access 0 (query-only). No input,
output or feature reports are ever read or written by this module. We only call
HidD_GetAttributes / HidD_Get*String / HidP_GetCaps, which the HID class driver
answers from cached descriptors.
"""
from __future__ import annotations

import ctypes
import re
import sys
from ctypes import wintypes
from dataclasses import dataclass, field, asdict

IS_WINDOWS = sys.platform == "win32"


@dataclass
class HidInterface:
    path: str
    vid: int
    pid: int
    version: int
    usage_page: int | None = None
    usage: int | None = None
    input_len: int | None = None
    output_len: int | None = None
    feature_len: int | None = None
    manufacturer: str | None = None
    product: str | None = None
    serial: str | None = None
    interface_number: int | None = None
    collection: str | None = None
    errors: list[str] = field(default_factory=list)

    @property
    def vidpid(self) -> str:
        return f"{self.vid:04X}:{self.pid:04X}"

    def to_dict(self) -> dict:
        d = asdict(self)
        d["vidpid"] = self.vidpid
        return d


if IS_WINDOWS:
    class GUID(ctypes.Structure):
        _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                    ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

    class SP_DEVICE_INTERFACE_DATA(ctypes.Structure):
        _fields_ = [("cbSize", wintypes.DWORD), ("InterfaceClassGuid", GUID),
                    ("Flags", wintypes.DWORD), ("Reserved", ctypes.c_void_p)]

    class HIDD_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Size", wintypes.ULONG), ("VendorID", wintypes.USHORT),
                    ("ProductID", wintypes.USHORT), ("VersionNumber", wintypes.USHORT)]

    class HIDP_CAPS(ctypes.Structure):
        _fields_ = [("Usage", wintypes.USHORT), ("UsagePage", wintypes.USHORT),
                    ("InputReportByteLength", wintypes.USHORT),
                    ("OutputReportByteLength", wintypes.USHORT),
                    ("FeatureReportByteLength", wintypes.USHORT),
                    ("Reserved", wintypes.USHORT * 17),
                    ("NumberLinkCollectionNodes", wintypes.USHORT),
                    ("NumberInputButtonCaps", wintypes.USHORT),
                    ("NumberInputValueCaps", wintypes.USHORT),
                    ("NumberInputDataIndices", wintypes.USHORT),
                    ("NumberOutputButtonCaps", wintypes.USHORT),
                    ("NumberOutputValueCaps", wintypes.USHORT),
                    ("NumberOutputDataIndices", wintypes.USHORT),
                    ("NumberFeatureButtonCaps", wintypes.USHORT),
                    ("NumberFeatureValueCaps", wintypes.USHORT),
                    ("NumberFeatureDataIndices", wintypes.USHORT)]

    _setupapi = ctypes.WinDLL("setupapi", use_last_error=True)
    _hid = ctypes.WinDLL("hid", use_last_error=True)
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _setupapi.SetupDiGetClassDevsW.restype = wintypes.HANDLE
    _setupapi.SetupDiGetClassDevsW.argtypes = [ctypes.POINTER(GUID), wintypes.LPCWSTR, wintypes.HWND, wintypes.DWORD]
    _setupapi.SetupDiEnumDeviceInterfaces.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.POINTER(GUID), wintypes.DWORD, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA)]
    _setupapi.SetupDiGetDeviceInterfaceDetailW.argtypes = [wintypes.HANDLE, ctypes.POINTER(SP_DEVICE_INTERFACE_DATA), ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    _setupapi.SetupDiDestroyDeviceInfoList.argtypes = [wintypes.HANDLE]
    _k32.CreateFileW.restype = wintypes.HANDLE
    _k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    _k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _hid.HidD_GetHidGuid.argtypes = [ctypes.POINTER(GUID)]
    _hid.HidD_GetAttributes.argtypes = [wintypes.HANDLE, ctypes.POINTER(HIDD_ATTRIBUTES)]
    for _fn in ("HidD_GetProductString", "HidD_GetManufacturerString", "HidD_GetSerialNumberString"):
        getattr(_hid, _fn).argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.ULONG]
    _hid.HidD_GetPreparsedData.argtypes = [wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    _hid.HidD_FreePreparsedData.argtypes = [ctypes.c_void_p]
    _hid.HidP_GetCaps.argtypes = [ctypes.c_void_p, ctypes.POINTER(HIDP_CAPS)]

    DIGCF_PRESENT, DIGCF_DEVICEINTERFACE = 0x02, 0x10
    FILE_SHARE_RW = 0x01 | 0x02
    OPEN_EXISTING = 3
    INVALID_HANDLE = wintypes.HANDLE(-1).value
    HIDP_STATUS_SUCCESS = 0x00110000


def _hid_string(handle, fn) -> str | None:
    buf = ctypes.create_unicode_buffer(256)
    if fn(handle, buf, ctypes.sizeof(buf)):
        s = buf.value.strip()
        return s or None
    return None


_MI_RE = re.compile(r"&mi_([0-9a-f]{2})", re.I)
_COL_RE = re.compile(r"&col([0-9a-f]{2})", re.I)


def enumerate_hid() -> list[HidInterface]:
    """Return every present HID top-level collection. Empty list off-Windows."""
    if not IS_WINDOWS:
        return []
    guid = GUID()
    _hid.HidD_GetHidGuid(ctypes.byref(guid))
    hdev = _setupapi.SetupDiGetClassDevsW(ctypes.byref(guid), None, None, DIGCF_PRESENT | DIGCF_DEVICEINTERFACE)
    if hdev == INVALID_HANDLE:
        raise OSError(ctypes.get_last_error(), "SetupDiGetClassDevsW failed")
    out: list[HidInterface] = []
    try:
        idx = 0
        while True:
            ifd = SP_DEVICE_INTERFACE_DATA()
            ifd.cbSize = ctypes.sizeof(SP_DEVICE_INTERFACE_DATA)
            if not _setupapi.SetupDiEnumDeviceInterfaces(hdev, None, ctypes.byref(guid), idx, ctypes.byref(ifd)):
                break
            idx += 1
            needed = wintypes.DWORD()
            _setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifd), None, 0, ctypes.byref(needed), None)
            buf = ctypes.create_string_buffer(needed.value)
            # cbSize of SP_DEVICE_INTERFACE_DETAIL_DATA_W is 8 on x64, 6 on x86
            ctypes.c_uint32.from_buffer(buf).value = 8 if ctypes.sizeof(ctypes.c_void_p) == 8 else 6
            if not _setupapi.SetupDiGetDeviceInterfaceDetailW(hdev, ctypes.byref(ifd), buf, needed, None, None):
                continue
            path = ctypes.wstring_at(ctypes.addressof(buf) + 4)
            out.append(_query(path))
    finally:
        _setupapi.SetupDiDestroyDeviceInfoList(hdev)
    return out


def _query(path: str) -> HidInterface:
    mi = _MI_RE.search(path)
    col = _COL_RE.search(path)
    m = re.search(r"vid_([0-9a-f]{4}).*?pid_([0-9a-f]{4})", path, re.I)
    info = HidInterface(path=path, vid=int(m.group(1), 16) if m else 0, pid=int(m.group(2), 16) if m else 0,
                        version=0, interface_number=int(mi.group(1), 16) if mi else None,
                        collection=col.group(1) if col else None)
    h = _k32.CreateFileW(path, 0, FILE_SHARE_RW, None, OPEN_EXISTING, 0, None)  # access 0 = query only
    if h == INVALID_HANDLE or h is None:
        info.errors.append(f"open(query-only) failed: winerror {ctypes.get_last_error()}")
        return info
    try:
        attrs = HIDD_ATTRIBUTES()
        attrs.Size = ctypes.sizeof(HIDD_ATTRIBUTES)
        if _hid.HidD_GetAttributes(h, ctypes.byref(attrs)):
            info.vid, info.pid, info.version = attrs.VendorID, attrs.ProductID, attrs.VersionNumber
        info.manufacturer = _hid_string(h, _hid.HidD_GetManufacturerString)
        info.product = _hid_string(h, _hid.HidD_GetProductString)
        info.serial = _hid_string(h, _hid.HidD_GetSerialNumberString)
        pp = ctypes.c_void_p()
        if _hid.HidD_GetPreparsedData(h, ctypes.byref(pp)):
            try:
                caps = HIDP_CAPS()
                if _hid.HidP_GetCaps(pp, ctypes.byref(caps)) == HIDP_STATUS_SUCCESS:
                    info.usage_page, info.usage = caps.UsagePage, caps.Usage
                    info.input_len = caps.InputReportByteLength
                    info.output_len = caps.OutputReportByteLength
                    info.feature_len = caps.FeatureReportByteLength
            finally:
                _hid.HidD_FreePreparsedData(pp)
        else:
            info.errors.append("preparsed data unavailable")
    finally:
        _k32.CloseHandle(h)
    return info


if __name__ == "__main__":
    for i in sorted(enumerate_hid(), key=lambda x: (x.vid, x.pid, x.path)):
        up = f"{i.usage_page:04X}:{i.usage:04X}" if i.usage_page is not None else "????"
        print(f"{i.vidpid} mi={i.interface_number} col={i.collection} up={up} in/out/feat={i.input_len}/{i.output_len}/{i.feature_len} "
              f"mfr={i.manufacturer!r} prod={i.product!r} {'ERR ' + ';'.join(i.errors) if i.errors else ''}")
