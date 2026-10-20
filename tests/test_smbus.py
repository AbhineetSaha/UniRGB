"""The opt-in SMBus helper must stay read-only and inside its address allowlist."""
import unittest
from contextlib import nullcontext
from pathlib import Path

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
            src = p.read_text(encoding="utf-8")
            self.assertNotRegex(src, r"(?i)smbus_write|I2C_SMBUS_WRITE|def write|WRITE\s*=", p.name)


if __name__ == "__main__":
    unittest.main()
