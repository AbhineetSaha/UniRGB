"""The opt-in SMBus helper must stay read-only and inside its address allowlist."""
import unittest
from contextlib import nullcontext
from pathlib import Path

from unirgb_smbus import ene
from unirgb_smbus.bus import ENE_DRAM_ADDRESSES, READ, ReadOnlySmbus
from unirgb_smbus.probe import probe

PKG = Path(__file__).resolve().parents[1] / "unirgb_smbus"


class FakePawn:
    """Answers like a PIIX4 bus with an ENE controller at `ene` and nothing elsewhere."""

    def __init__(self, ene=0x71):
        self.ene, self.calls = ene, []

    def execute(self, name, args, out_size):
        self.calls.append((name, list(args)))
        addr, _rw, command, _proto = args
        if addr != self.ene:
            raise OSError(0xC0000001, "no ack")
        return [command - 0xA0 if 0xA0 <= command <= 0xAF else 0x00]


class ReadOnlyTests(unittest.TestCase):
    def test_probe_finds_ene_and_only_reads(self):
        fake = FakePawn()
        found = probe(ReadOnlySmbus(fake, nullcontext()))
        self.assertEqual([(f["address"], f["ene"]) for f in found], [(0x71, True)])
        self.assertTrue(all(name == "ioctl_smbus_xfer" and args[1] == READ for name, args in fake.calls))
        self.assertTrue(all(args[0] in ENE_DRAM_ADDRESSES for _, args in fake.calls))

    def test_non_ene_signature_is_not_ene(self):
        class Junk(FakePawn):
            def execute(self, name, args, out_size):
                super().execute(name, args, out_size)
                return [0xFF]
        self.assertEqual([f["ene"] for f in probe(ReadOnlySmbus(Junk(), nullcontext()))], [False])

    def test_spd_and_pmic_addresses_are_unreachable(self):
        bus = ReadOnlySmbus(FakePawn(), nullcontext())
        for addr in (0x48, 0x4F, 0x50, 0x57, 0x77 + 1):
            with self.assertRaises(ValueError):
                bus.read_byte(addr)

    def test_package_has_no_write_path(self):
        for p in PKG.rglob("*.py"):
            if p.name == "ene.py":   # the one fenced pointer write; tested in EneReaderTests
                continue
            src = p.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"(?i)smbus_write|I2C_SMBUS_WRITE|def write|WRITE\s*=", p.name)



class FakeEne:
    """An ENE controller at 0x71: a 16-bit register pointer set by a word write to 0x00, read at 0x81."""

    def __init__(self, fail_after=None):
        self.calls, self.pointer, self.fail_after = [], None, fail_after
        self.mem = {0x1000 + i: b for i, b in enumerate(b"AUDA0-E6K5-0101" + bytes(1))}
        self.mem.update({0x1C00 + i: i for i in range(64)})
        self.mem[0x1C02] = 8

    def execute(self, name, args, out_size):
        self.calls.append(list(args))
        if self.fail_after is not None and len(self.calls) > self.fail_after:
            raise OSError(0xC0000001, "no ack")
        addr, rw, cmd, proto, *data = args
        if rw == 0:
            self.pointer = ((data[0] & 0xFF) << 8) | (data[0] >> 8)
            return []
        return [self.mem.get(self.pointer, 0)]


class EneReaderTests(unittest.TestCase):
    def test_identify_reads_name_and_led_count(self):
        fake = FakeEne()
        info = ene.EneReader(fake, nullcontext(), {0x71}).identify(0x71)
        self.assertEqual(info["name"], "AUDA0-E6K5-0101")
        self.assertEqual(info["led_count_candidates"][0], 8)

    def test_the_only_write_is_the_register_pointer_inside_the_read_windows(self):
        fake = FakeEne()
        ene.EneReader(fake, nullcontext(), {0x71}).identify(0x71)
        writes = [c for c in fake.calls if c[1] == 0]
        self.assertEqual(len(writes), 16 + 64)
        for addr, _rw, cmd, proto, data in writes:
            reg = ((data & 0xFF) << 8) | (data >> 8)
            self.assertEqual((addr, cmd, proto), (0x71, ene.POINTER_CMD, 3))
            self.assertTrue(any(reg in w for w in ene.READ_WINDOWS), hex(reg))
        self.assertNotIn(0x01, [c[2] for c in fake.calls], "the value-write command is never sent")

    def test_refuses_unconfirmed_addresses_and_registers_outside_the_windows(self):
        r = ene.EneReader(FakeEne(), nullcontext(), {0x71})
        for addr, reg in ((0x73, 0x1000), (0x50, 0x1000), (0x71, 0x8020), (0x71, 0x80A0), (0x71, 0x1010)):
            with self.assertRaises(ValueError):
                r.read_register(addr, reg)
        with self.assertRaises(ValueError):
            ene.EneReader(FakeEne(), nullcontext(), {0x50})   # an SPD hub can never be "confirmed"

    def test_stops_at_the_first_failure(self):
        fake = FakeEne(fail_after=5)
        self.assertIsNone(ene.EneReader(fake, nullcontext(), {0x71}).identify(0x71))
        self.assertLessEqual(len(fake.calls), 6)


if __name__ == "__main__":
    unittest.main()
