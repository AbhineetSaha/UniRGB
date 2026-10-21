import hashlib
import importlib.util
import io
import unittest
from pathlib import Path

_spec = importlib.util.spec_from_file_location("fetch_pawnio", Path(__file__).resolve().parents[1] / "tools" / "fetch_pawnio.py")
fetch_pawnio = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fetch_pawnio)


class FetchTests(unittest.TestCase):
    def test_hash_is_enforced(self):
        opener = lambda url, timeout: io.BytesIO(b"payload")
        good = hashlib.sha256(b"payload").hexdigest()
        self.assertEqual(fetch_pawnio.fetch("u", good, urlopen=opener), b"payload")
        with self.assertRaises(SystemExit):
            fetch_pawnio.fetch("u", "0" * 64, urlopen=opener)

    def test_bundle_layout_matches_what_setup_reads(self):
        from unirgb.system_setup import bundle_dir
        self.assertEqual(bundle_dir(Path("app/UniRGB.exe")).name, fetch_pawnio.OUT.name)


if __name__ == "__main__":
    unittest.main()
