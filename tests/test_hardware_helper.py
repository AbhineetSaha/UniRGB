import sys
import tempfile
import threading
import unittest
import uuid
from pathlib import Path
from unittest import mock

from unirgb import sensors
from unirgb.adapters.simulated import SimulatedAdapter
from unirgb.app import App, HidCache
from unirgb.hardware_helper import TCTL_SMN, Handler, decode_tctl


class TctlTests(unittest.TestCase):
    def test_decode(self):
        self.assertEqual(decode_tctl(int(52 / 0.125) << 21), 52.0)
        self.assertEqual(decode_tctl((int(101 / 0.125) << 21) | (1 << 19)), 52.0, "-49 range select")
        self.assertEqual(decode_tctl((int(45.625 / 0.125) << 21) | 0x1FFFFF & ~(1 << 19)), 45.625, "low bits ignored")


class HandlerTests(unittest.TestCase):
    def test_only_known_requests_are_served(self):
        offsets = []
        h = Handler(lambda off: offsets.append(off) or (int(60 / 0.125) << 21), "0.1.0")
        self.assertEqual(h({"op": "ping"}), {"ok": True, "version": "0.1.0"})
        self.assertEqual(h({"op": "cpu_temp"})["celsius"], 60.0)
        self.assertEqual(offsets, [TCTL_SMN])
        for bad in ({"op": "read_smn", "offset": 0}, {"op": "write"}, {}):
            self.assertFalse(h(bad)["ok"])

    def test_driver_error_is_reported_not_raised(self):
        def boom(_):
            raise OSError("pawnio failed")
        self.assertEqual(Handler(boom, "x")({"op": "cpu_temp"}), {"ok": False, "error": "pawnio failed"})


class ClientTests(unittest.TestCase):
    def test_missing_helper_triggers_start(self):
        started = []
        self.assertIsNone(sensors.read_hw_helper(lambda: started.append(1), request=lambda req: None))
        self.assertEqual(started, [1])

    def test_reading_and_bad_reply(self):
        r = sensors.read_hw_helper(request=lambda req: {"ok": True, "celsius": 48.5, "label": "CPU (Tctl)"})
        self.assertEqual((r.celsius, r.source), (48.5, "cpu-pawnio"))
        self.assertIsNone(sensors.read_hw_helper(request=lambda req: {"ok": True, "celsius": "hot"}))

    def test_app_starts_helper_only_when_enabled_and_backs_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = App(adapters=[SimulatedAdapter()], hid_cache=HidCache(lambda: []), scenes_path=Path(tmp) / "s.json")
            with mock.patch("unirgb.system_setup.start_helper") as start,                     mock.patch("unirgb.system_setup.driver_state", return_value="running") as drv:
                app._start_helper()
                start.assert_not_called()
                app.prefs.update({"cpu_temperature": True})
                app._start_helper()
                app._start_helper()
                self.assertEqual(start.call_count, 1, "second call within 30 s is skipped")
                drv.return_value, app._helper_started = "not-installed", float("-inf")
                app._start_helper()
                self.assertEqual(start.call_count, 1, "no driver: the helper would only fail")
            app.shutdown()


@unittest.skipUnless(sys.platform == "win32", "Windows named pipes")
class PipeRoundTripTests(unittest.TestCase):
    def test_request_reply_over_a_real_pipe(self):
        from unirgb import system_setup
        from unirgb.hostos import pipe
        name = rf"\\.\pipe\UniRGB-test-{uuid.uuid4().hex}"
        with mock.patch.object(pipe, "PIPE_NAME", name):
            ready = threading.Event()
            h = Handler(lambda off: int(55 / 0.125) << 21, "test")
            t = threading.Thread(target=lambda: (ready.set(), pipe.serve(system_setup.current_user_sid(), h)), daemon=True)
            t.start()
            ready.wait(2)
            reply = None
            for _ in range(50):   # the server needs a moment to create the pipe
                reply = pipe.request({"op": "cpu_temp"})
                if reply:
                    break
                threading.Event().wait(0.05)
            self.assertEqual(reply, {"ok": True, "celsius": 55.0, "label": "CPU (Tctl)"})
            self.assertEqual(pipe.request({"op": "nope"}), {"ok": False, "error": "unknown request"})

    def test_no_helper_gives_up_fast(self):
        import time
        from unirgb.hostos import pipe
        with mock.patch.object(pipe, "PIPE_NAME", rf"\\.\pipe\UniRGB-absent-{uuid.uuid4().hex}"):
            t = time.monotonic()
            self.assertIsNone(pipe.request({"op": "ping"}))
            self.assertLess(time.monotonic() - t, 0.5, "the display polls every second")


if __name__ == "__main__":
    unittest.main()
