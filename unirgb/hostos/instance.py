"""One UniRGB per user session: a named mutex, plus an event a second launch uses to show the first one's window."""
from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

ERROR_ALREADY_EXISTS = 183
WAIT_OBJECT_0 = 0


class SingleInstance:
    def __init__(self, name: str = "UniRGB"):
        k = self._k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.CreateMutexW.restype = k.CreateEventW.restype = wintypes.HANDLE
        k.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
        k.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        k.SetEvent.argtypes = k.CloseHandle.argtypes = [wintypes.HANDLE]
        k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self._mutex = k.CreateMutexW(None, True, f"Local\\{name}-instance")
        self.first = ctypes.get_last_error() != ERROR_ALREADY_EXISTS
        self._event = k.CreateEventW(None, False, False, f"Local\\{name}-show")   # auto-reset

    def show_existing(self) -> None:
        """From a second launch: ask the running instance to show its window."""
        self._k.SetEvent(self._event)

    def watch(self, on_show) -> None:
        """In the running instance: call on_show() (from a worker thread) whenever a second launch asks."""
        def loop():
            while self._event and self._k.WaitForSingleObject(self._event, 0xFFFFFFFF) == WAIT_OBJECT_0:
                if self._event:
                    on_show()
        threading.Thread(target=loop, name="instance-show", daemon=True).start()

    def release(self) -> None:
        """Before restarting: let the new process become the first instance."""
        for h in (self._mutex, self._event):
            if h:
                self._k.CloseHandle(h)
        self._mutex = self._event = None
