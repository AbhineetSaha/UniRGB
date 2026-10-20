"""Local named pipe between the unprivileged app (client) and the elevated helper (server).

One newline-terminated JSON request and one JSON reply per connection. The pipe's DACL allows only
the signed-in user and SYSTEM, at medium integrity, and refuses remote clients. FIRST_PIPE_INSTANCE
makes the helper fail instead of sharing a name another program created first.
"""
from __future__ import annotations

import ctypes
import json
import time
from ctypes import wintypes

PIPE_NAME = r"\\.\pipe\UniRGB-hardware-helper"
MAX_MSG = 4096

PIPE_ACCESS_DUPLEX = 0x3
FILE_FLAG_FIRST_PIPE_INSTANCE = 0x80000
PIPE_REJECT_REMOTE_CLIENTS = 0x8
ERROR_PIPE_CONNECTED = 535
INVALID_HANDLE = ctypes.c_void_p(-1).value


def sddl_for(user_sid: str) -> str:
    # P: no inherited ACEs; user may read/write, SYSTEM full; S: medium-integrity clients may write.
    return f"D:P(A;;GRGW;;;{user_sid})(A;;GA;;;SY)S:(ML;;NW;;;ME)"


class _SA(ctypes.Structure):
    _fields_ = [("nLength", wintypes.DWORD), ("lpSecurityDescriptor", ctypes.c_void_p), ("bInheritHandle", wintypes.BOOL)]


def serve(user_sid: str, handle_request, should_stop=lambda: False) -> None:
    """Accept connections forever (until should_stop()); handle_request(dict) -> dict."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    adv.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p]
    k32.CreateNamedPipeW.restype = wintypes.HANDLE
    k32.CreateNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(_SA)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.ConnectNamedPipe.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    k32.DisconnectNamedPipe.argtypes = [wintypes.HANDLE]
    k32.FlushFileBuffers.argtypes = [wintypes.HANDLE]
    k32.ReadFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    k32.WriteFile.argtypes = [wintypes.HANDLE, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]

    sd = ctypes.c_void_p()
    if not adv.ConvertStringSecurityDescriptorToSecurityDescriptorW(sddl_for(user_sid), 1, ctypes.byref(sd), None):
        raise ctypes.WinError(ctypes.get_last_error())
    sa = _SA(ctypes.sizeof(_SA), sd, False)
    first = True
    while not should_stop():
        flags = PIPE_ACCESS_DUPLEX | (FILE_FLAG_FIRST_PIPE_INSTANCE if first else 0)
        h = k32.CreateNamedPipeW(PIPE_NAME, flags, PIPE_REJECT_REMOTE_CLIENTS, 1, MAX_MSG, MAX_MSG, 0, ctypes.byref(sa))
        if h == INVALID_HANDLE or not h:
            raise ctypes.WinError(ctypes.get_last_error())
        first = False
        try:
            if not k32.ConnectNamedPipe(h, None) and ctypes.get_last_error() != ERROR_PIPE_CONNECTED:
                continue
            buf, data, n = ctypes.create_string_buffer(MAX_MSG), b"", wintypes.DWORD()
            while b"\n" not in data and len(data) < MAX_MSG and k32.ReadFile(h, buf, MAX_MSG, ctypes.byref(n), None) and n.value:
                data += buf.raw[:n.value]
            try:
                req = json.loads(data.split(b"\n", 1)[0])
                reply = handle_request(req) if isinstance(req, dict) else {"ok": False, "error": "expected an object"}
            except ValueError:
                reply = {"ok": False, "error": "bad request"}
            out = json.dumps(reply).encode() + b"\n"
            k32.WriteFile(h, out, len(out), ctypes.byref(n), None)
            k32.FlushFileBuffers(h)
            k32.DisconnectNamedPipe(h)
        finally:
            k32.CloseHandle(h)


def _open(timeout_s: float):
    """Open the client end, or None if no helper is listening."""
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.WaitNamedPipeW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    deadline, misses, seen = time.monotonic() + timeout_s, 0, False
    while time.monotonic() < deadline:
        try:
            return open(PIPE_NAME, "r+b", buffering=0)
        except FileNotFoundError:
            # The server re-creates the pipe between clients. Never seen it: give up fast (not running).
            misses += 1
            if not seen and misses > 3:
                return None
            time.sleep(0.05)
        except OSError:   # busy with the previous client; it may vanish and come back, so retry after
            seen = True
            k32.WaitNamedPipeW(PIPE_NAME, max(1, int((deadline - time.monotonic()) * 1000)))
    return None


def request(req: dict, timeout_s: float = 2.0) -> dict | None:
    """Client side: one request, one reply. None when no helper is listening."""
    try:
        f = _open(timeout_s)
        if f is None:
            return None
        with f:
            f.write(json.dumps(req).encode() + b"\n")
            data = b""
            while b"\n" not in data and len(data) < MAX_MSG:
                chunk = f.read(MAX_MSG)
                if not chunk:
                    break
                data += chunk
        return json.loads(data.split(b"\n", 1)[0])
    except (OSError, ValueError):
        return None
