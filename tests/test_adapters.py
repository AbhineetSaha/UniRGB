import struct
import tempfile
import time
import unittest
from pathlib import Path

from tests.fakes import FakeChroma, FakeHid, FakeOpenRGB
from unirgb.adapters.inventory import InventoryAdapter
from unirgb.adapters.msi_mystic import MysticLightMonitor, parse_zones
from unirgb.adapters.openrgb import OpenRGBAdapter
from unirgb.adapters.razer_chroma import MOUSE_ZONES, RazerChromaAdapter, bgr
from unirgb.core.models import Color, Connection, LightingState, Support

RED, GREEN = Color(255, 0, 0), Color(0, 255, 0)
BASILISK = FakeHid(0x1532, 0x00AB, 0x01, 0x02, "Razer Basilisk V3 Pro", "Razer")


class RazerTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeChroma()
        self.tmp = tempfile.TemporaryDirectory()
        self.journal = Path(self.tmp.name) / "chroma_session.json"
        self.a = RazerChromaAdapter(lambda: [BASILISK], base_url=self.fake.base, heartbeat_s=0.1, journal=self.journal)

    def tearDown(self):
        self.a.shutdown()
        self.fake.close()
        self.tmp.cleanup()

    def mouse(self):
        return next(d.info.id for d in self.a.discover() if d.info.category.value == "mouse")

    def test_discovery_without_session(self):
        devs = self.a.discover()
        self.assertEqual({d.info.id for d in devs}, {"razer:mouse:1532:00AB", "razer:chromalink"})
        self.assertFalse(any(m == "POST" for m, _, _ in self.fake.calls), "discovery must not take over lighting")
        cl = next(d for d in devs if d.info.id == "razer:chromalink")
        self.assertEqual(cl.caps.color, Support.EXPERIMENTAL)

    def test_no_mouse_when_hid_absent(self):
        a = RazerChromaAdapter(lambda: [], base_url=self.fake.base, journal=self.journal)
        self.assertEqual([d.info.id for d in a.discover()], ["razer:chromalink"])

    def test_bgr_encoding(self):
        self.assertEqual(bgr(Color(0x11, 0x22, 0x33)), 0x332211)

    def test_static_brightness_and_off(self):
        m = self.mouse()
        self.assertTrue(self.a.apply(m, LightingState(color=Color(200, 100, 0), brightness=50)).ok)
        self.assertTrue(self.a.apply(m, LightingState(mode="off")).ok)
        eff = self.fake.effects("mouse")
        self.assertEqual(eff[0], {"effect": "CHROMA_STATIC", "param": {"color": bgr(Color(100, 50, 0))}})
        self.assertEqual(eff[1], {"effect": "CHROMA_NONE"})
        self.assertEqual(sum(1 for m_, p, _ in self.fake.calls if m_ == "POST"), 1, "one session reused")

    def test_zone_grid(self):
        m = self.mouse()
        self.assertTrue(self.a.apply(m, LightingState(color=GREEN, zones={"logo": RED})).ok)
        body = self.fake.effects("mouse")[-1]
        self.assertEqual(body["effect"], "CHROMA_CUSTOM2")
        grid = body["param"]
        self.assertEqual((len(grid), len(grid[0])), (9, 7))
        r, c = MOUSE_ZONES["logo"][0]
        self.assertEqual(grid[r][c], bgr(RED))
        self.assertEqual(grid[0][0], bgr(GREEN))

    def test_heartbeat(self):
        self.a.apply(self.mouse(), LightingState(color=RED))
        time.sleep(0.35)
        beats = [p for m, p, _ in self.fake.calls if m == "PUT" and p.endswith("/heartbeat")]
        self.assertGreaterEqual(len(beats), 2)
        self.assertNotIn("411", [m for m, _, _ in self.fake.calls], "body-less writes are rejected by HTTP.sys")
        self.assertIsNotNone(self.a._session_uri, "heartbeats must keep the session alive")
        self.assertEqual(sum(1 for m, *_ in self.fake.calls if m == "POST"), 1)

    def test_session_recreated_after_loss(self):
        m = self.mouse()
        self.a.apply(m, LightingState(color=RED))
        self.fake.sessions.clear()   # Synapse restarted / session expired
        self.assertTrue(self.a.apply(m, LightingState(color=GREEN)).ok)
        self.assertEqual(sum(1 for m_, *_ in self.fake.calls if m_ == "POST"), 2)

    def test_error_result(self):
        m = self.mouse()
        self.fake.result_code = 1167
        r = self.a.apply(m, LightingState(color=RED))
        self.assertFalse(r.ok)
        self.assertIn("device not connected", r.message)

    def test_restore_ends_session(self):
        m = self.mouse()
        self.a.apply(m, LightingState(color=RED))
        self.assertTrue(self.journal.exists(), "live session is journaled")
        r = self.a.restore(m)
        self.assertTrue(r.ok)
        self.assertEqual(r.released, ["razer:chromalink"])
        self.assertEqual(self.fake.sessions, set())
        self.assertFalse(self.journal.exists())

    def test_stale_session_from_crash_is_deleted_on_next_start(self):
        self.a.apply(self.mouse(), LightingState(color=RED))
        stale = set(self.fake.sessions)
        self.a._hb_stop.set()          # simulate a crash: no DELETE, journal left behind
        self.a._session_uri = None
        b = RazerChromaAdapter(lambda: [BASILISK], base_url=self.fake.base, journal=self.journal)
        b.discover()
        self.assertTrue(stale and not (stale & self.fake.sessions), "stale session deleted")
        self.assertFalse(self.journal.exists())
        b.shutdown()

    def test_unreachable(self):
        a = RazerChromaAdapter(lambda: [BASILISK], base_url="http://127.0.0.1:9/razer/chromasdk", timeout=0.3,
                               journal=self.journal)
        self.assertFalse(a.health().available)
        self.assertEqual(a.discover(), [])


class OpenRGBTests(unittest.TestCase):
    def setUp(self):
        self.fake = FakeOpenRGB([
            ("MSI MYSTIC LIGHT", "HID: \\\\?\\HID#VID_0DB0&PID_0076#b&1", [("JRGB1", 1), ("JARGB_V2_1", 4)]),
            ("Razer Basilisk V3 Pro", "HID: \\\\?\\HID#VID_1532&PID_00AB&MI_00", [("Logo", 1)]),
        ])
        self.a = OpenRGBAdapter(port=self.fake.port, timeout=1.0, allowed_types=None)

    def tearDown(self):
        self.a.shutdown()
        self.fake.close()

    def test_discover_parses_controllers(self):
        devs = self.a.discover()
        self.assertEqual(len(devs), 2)
        msi = devs[0]
        self.assertEqual(msi.info.vidpid, "0DB0:0076")
        self.assertEqual(msi.info.physical_key, "usb:0DB0:0076")
        self.assertEqual([z.name for z in msi.caps.zones], ["JRGB1", "JARGB_V2_1"])
        self.assertEqual(msi.caps.color, Support.UNTESTED)

    def test_apply_payload(self):
        dev = self.a.discover()[0].info.id
        r = self.a.apply(dev, LightingState(color=RED, zones={"z1": GREEN}))
        self.assertTrue(r.ok, r.message)
        time.sleep(0.1)
        pkts = [(p, body) for d, p, body in self.fake.received if p in (1100, 1050)]
        self.assertEqual([p for p, _ in pkts], [1100, 1050])
        body = pkts[1][1]
        size, n = struct.unpack_from("<IH", body)
        colors = struct.unpack_from(f"<{n}I", body, 6)
        self.assertEqual((size, n), (len(body), 5))
        self.assertEqual(colors, (0x0000FF,) + (0x00FF00,) * 4)

    def test_apply_refuses_when_openrgb_list_shifted(self):
        dev = self.a.discover()[0].info.id            # index 0 = MSI MYSTIC LIGHT
        self.fake.controllers.reverse()                # OpenRGB reorders its list
        r = self.a.apply(dev, LightingState(color=RED))
        self.assertFalse(r.ok)
        self.assertIn("changed", r.message)
        time.sleep(0.1)
        self.assertNotIn(1050, [p for _, p, _ in self.fake.received], "no color write after a shift")

    def test_read_state(self):
        dev = self.a.discover()[0].info.id
        st = self.a.read_state(dev)
        self.assertEqual(st.color, Color(255, 0, 0))

    def test_protocol_v0_server(self):
        fake0 = FakeOpenRGB([("X", "loc", [("Z", 2)])], server_proto=0)
        try:
            a = OpenRGBAdapter(port=fake0.port, timeout=1.0, allowed_types=None)
            self.assertEqual(len(a.discover()), 1)
            a.shutdown()
        finally:
            fake0.close()

    def test_default_is_ram_only(self):
        fake = FakeOpenRGB([("MSI MYSTIC LIGHT", "HID: x", [("Z", 1)], 0), ("ENE DRAM", "I2C: PIIX4, address 0x70", [("DRAM", 8)], 1)])
        try:
            a = OpenRGBAdapter(port=fake.port, timeout=1.0)
            devs = a.discover()
            self.assertEqual([d.info.category.value for d in devs], ["memory"])
            self.assertTrue(devs[0].info.id.startswith("openrgb:1:"), "OpenRGB index kept")
            self.assertTrue(a.apply(devs[0].info.id, LightingState(color=RED)).ok)
            time.sleep(0.1)
            self.assertIn((1, 1050), [(dv, p) for dv, p, _ in fake.received])
            a.shutdown()
        finally:
            fake.close()

    def test_health_and_rescans_never_bare_connect(self):
        for _ in range(3):
            self.assertTrue(self.a.health().available)
            self.a.discover()
        time.sleep(0.1)
        self.assertEqual(self.fake.bare_connections, 0, "bare connect/close wedges real OpenRGB servers")
        self.assertEqual(self.fake.connections, 1, "one persistent connection is reused")

    def test_absent_server(self):
        a = OpenRGBAdapter(port=9, timeout=0.3)
        self.assertFalse(a.health().available)
        self.assertEqual(a.discover(), [])


SAMPLE_LOG = """
10-18-2026 09:00:00 PM        ResetItem : 0	(OLD)	10
10-19-2026 15:15:55:561 PM        ResetItem : 0	(JRGB1)	10
10-19-2026 15:15:55:562 PM        ResetItem : 1	(JARGB_V2_1)	10
10-19-2026 15:15:55:563 PM        ResetItem : 5	(SELECT ALL)	10
10-19-2026 15:15:55:564 PM        ResetItem : 6	(DDR5 DIMM)	1
"""


class MsiAndInventoryTests(unittest.TestCase):
    def test_parse_zones_uses_latest_block(self):
        self.assertEqual(parse_zones(SAMPLE_LOG), ["JRGB1", "JARGB_V2_1", "DDR5 DIMM"])

    def test_msi_monitor_is_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "MysticLight.txt"
            log.write_text(SAMPLE_LOG, encoding="utf-8")
            hid = FakeHid(0x0DB0, 0x0076, 0xFF00, 0x01, "MYSTIC LIGHT", "MSI", feature_len=761)
            a = MysticLightMonitor(lambda: [hid], log_path=log, service_query=lambda n: "running")
            [dev] = a.discover()
            self.assertEqual(dev.connection, Connection.MONITOR_ONLY)
            self.assertFalse(dev.caps.writable)
            self.assertEqual(len(dev.caps.zones), 3)
            self.assertTrue(a.health().available)

    def test_inventory(self):
        hids = [BASILISK, FakeHid(0x320F, 0x5055, 0xFF1C, 0x92, "Kreo Hive RGB", "Evision"),
                FakeHid(0x320F, 0x5055, 0x01, 0x06, "Kreo Hive RGB", "Evision")]
        cim = {"gpus": [{"Name": "NVIDIA GeForce RTX 5070 Ti", "PNPDeviceID": "PCI\\VEN_10DE&DEV_2C05&SUBSYS_41A81458&REV_A1\\4"},
                        {"Name": "Parsec Virtual Display Adapter", "PNPDeviceID": "ROOT\\DISPLAY\\0000"}],
               "dimms": [{"PartNumber": "F5-6000J3636F16G", "Capacity": 17179869184}] * 2}
        devs = {d.info.id: d for d in InventoryAdapter(lambda: hids, lambda: cim).discover()}
        self.assertIn("inventory:hid:320F:5055", devs)
        self.assertEqual(devs["inventory:hid:320F:5055"].caps.color, Support.BLOCKED)
        self.assertEqual(devs["inventory:hid:320F:5055"].info.category.value, "keyboard")
        gpus = [d for d in devs.values() if d.info.category.value == "gpu"]
        self.assertEqual(len(gpus), 1, "virtual display adapters are skipped")
        self.assertEqual(gpus[0].info.vendor, "Gigabyte")
        self.assertEqual(devs["inventory:dram"].info.name, "DDR5 memory (2x, 32 GB)")
        self.assertTrue(all(not d.caps.writable for d in devs.values()))


if __name__ == "__main__":
    unittest.main()
