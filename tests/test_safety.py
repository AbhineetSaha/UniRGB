"""Guards for user-imposed safety rules. Fails the build if they are violated."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "unirgb"
# primitives that could reach a DIMM's SMBus (SPD / RGB hub)
FORBIDDEN = re.compile(r"Smbus(PIIX4|I801|NCT)|smbus_write|i2c_smbus|WriteByteData|pawnio_load.*smbus|SB_SMBUS|EneIo", re.I)


class RamNoWriteRule(unittest.TestCase):
    def test_no_smbus_write_paths(self):
        hits = []
        for p in ROOT.rglob("*.py"):
            for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if FORBIDDEN.search(line) and not line.lstrip().startswith("#"):
                    hits.append(f"{p.relative_to(ROOT)}:{i}: {line.strip()}")
        self.assertEqual(hits, [], "RAM must never be written (user rule). Offending lines:\n" + "\n".join(hits))

    def test_dram_entry_is_read_only(self):
        from unirgb.adapters.inventory import InventoryAdapter
        devs = InventoryAdapter(lambda: [], lambda: {"dimms": [{"PartNumber": "F5-6000J3636F16G", "Capacity": 1}]}).discover()
        dram = next(d for d in devs if d.info.id == "inventory:dram")
        self.assertFalse(dram.caps.writable)


if __name__ == "__main__":
    unittest.main()
