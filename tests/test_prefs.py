import json
import tempfile
import unittest
from pathlib import Path

from unirgb.prefs import PrefsStore


class PrefsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "prefs.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_ask_again_and_need_no_driver(self):
        p = PrefsStore(self.path).prefs
        self.assertFalse(p.setup_done or p.needs_driver)

    def test_saved_choices_survive_a_restart(self):
        PrefsStore(self.path).update({"setup_done": True, "cpu_temperature": True})
        p = PrefsStore(self.path).prefs
        self.assertTrue(p.setup_done and p.cpu_temperature and p.needs_driver)

    def test_corrupt_or_tampered_file_falls_back_to_defaults(self):
        self.path.write_text("{not json", encoding="utf-8")
        self.assertFalse(PrefsStore(self.path).prefs.setup_done)
        self.path.write_text(json.dumps({"cpu_temperature": "yes", "admin": True}), encoding="utf-8")
        self.assertFalse(PrefsStore(self.path).prefs.cpu_temperature)

    def test_rejected_update_changes_nothing(self):
        s = PrefsStore(self.path)
        for bad in ({"ram_lighting": True}, {"admin": True}, {"cpu_temperature": 1}, ["setup_done"]):
            with self.assertRaises(ValueError):
                s.update(bad)
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
