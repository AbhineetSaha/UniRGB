import unittest

from tests.fakes import FakeHid
from unirgb.adapters.kreo_direct import KreoDirectAdapter
from unirgb.core.models import Color, LightingState
from unirgb.protocols import evision_v2 as ev


class FakeKeyboard:
    """Echoes Evision V2 requests like the Kreo Hive RGB did on 2026-10-19."""

    def __init__(self, bad_echo=False):
        self.sent: list[bytes] = []
        self.bad_echo = bad_echo
        self._resp = b""

    def write(self, data):
        self.sent.append(bytes(data))
        r = bytearray(data)
        if data[3] == ev.READ_CAPABILITIES:
            r[8:15] = bytes([0xAA, 0x55, 0, 0, 0x0D, 0x80, 0x50])   # map_size 0x80 = 128 slots
        if self.bad_echo:
            r[1] ^= 0xFF
        self._resp = bytes(r)

    def read(self, timeout_ms=0):
        return self._resp

    def close(self):
        pass


HID = FakeHid(0x320F, 0x5055, 0xFF1C, 0x92, "Kreo Hive RGB", "Evision")
HID.output_len = 64
HID.path = "fake-kreo"


class ProtocolTests(unittest.TestCase):
    def test_frame_and_checksum(self):
        b = ev.build(ev.SEND_DYNAMIC_COLORS, 0x0138, 3, b"\x01\x02\x03")
        self.assertEqual((b[0], b[3], b[4], b[5], b[6]), (4, 0x12, 3, 0x38, 0x01))
        self.assertEqual(b[1] | (b[2] << 8), sum(b[3:]) & 0xFFFF)

    def test_profile_writes_are_impossible(self):
        for cmd in (0x01, 0x02, 0x06, 0x0B):
            with self.assertRaises(ev.EvisionError):
                ev.build(cmd)

    def test_bad_echo_is_rejected(self):
        with self.assertRaises(ev.EvisionError):
            ev.EvisionTransport(FakeKeyboard(bad_echo=True)).query(ev.READ_CONFIG, 0, 1)


class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.kb = FakeKeyboard()
        self.a = KreoDirectAdapter(lambda: [HID], open_device=lambda i: self.kb, keepalive_s=60)
        [self.dev] = self.a.discover()

    def tearDown(self):
        self.a.shutdown()

    def test_static_color_fills_all_slots_in_seven_packets(self):
        self.kb.sent.clear()
        self.assertTrue(self.a.apply(self.dev.info.id, LightingState(color=Color(10, 20, 30), brightness=50)).ok)
        self.assertEqual(len(self.kb.sent), 7)                      # 128 slots * 3 bytes / 56 per packet
        self.assertTrue(all(p[3] == ev.SEND_DYNAMIC_COLORS for p in self.kb.sent))
        self.assertEqual(self.kb.sent[0][8:11], bytes((5, 10, 15)))  # brightness scales the color

    def test_restore_ends_direct_mode(self):
        self.a.apply(self.dev.info.id, LightingState(color=Color(255, 0, 0)))
        self.assertTrue(self.a.restore(self.dev.info.id).ok)
        self.assertEqual(self.kb.sent[-1][3], ev.END_DYNAMIC_COLORS)


if __name__ == "__main__":
    unittest.main()
