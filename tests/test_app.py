import sys
import tempfile
import threading
import time
import unittest
import uuid
from pathlib import Path

from unirgb.adapters.simulated import SimulatedAdapter
from unirgb.app import App, HidCache
from unirgb.core.models import Color, LightingState


class LastStateTests(unittest.TestCase):
    def test_last_color_is_reapplied_after_restart_and_reconnect(self):
        with tempfile.TemporaryDirectory() as d:
            mk = lambda sim: App(adapters=[sim], hid_cache=HidCache(lambda: []), scenes_path=Path(d) / "s.json")
            sim1 = SimulatedAdapter()
            a = mk(sim1)
            a.rescan()
            self.assertTrue(a.orch.apply("sim:fan", LightingState(color=Color(1, 2, 3))).ok)
            a.shutdown()

            sim2 = SimulatedAdapter()                       # "next boot"
            b = mk(sim2)
            b.rescan()
            time.sleep(0.2)
            self.assertEqual(sim2.read_state("sim:fan").color, Color(1, 2, 3))

            sim2.connected = False; b.rescan()              # device drops out ...
            sim2.state.clear(); sim2.connected = True; b.rescan()   # ... and comes back without its colors
            time.sleep(0.2)
            self.assertEqual(sim2.read_state("sim:fan").color, Color(1, 2, 3))

            self.assertTrue(b.orch.restore("sim:fan").ok)   # restore = forget it for next boot
            b.shutdown()
            c = mk(SimulatedAdapter())
            c.rescan()
            time.sleep(0.2)
            self.assertIsNone(c.orch.adapters["sim"].read_state("sim:fan"))
            c.shutdown()

    def test_restart_request_sets_both_flags(self):
        with tempfile.TemporaryDirectory() as d:
            a = App(adapters=[SimulatedAdapter()], hid_cache=HidCache(lambda: []), scenes_path=Path(d) / "s.json")
            a.request_quit(restart=True)
            self.assertTrue(a.quit_requested.is_set() and a.restart_requested)
            a.shutdown()


@unittest.skipUnless(sys.platform == "win32", "Windows named objects")
class SingleInstanceTests(unittest.TestCase):
    def test_second_launch_is_refused_and_shows_the_first(self):
        from unirgb.hostos.instance import SingleInstance
        name = f"UniRGB-test-{uuid.uuid4().hex}"
        first, shown = SingleInstance(name), threading.Event()
        first.watch(shown.set)
        second = SingleInstance(name)
        self.assertTrue(first.first)
        self.assertFalse(second.first)
        second.show_existing()
        self.assertTrue(shown.wait(2))
        second.release()
        first.release()
        self.assertTrue(SingleInstance(name).first, "released: the next launch is first again")


if __name__ == "__main__":
    unittest.main()
