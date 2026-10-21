"""The native window, driven against simulated devices. Skipped where Tk has no display."""
import gc
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest import mock

from unirgb.adapters.simulated import SimulatedAdapter
from unirgb.app import App, HidCache
from unirgb.gui import Bridge
from unirgb.gui.dialogs import DiagnosticsDialog, ScenesDialog, SettingsDialog
from unirgb.gui.window import MainWindow

READY = {"task": True, "helper": True, "stale": False, "driver": "running", "ready": True, "last_result": None}


class GuiTests(unittest.TestCase):
    def setUp(self):
        # Tk objects left by earlier tests must be freed on this thread: if a worker thread's garbage collection
        # frees them, Tk waits for a main loop that tests don't run.
        gc.collect()
        try:
            self.root = tk.Tk()
        except tk.TclError as e:
            self.skipTest(f"no display: {e}")
        self.root.withdraw()
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(adapters=[SimulatedAdapter()], hid_cache=HidCache(lambda: []),
                       scenes_path=Path(self.tmp.name) / "s.json", simulate=True)
        self.app.rescan()
        self.quit = []
        self.win = MainWindow(self.root, self.app, Bridge(self.root, 10), "test", on_quit=lambda: self.quit.append(1),
                              open_settings=lambda first: None, open_scenes=lambda: None, open_diagnostics=lambda: None)

    def tearDown(self):
        self.root.destroy()
        gc.collect()
        self.app.shutdown()
        self.tmp.cleanup()

    def pump(self, cond, timeout=3.0):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            self.root.update()
            if cond():
                return True
            time.sleep(0.01)
        return False

    def desired(self, dev):
        r = self.app.orch.registry.get(dev)
        return r.desired.color.hex() if r and r.desired and r.desired.color else None

    def test_lists_devices_and_selects_a_controllable_one(self):
        self.assertTrue(self.win.tree.exists("grp:Controllable"))
        self.assertIsNotNone(self.win.sel)
        self.assertTrue(self.app.orch.registry.get(self.win.sel).caps.writable)

    def test_live_color_change_reaches_the_device(self):
        rec = self.app.orch.registry.get(self.win.sel)
        self.win._set_color(rec, "#00ff00")
        self.assertTrue(self.pump(lambda: self.desired(rec.info.id) == "#00ff00"))

    def test_sync_all_and_restore(self):
        self.win.sync_color = "#123456"
        self.win.sync_all()
        ids = [r.info.id for r in self.app.orch.registry.snapshot() if r.caps.writable and not r.shadowed_by]
        self.assertTrue(self.pump(lambda: all(self.desired(i) == "#123456" for i in ids)))
        rec = self.app.orch.registry.get(ids[0])
        self.win._restore(rec)
        self.assertTrue(self.pump(lambda: self.app.orch.registry.get(ids[0]).desired is None))

    def test_settings_save_preferences(self):
        with mock.patch("unirgb.system_setup.status", return_value=READY):
            dlg = SettingsDialog(self.win, True, on_restart=lambda: None)
            dlg.cpu.set(True)
            dlg.save()
            self.pump(lambda: not dlg.winfo_exists(), 1.0)
        p = self.app.prefs.prefs
        self.assertTrue(p.setup_done and p.cpu_temperature)

    def test_settings_rejects_nothing_silently(self):
        with mock.patch("unirgb.system_setup.status", return_value=READY), \
                mock.patch.dict("unirgb.prefs.AVAILABLE", {"ram_lighting": False}):
            dlg = SettingsDialog(self.win, False, on_restart=lambda: None)
            dlg.ram.set(True)   # not available: refused with a message, prefs unchanged
            dlg.save()
        self.assertFalse(self.app.prefs.prefs.ram_lighting)
        self.assertIn("not available", self.win.status.cget("text"))

    def test_scenes_save_apply_delete(self):
        rec = self.app.orch.registry.get(self.win.sel)
        self.win._set_color(rec, "#abcdef")
        self.pump(lambda: self.desired(rec.info.id) == "#abcdef")
        dlg = ScenesDialog(self.win)
        dlg.name.set("Night")
        dlg.save()
        self.assertIn("Night", self.app.scenes.list())
        self.win._set_color(rec, "#000001")
        self.pump(lambda: self.desired(rec.info.id) == "#000001")
        dlg.apply("Night")
        self.assertTrue(self.pump(lambda: self.desired(rec.info.id) == "#abcdef"))
        dlg.delete("Night")
        self.assertNotIn("Night", self.app.scenes.list())

    def test_diagnostics_opens(self):
        DiagnosticsDialog(self.win)
        self.root.update()

    def test_every_device_page_renders(self):
        for r in self.app.orch.registry.snapshot():
            self.win.sel, self.win._sig = r.info.id, None
            self.win.refresh()
            self.root.update()


if __name__ == "__main__":
    unittest.main()
