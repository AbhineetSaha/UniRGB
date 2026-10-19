import json
import tempfile
import time
import unittest
from pathlib import Path

from tests.fakes import FakeHid
from unirgb import sensors
from unirgb.adapters.cooler_display import CoolerDisplayAdapter
from unirgb.protocols import antcooler

HID = FakeHid(0x5131, 0x2007, 0x0C, 0x01, feature_len=65)
HID.output_len = 65
HID.path = "fake-cooler"


class _Dev:
    def close(self):
        pass


class ProtocolTests(unittest.TestCase):
    def test_packet_layout(self):
        p = antcooler.build_packet(47.6)
        self.assertEqual(len(p), 65)
        self.assertEqual((p[0], p[1], p[2]), (0x00, 0x40, 48))
        self.assertEqual(sum(p[3:]), 0)

    def test_fahrenheit_flag(self):
        p = antcooler.build_packet(30, fahrenheit=True)
        self.assertEqual(p[2] & 0x80, 0x80)
        self.assertEqual(p[2] & 0x7F, 86)

    def test_anti_blink(self):
        self.assertEqual(antcooler.shape_temperature(92, "cap84"), 84)
        self.assertEqual(antcooler.shape_temperature(100, "compress"), 84)
        self.assertEqual(antcooler.shape_temperature(75, "compress"), 75)
        self.assertEqual(antcooler.shape_temperature(92, "raw"), 92)
        self.assertEqual(antcooler.shape_temperature(-5), 0)

    def test_blank(self):
        self.assertEqual(antcooler.build_blank()[:3], bytes([0, 0x40, 0]))


class SensorTests(unittest.TestCase):
    def test_parse_amd_cli(self):
        self.assertEqual(sensors.parse_amd_cli("GetCurrentTemperature ...................  46.38 Celsius\n"), 46.38)
        self.assertIsNone(sensors.parse_amd_cli("User is not admin..."))

    def test_helper_file_staleness(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "t.json"
            p.write_text(json.dumps({"celsius": 51.5, "at": 1000.0}))
            self.assertEqual(sensors.read_helper_file(p, now=1005).celsius, 51.5)
            self.assertIsNone(sensors.read_helper_file(p, now=1100), "stale readings are ignored")
            self.assertIsNone(sensors.read_helper_file(Path(d) / "missing.json"))


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.sent = []
        self.cpu = None
        self.gpu = sensors.Reading(40.0, "gpu-nvidia", "GPU", time.time())

    def tearDown(self):
        self.a.shutdown()
        self.tmp.cleanup()

    def make(self, confirmed=True):
        (Path(self.tmp.name) / "c.json").write_text(json.dumps({"confirmed": confirmed}))
        self.a = CoolerDisplayAdapter(lambda: [HID], open_device=lambda i: _Dev(),
                                      write=lambda dev, data: self.sent.append(data),
                                      settings_path=Path(self.tmp.name) / "c.json", interval=60,
                                      cpu_reader=lambda: self.cpu, gpu_reader=lambda: self.gpu)
        return self.a.discover()

    def test_discovery_and_gpu_fallback(self):
        [d] = self.make()
        self.assertEqual(d.info.category.value, "cooler")
        self.a.tick()
        self.assertEqual(self.sent[-1][2], 40)
        self.assertEqual(self.a.last["reading"]["source"], "gpu-nvidia")

    def test_cpu_preferred_when_helper_runs(self):
        self.make()
        self.cpu = sensors.Reading(63.2, "cpu-amd", "CPU", time.time())
        self.a.tick()
        self.assertEqual(self.sent[-1][2], 63)

    def test_cpu_only_without_helper_sends_nothing(self):
        self.make()
        n = len(self.sent)
        self.assertTrue(self.a.configure("cooler:5131:2007", {"source": "cpu"}).ok)
        self.assertEqual(len(self.sent), n)
        self.assertIn("no temperature", self.a.last["error"])

    def test_settings_validation_persistence_and_disable(self):
        self.make()
        for bad in ({"source": "moon"}, {"enabled": "yes"}, {"anti_blink": "x"}, {"color": "#fff"}):
            self.assertFalse(self.a.configure("cooler:5131:2007", bad).ok)
        self.assertTrue(self.a.configure("cooler:5131:2007", {"fahrenheit": True}).ok)
        self.assertEqual(self.sent[-1][2] & 0x80, 0x80)
        self.assertTrue(json.loads((Path(self.tmp.name) / "c.json").read_text())["fahrenheit"])
        self.assertTrue(self.a.configure("cooler:5131:2007", {"enabled": False}).ok)
        self.assertEqual(self.sent[-1], antcooler.build_blank(), "turning off blanks the panel")

    def test_nothing_sent_until_confirmed(self):
        self.make(confirmed=False)
        self.a.tick()
        self.assertEqual(self.sent, [], "generic 5131:2007 chip: no packets before confirmation")
        self.assertIn("confirm", self.a.last["error"])
        self.assertTrue(self.a.configure("cooler:5131:2007", {"confirmed": True}).ok)
        self.assertEqual(self.sent[-1][2], 40)

    def test_shutdown_blanks_the_panel(self):
        self.make()
        self.a.shutdown()
        self.assertEqual(self.sent[-1], antcooler.build_blank(), "no frozen temperature after quit")

    def test_write_error_recovers(self):
        self.make()
        calls = {"n": 0}

        def flaky(dev, data):
            calls["n"] += 1
            if calls["n"] == 1:
                raise OSError("unplugged")
            self.sent.append(data)
        self.a.write = flaky
        self.a.tick()
        self.assertIn("unplugged", self.a.last["error"])
        self.a.tick()
        self.assertIsNone(self.a.last["error"])


if __name__ == "__main__":
    unittest.main()


class DecodeTests(unittest.TestCase):
    def test_utf16_and_ansi(self):
        line = "GetCurrentTemperature ....  52.10 Celsius\r\n"
        self.assertEqual(sensors.parse_amd_cli(sensors.decode_cli(line.encode("utf-16-le"))), 52.10)
        self.assertEqual(sensors.parse_amd_cli(sensors.decode_cli(line.encode("ascii"))), 52.10)


class LhmTests(unittest.TestCase):
    DOC = {"Text": "Sensor", "Children": [{"Text": "PC", "Children": [
        {"Text": "AMD Ryzen 7 9800X3D", "Children": [{"Text": "Temperatures", "Children": [
            {"Text": "Core (Tctl/Tdie)", "Value": "47,5 \u00b0C", "Type": "Temperature", "SensorId": "/amdcpu/0/temperature/2"},
            {"Text": "CCD1 (Tdie)", "Value": "45.0 \u00b0C", "Type": "Temperature", "SensorId": "/amdcpu/0/temperature/3"}]}]},
        {"Text": "Nuvoton NCT6687D", "Children": [{"Text": "Fans", "Children": [
            {"Text": "CPU Fan", "Value": "1205 RPM", "Type": "Fan", "SensorId": "/lpc/nct6687d/0/fan/0"},
            {"Text": "Pump Fan", "Value": "2650 RPM", "Type": "Fan", "SensorId": "/lpc/nct6687d/0/fan/1"}]}]}]}]}

    def test_parse(self):
        d = sensors.parse_lhm(self.DOC)
        self.assertEqual(d["cpu"], ("Core (Tctl/Tdie)", 47.5))
        self.assertEqual([(f["name"], f["rpm"]) for f in d["fans"]], [("CPU Fan", 1205), ("Pump Fan", 2650)])

    def test_unreachable(self):
        self.assertIsNone(sensors.read_lhm("http://127.0.0.1:9/data.json", timeout=0.3))
