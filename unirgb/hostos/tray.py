"""Notification-area (tray) icon so you can see UniRGB is running: click opens it, right-click has Quit.

Plain Win32 through ctypes: a hidden window owns the icon and runs its own message loop on a thread.
"""
from __future__ import annotations

import ctypes
import logging
import threading
from ctypes import wintypes as w
from pathlib import Path

log = logging.getLogger("unirgb.tray")

WM_DESTROY, WM_CLOSE, WM_NULL, WM_APP = 0x0002, 0x0010, 0x0000, 0x8000
WM_LBUTTONUP, WM_RBUTTONUP, WM_CONTEXTMENU = 0x0202, 0x0205, 0x007B
NIM_ADD, NIM_DELETE = 0, 2
NIF_MESSAGE, NIF_ICON, NIF_TIP = 1, 2, 4
CALLBACK_MSG = WM_APP + 1
CMD_OPEN, CMD_QUIT = 1, 2

LRESULT = ctypes.c_ssize_t
WNDPROC = ctypes.WINFUNCTYPE(LRESULT, w.HWND, w.UINT, w.WPARAM, w.LPARAM)


class WNDCLASSW(ctypes.Structure):
    _fields_ = [("style", w.UINT), ("lpfnWndProc", WNDPROC), ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int), ("hInstance", w.HINSTANCE), ("hIcon", w.HICON),
                ("hCursor", w.HANDLE), ("hbrBackground", w.HBRUSH), ("lpszMenuName", w.LPCWSTR),
                ("lpszClassName", w.LPCWSTR)]


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", w.DWORD), ("hWnd", w.HWND), ("uID", w.UINT), ("uFlags", w.UINT),
                ("uCallbackMessage", w.UINT), ("hIcon", w.HICON), ("szTip", w.WCHAR * 128),
                ("dwState", w.DWORD), ("dwStateMask", w.DWORD), ("szInfo", w.WCHAR * 256),
                ("uVersion", w.UINT), ("szInfoTitle", w.WCHAR * 64), ("dwInfoFlags", w.DWORD),
                ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", w.HICON)]


def _api():
    u, s, k = ctypes.windll.user32, ctypes.windll.shell32, ctypes.windll.kernel32
    u.DefWindowProcW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.DefWindowProcW.restype = LRESULT
    u.CreateWindowExW.argtypes = [w.DWORD, w.LPCWSTR, w.LPCWSTR, w.DWORD, ctypes.c_int, ctypes.c_int,
                                  ctypes.c_int, ctypes.c_int, w.HWND, w.HMENU, w.HINSTANCE, w.LPVOID]
    u.CreateWindowExW.restype = w.HWND
    u.RegisterClassW.argtypes = [ctypes.POINTER(WNDCLASSW)]
    u.RegisterClassW.restype = w.ATOM
    u.LoadImageW.argtypes = [w.HINSTANCE, w.LPCWSTR, w.UINT, ctypes.c_int, ctypes.c_int, w.UINT]
    u.LoadImageW.restype = w.HANDLE
    u.LoadIconW.argtypes = [w.HINSTANCE, w.LPVOID]
    u.LoadIconW.restype = w.HICON
    u.CreatePopupMenu.restype = w.HMENU
    u.AppendMenuW.argtypes = [w.HMENU, w.UINT, ctypes.c_size_t, w.LPCWSTR]
    u.TrackPopupMenu.argtypes = [w.HMENU, w.UINT, ctypes.c_int, ctypes.c_int, ctypes.c_int, w.HWND, w.LPVOID]
    u.DestroyMenu.argtypes = [w.HMENU]
    u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
    u.DestroyWindow.argtypes = [w.HWND]
    u.SetForegroundWindow.argtypes = [w.HWND]
    u.DestroyIcon.argtypes = [w.HICON]
    u.GetMessageW.argtypes = [ctypes.POINTER(w.MSG), w.HWND, w.UINT, w.UINT]
    u.DispatchMessageW.argtypes = [ctypes.POINTER(w.MSG)]
    s.Shell_NotifyIconW.argtypes = [w.DWORD, ctypes.POINTER(NOTIFYICONDATAW)]
    k.GetModuleHandleW.restype = w.HMODULE
    return u, s, k


class Tray:
    def __init__(self, icon_path: Path, tip: str, on_open, on_quit):
        self._icon_path, self._tip, self._on_open, self._on_quit = icon_path, tip, on_open, on_quit
        self._hwnd = None
        self._ready = threading.Event()
        self.shown = False   # True once Windows accepted the icon
        self._thread = threading.Thread(target=self._run, name="tray", daemon=True)

    def start(self, timeout: float = 5.0) -> bool:
        self._thread.start()
        self._ready.wait(timeout)
        return self.shown

    def stop(self) -> None:
        """Remove the icon (otherwise a dead one lingers until the mouse passes over it)."""
        if self._hwnd:
            self._u.PostMessageW(self._hwnd, WM_CLOSE, 0, 0)
        self._thread.join(2.0)

    def _notify(self, msg: int) -> bool:
        nid = NOTIFYICONDATAW(cbSize=ctypes.sizeof(NOTIFYICONDATAW), hWnd=self._hwnd, uID=1,
                              uFlags=NIF_MESSAGE | NIF_ICON | NIF_TIP, uCallbackMessage=CALLBACK_MSG,
                              hIcon=self._hicon, szTip=self._tip[:127])
        return bool(self._s.Shell_NotifyIconW(msg, ctypes.byref(nid)))

    def _menu(self) -> None:
        u = self._u
        menu = u.CreatePopupMenu()
        u.AppendMenuW(menu, 0, CMD_OPEN, "Open UniRGB")
        u.AppendMenuW(menu, 0, CMD_QUIT, "Quit UniRGB")
        pt = w.POINT()
        u.GetCursorPos(ctypes.byref(pt))
        u.SetForegroundWindow(self._hwnd)   # without this the menu does not close when you click away
        cmd = u.TrackPopupMenu(menu, 0x0100 | 0x0002, pt.x, pt.y, 0, self._hwnd, None)   # RETURNCMD|RIGHTBUTTON
        u.PostMessageW(self._hwnd, WM_NULL, 0, 0)
        u.DestroyMenu(menu)
        if cmd == CMD_OPEN:
            self._on_open()
        elif cmd == CMD_QUIT:
            self._on_quit()

    def _proc(self, hwnd, msg, wparam, lparam):
        try:
            if msg == CALLBACK_MSG:
                if lparam == WM_LBUTTONUP:
                    self._on_open()
                elif lparam in (WM_RBUTTONUP, WM_CONTEXTMENU):
                    self._menu()
                return 0
            if msg == self._taskbar_created:   # Explorer restarted: the icon is gone, add it again
                self._notify(NIM_ADD)
                return 0
            if msg == WM_CLOSE:
                self._u.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                self._notify(NIM_DELETE)
                self._u.PostQuitMessage(0)
                return 0
        except Exception:
            log.exception("tray event failed")
        return self._u.DefWindowProcW(hwnd, msg, wparam, lparam)

    def _run(self) -> None:
        try:
            u, self._s, k = _api()
            self._u = u
            hinst = k.GetModuleHandleW(None)
            self._wndproc = WNDPROC(self._proc)   # keep a reference: Windows calls it for the window's life
            cls = WNDCLASSW(lpfnWndProc=self._wndproc, hInstance=hinst, lpszClassName="UniRGBTray")
            u.RegisterClassW(ctypes.byref(cls))
            self._taskbar_created = u.RegisterWindowMessageW("TaskbarCreated")
            # a hidden top-level window (not message-only) so it receives the TaskbarCreated broadcast
            self._hwnd = u.CreateWindowExW(0, "UniRGBTray", "UniRGB", 0, 0, 0, 0, 0, None, None, hinst, None)
            cx, cy = u.GetSystemMetrics(49), u.GetSystemMetrics(50)   # SM_CXSMICON, SM_CYSMICON
            self._hicon = (u.LoadImageW(None, str(self._icon_path), 1, cx, cy, 0x10)   # IMAGE_ICON, LR_LOADFROMFILE
                           or u.LoadIconW(None, ctypes.c_void_p(32512)))              # IDI_APPLICATION
            self.shown = bool(self._hwnd) and self._notify(NIM_ADD)
        except Exception:
            log.exception("tray icon unavailable")
            return
        finally:
            self._ready.set()
        if not self.shown:
            log.warning("Windows did not accept the tray icon")
            if self._hwnd:
                u.DestroyWindow(self._hwnd)
            self._hwnd = None
            return
        msg = w.MSG()
        while u.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            u.TranslateMessage(ctypes.byref(msg))
            u.DispatchMessageW(ctypes.byref(msg))
        u.DestroyIcon(self._hicon)
