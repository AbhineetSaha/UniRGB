import ctypes
import sys
import threading
import unittest
from pathlib import Path

ICON = Path(__file__).resolve().parents[1] / "unirgb" / "ui" / "logo.ico"


@unittest.skipUnless(sys.platform == "win32", "Windows tray")
class TrayTest(unittest.TestCase):
    def test_icon_appears_answers_a_click_and_goes_away(self):
        from unirgb.hostos import tray
        opened = threading.Event()
        t = tray.Tray(ICON, "UniRGB test", on_open=opened.set, on_quit=lambda: None)
        self.assertTrue(t.start())
        # what Windows sends when the icon is left-clicked
        ctypes.windll.user32.SendMessageW.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t]
        ctypes.windll.user32.SendMessageW(t._hwnd, tray.CALLBACK_MSG, 1, tray.WM_LBUTTONUP)
        self.assertTrue(opened.wait(2))
        t.stop()
        self.assertFalse(t._thread.is_alive())


if __name__ == "__main__":
    unittest.main()
