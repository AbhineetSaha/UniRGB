"""Integration tests against this machine's real hardware.

* Read-only discovery tests run whenever on Windows.
* Tests that change lighting run only with UNIRGB_HW_WRITE=1. They use the official
  Chroma SDK and always end the session afterwards, which hands lighting back to Synapse.
"""
import os
import sys
import time
import unittest

from unirgb.adapters.razer_chroma import RazerChromaAdapter
from unirgb.app import App, HidCache
from unirgb.core.models import Color, LightingState
from unirgb.hostos.windows_hid import enumerate_hid

WIN = sys.platform == "win32"
WRITE = os.environ.get("UNIRGB_HW_WRITE") == "1"


@unittest.skipUnless(WIN, "Windows only")
class HardwareDiscovery(unittest.TestCase):
    def test_hid_enumeration_is_query_only_and_finds_devices(self):
        items = enumerate_hid()
        self.assertGreater(len(items), 0)
        self.assertTrue(any(i.usage_page is not None for i in items))

    def test_full_discovery_no_adapter_crashes(self):
        app = App(rescan_interval=999)
        try:
            app.rescan(full=True)
            health = app.orch.health()
            self.assertEqual(set(health), {"cooler", "kreo-hid", "razer-hid", "msi-hid", "razer", "openrgb", "msi", "inventory"})
            self.assertTrue(all(not h.detail.startswith("discovery failed") for h in health.values()), health)
        finally:
            app.shutdown()


@unittest.skipUnless(WIN and WRITE, "set UNIRGB_HW_WRITE=1 to change real lighting")
class HardwareChromaWrite(unittest.TestCase):
    def test_static_zone_restore_cycle(self):
        hid = HidCache()
        hid.refresh()
        a = RazerChromaAdapter(hid.get)
        try:
            if not a.health().available:
                self.skipTest("Chroma SDK not running")
            mice = [d.info.id for d in a.discover() if d.info.category.value == "mouse"]
            if not mice:
                self.skipTest("no Razer mouse present")
            m = mice[0]
            for st in (LightingState(color=Color(0, 255, 0)),
                       LightingState(color=Color(0, 0, 60), zones={"logo": Color(255, 255, 255)}),
                       LightingState(mode="off")):
                r = a.apply(m, st)
                self.assertTrue(r.ok, r.message)
                time.sleep(1)
        finally:
            r = a.restore("razer:chromalink")
            self.assertTrue(r.ok)


if __name__ == "__main__":
    unittest.main()
