"""RAM lighting in the app: adapter -> helper requests -> RamService -> ENE fences -> virtual sticks (Device Lab)."""
import unittest
from contextlib import nullcontext

from devlab.virtual_smbus import VirtualEne, VirtualPiix4
from unirgb.adapters.ram_ene import RamEneAdapter
from unirgb.core.models import Color, Connection, LightingState
from unirgb.hardware_helper import Handler
from unirgb_smbus.service import RamService


def rig(controllers=None, enabled=True):
    bus = VirtualPiix4(controllers if controllers is not None else {0x71: VirtualEne(), 0x73: VirtualEne()})
    handler = Handler(None, "test", lambda: RamService(bus, nullcontext()))
    started = []
    adapter = RamEneAdapter(enabled=lambda: enabled, start_helper=lambda: started.append(1), request=handler)
    return bus, handler, adapter, started


def trips(bus):
    return [t for t in bus.trace if t["level"] == "trip"]


class EndToEnd(unittest.TestCase):
    def test_two_sticks_are_found_colored_and_handed_back(self):
        bus, _, a, _ = rig()
        devs = a.discover()
        self.assertEqual([d.info.id for d in devs], ["ram:0x71", "ram:0x73"])
        self.assertEqual({d.connection for d in devs}, {Connection.CONNECTED})
        r = a.apply("ram:0x71", LightingState(color=Color(0, 255, 0), brightness=50))
        self.assertTrue(r.ok, r.message)
        self.assertEqual(bus.controllers[0x71].leds(), ["#008000"] * 8, "brightness scales the color")
        self.assertEqual(bus.controllers[0x73].leds(), ["#ff7800"] * 8, "the other stick is untouched")
        a.shutdown()   # quit
        self.assertEqual(bus.controllers[0x71].leds(), ["#ff7800"] * 8, "back to its stored effect")
        self.assertFalse(any(c.saved for c in bus.controllers.values()))
        self.assertEqual(trips(bus), [])

    def test_off_is_black_in_direct_mode(self):
        bus, _, a, _ = rig()
        a.discover()
        self.assertTrue(a.apply("ram:0x73", LightingState(mode="off")).ok)
        self.assertEqual(bus.controllers[0x73].leds(), ["#000000"] * 8)

    def test_disabled_in_settings_means_no_requests_at_all(self):
        bus, _, a, started = rig(enabled=False)
        self.assertEqual(a.discover(), [])
        self.assertEqual((bus.trace, started), ([], []))

    def test_helper_not_running_is_started(self):
        a = RamEneAdapter(enabled=lambda: True, start_helper=lambda: started.append(1), request=lambda req: None)
        started = []
        self.assertEqual(a.discover(), [])
        self.assertEqual(started, [1])

    def test_unremapped_controllers_at_0x77_are_never_used(self):
        bus, handler, a, _ = rig({0x77: VirtualEne()})
        self.assertEqual(a.discover(), [])
        self.assertIn("0x77", handler({"op": "ram_list"})["problem"])
        self.assertFalse([t for t in bus.trace if t["args"][1] == 0], "nothing written at all")


class HelperRequests(unittest.TestCase):
    def test_bad_requests_are_refused_before_the_bus(self):
        bus, h, _, _ = rig()
        h({"op": "ram_list"})
        writes_before = len([t for t in bus.trace if t["args"][1] == 0])
        for req in ({"op": "ram_set", "address": 0x50, "color": "#ff0000"},     # SPD hub
                    {"op": "ram_set", "address": 0x72, "color": "#ff0000"},     # no stick there
                    {"op": "ram_set", "address": "0x71", "color": "#ff0000"},   # not an int
                    {"op": "ram_set", "address": True, "color": "#ff0000"},
                    {"op": "ram_set", "address": 0x71, "color": "red"},
                    {"op": "ram_save", "address": 0x71}):                        # no such request
            self.assertFalse(h(req)["ok"], req)
        self.assertEqual(len([t for t in bus.trace if t["args"][1] == 0]), writes_before)
        self.assertEqual(trips(bus), [])

    def test_cpu_temperature_unavailable_does_not_break_ram(self):
        _, h, _, _ = rig()
        self.assertFalse(h({"op": "cpu_temp"})["ok"])
        self.assertEqual(len(h({"op": "ram_list"})["sticks"]), 2)


if __name__ == "__main__":
    unittest.main()
