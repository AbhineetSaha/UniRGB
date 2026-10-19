import tempfile
import unittest
from pathlib import Path

from tests.fakes import FakeHid
from unirgb.adapters.msi_direct import MsiDirectAdapter
from unirgb.adapters.razer_direct import RazerDirectAdapter
from unirgb.core.models import Color, Confirmation, Connection, LightingState, Support
from unirgb.protocols import msi761
from unirgb.protocols import razer as rz

RED, GREEN = Color(255, 0, 0), Color(0, 255, 0)


class FakeRazerDev:
    """Answers Razer protocol requests like the Basilisk V3 Pro did on 2026-10-19."""

    def __init__(self, asleep=False):
        self.asleep = asleep
        self.requests: list[bytes] = []
        self.bright = {rz.NOSTORE: 84, rz.VARSTORE: 84}
        self._resp = bytes(91)
        self.closed = False

    def set_feature(self, data):
        req = data[1:91]
        assert req[88] == rz.crc(req), "bad crc"
        self.requests.append(req)
        r = bytearray(req)
        r[0] = 0x04 if self.asleep else 0x02
        cls, cid, args = req[6], req[7], req[8:]
        if (cls, cid) == (0x00, 0x81):
            r[8:10] = bytes([2, 50])
        elif (cls, cid) == (0x0F, 0x04):
            self.bright[args[0]] = args[2]
        elif (cls, cid) == (0x0F, 0x84):
            if args[1] == rz.ZERO_LED:
                r[0] = 0x03            # firmware 2.50 refuses ZERO_LED reads
            r[10] = self.bright[args[0]]
        r[88] = rz.crc(r)
        self._resp = b"\x00" + bytes(r)

    def get_feature(self, rid):
        return self._resp

    def close(self):
        self.closed = True


RAZER_IF0 = FakeHid(0x1532, 0x00AB, 0x01, 0x02, "Razer Basilisk V3 Pro", "Razer", feature_len=91)
RAZER_IF0.interface_number = 0
RAZER_IF0.path = "fake-razer"


class RazerDirectTests(unittest.TestCase):
    def make(self, dev):
        a = RazerDirectAdapter(lambda: [RAZER_IF0], open_device=lambda info: dev, process_provider=lambda: set())
        return a, a.discover()

    def test_protocol_bytes(self):
        r = rz.effect_static(1, 2, 3)
        self.assertEqual((r[1], r[5], r[6], r[7]), (0x1F, 0x09, 0x0F, 0x02))
        self.assertEqual(r[8:17], bytes([rz.NOSTORE, 0, 1, 0, 0, 1, 1, 2, 3]))
        self.assertEqual(r[88], rz.crc(r))
        f = rz.set_custom_frame(0, 0, 12, bytes(39))
        self.assertEqual((f[5], f[10], f[11], f[12]), (0x47, 0, 0, 12))

    def test_discovery_reads_firmware(self):
        a, [d] = self.make(FakeRazerDev())
        self.assertEqual(d.connection, Connection.CONNECTED)
        self.assertIn("firmware v2.50", " ".join(d.info.evidence))

    def test_asleep_is_unavailable(self):
        a, [d] = self.make(FakeRazerDev(asleep=True))
        self.assertEqual(d.connection, Connection.UNAVAILABLE)

    def test_static_uses_nostore_and_reads_back(self):
        dev = FakeRazerDev()
        a, [d] = self.make(dev)
        r = a.apply(d.info.id, LightingState(color=RED, brightness=40))
        self.assertTrue(r.ok, r.message)
        self.assertEqual(r.confirmation, Confirmation.DEVICE_ACK)
        self.assertEqual(dev.bright[rz.NOSTORE], 102)
        self.assertEqual(dev.bright[rz.VARSTORE], 84, "saved profile untouched")
        writes = [q for q in dev.requests if q[7] in (0x02, 0x03, 0x04)]
        self.assertTrue(all(q[8] == rz.NOSTORE for q in writes if q[7] != 0x03))

    def test_zones_frame(self):
        dev = FakeRazerDev()
        a, [d] = self.make(dev)
        self.assertTrue(a.apply(d.info.id, LightingState(color=GREEN, zones={"logo": RED})).ok)
        frame = next(q for q in dev.requests if q[7] == 0x03)
        rgb = frame[13:13 + 39]
        self.assertEqual(rgb[3:6], bytes((255, 0, 0)), "column 1 = logo")
        self.assertEqual(rgb[0:3], bytes((0, 255, 0)))

    def test_restore_copies_saved_brightness(self):
        dev = FakeRazerDev()
        a, [d] = self.make(dev)
        a.apply(d.info.id, LightingState(color=RED, brightness=100))
        self.assertTrue(a.restore(d.info.id).ok)
        self.assertEqual(dev.bright[rz.NOSTORE], 84)


class FakeMsiDev:
    def __init__(self, setup):
        self.setup = setup
        self.sent: list[bytes] = []

    def get_feature(self, rid):
        return self.setup + bytes(761 - len(self.setup))

    def set_feature(self, data):
        self.sent.append(bytes(data))

    def close(self):
        pass


def msi_baseline():
    b = bytearray(msi761.SETUP_LEN)
    b[0] = 0x50
    for i in range(4):
        b[1 + 16 * i] = 0x02
        b[1 + 16 * i + 14] = 0xB5
        b[1 + 16 * i + 15] = 30
    return bytes(b)


MSI_HID = FakeHid(0x0DB0, 0x0076, 0xFF00, 0x01, "MYSTIC LIGHT", "MSI", feature_len=761)
MSI_HID.path = "fake-msi"


class MsiDirectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name) / "b.bin"
        self.dev = FakeMsiDev(msi_baseline())
        self.procs = set()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, board="X870E GAMING PLUS WIFI (MS-7E70)"):
        a = MsiDirectAdapter(lambda: [MSI_HID], open_device=lambda i: self.dev, process_provider=lambda: self.procs,
                             board_provider=lambda: board, baseline_path=self.base)
        return a, a.discover()

    def test_decode_and_counts(self):
        self.assertEqual(msi761.led_counts_from(msi_baseline()), {"jargb1": 30, "jargb2": 30, "jargb3": 30, "jaf": 30})
        self.assertEqual(set(msi761.decode_setup(msi_baseline())), {"JARGB1", "JARGB2", "JARGB3", "JAF"})

    def test_blocked_while_msi_center_runs(self):
        self.procs = {"ledkeeper2.exe"}
        a, [d] = self.make()
        self.assertEqual(d.caps.color, Support.BLOCKED)
        self.assertFalse(a.apply(d.info.id, LightingState(color=RED)).ok)
        self.assertEqual(self.dev.sent, [])

    def test_blocked_on_untested_board(self):
        a, [d] = self.make(board="SOME OTHER BOARD (MS-0000)")
        self.assertEqual(d.caps.color, Support.BLOCKED)

    def test_baseline_saved_before_write_and_restored(self):
        a, [d] = self.make()
        self.assertEqual(self.base.read_bytes(), msi_baseline())
        r = a.apply(d.info.id, LightingState(color=RED, brightness=50, zones={"jaf": GREEN}))
        self.assertTrue(r.ok, r.message)
        setup, *zones = self.dev.sent
        self.assertEqual(setup[0], 0x50)
        self.assertEqual(setup[1 + 15], 30, "LED count from MSI baseline")
        self.assertTrue(all(b == 0 for b in setup[1 + 16 * 4:]), "rows 4.. off as in OpenRGB")
        self.assertEqual([z[:4] for z in zones], [bytes([0x51, 9, 4, 0]), bytes([0x51, 9, 4, 1]),
                                                   bytes([0x51, 9, 4, 2]), bytes([0x51, 9, 8, 0])])
        self.assertEqual(zones[0][6], 30)
        self.assertEqual(zones[0][7:10], bytes((128, 0, 0)), "brightness scales colors")
        self.assertEqual(zones[3][7:10], bytes((0, 128, 0)), "zone override")
        self.assertTrue(a.restore(d.info.id).ok)
        self.assertEqual(self.dev.sent[-1], msi_baseline())

    def test_rediscovery_never_overwrites_first_baseline(self):
        a, [d] = self.make()
        a.apply(d.info.id, LightingState(color=RED))
        self.dev.setup = msi761.build_direct_setup({"jargb1": 30})
        a.discover()
        self.assertEqual(self.base.read_bytes(), msi_baseline())


if __name__ == "__main__":
    unittest.main()
