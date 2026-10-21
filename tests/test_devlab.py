"""The Device Lab's virtual ENE sticks, driven by unirgb_smbus's real code."""
import unittest
from contextlib import nullcontext

from devlab.__main__ import Lab
from devlab.virtual_smbus import Tripwire, VirtualEne, VirtualPiix4
from unirgb_smbus import ene
from unirgb_smbus.bus import ReadOnlySmbus
from unirgb_smbus.probe import probe


def lighting(bus):
    confirmed = {f["address"] for f in probe(ReadOnlySmbus(bus, nullcontext())) if f["ene"]}
    return ene.EneLighting(ene.EneReader(bus, nullcontext(), confirmed))


class StepTwoRehearsal(unittest.TestCase):
    def test_shows_the_color_then_hands_back_without_saving(self):
        bus = VirtualPiix4({0x71: VirtualEne(), 0x73: VirtualEne()})
        stick, seen = bus.controllers[0x71], []
        result = ene.color_test(lighting(bus), 0x71, (255, 0, 0), hold_s=0, sleep=lambda s: seen.append(stick.leds()))
        self.assertEqual(result, "shown, then handed back")
        self.assertEqual(seen, [["#ff0000"] * 8])
        self.assertEqual(stick.leds(), ["#ff7800"] * 8, "back to its stored effect")
        self.assertFalse(stick.saved)
        self.assertEqual([t for t in bus.trace if t["level"] == "trip"], [])
        self.assertTrue(all(t["addr"] in ("0x71", "0x73") for t in bus.trace if t["args"][1] == 0),
                        "writes only ever go to the ENE controllers")
        self.assertEqual(bus.controllers[0x73].leds(), ["#ff7800"] * 8, "the other stick is untouched")

    def test_hands_back_when_the_stick_stops_answering_midway(self):
        bus = VirtualPiix4({0x71: VirtualEne()})
        L = lighting(bus)

        def unplug(_):
            bus.controllers.pop(0x71)
        self.assertTrue(ene.color_test(L, 0x71, hold_s=0, sleep=unplug).startswith("could not switch direct mode off"),
                        "a failed handback is reported, never claimed as done")

    def test_a_failed_color_write_still_switches_direct_mode_off(self):
        class FlakyColors(VirtualEne):
            def _write(self, reg, v):
                if reg == ene.COLORS_REG + 5:
                    raise OSError(0xC00000B5, "bus error")
                return super()._write(reg, v)
        bus = VirtualPiix4({0x71: FlakyColors()})
        self.assertIn("switched off again", ene.color_test(lighting(bus), 0x71, hold_s=0))
        self.assertFalse(bus.controllers[0x71].direct_active)

    def test_a_failed_recheck_writes_nothing(self):
        bus = VirtualPiix4({0x71: VirtualEne()})
        L = lighting(bus)
        L.verify(0x71)
        bus.busy_for = 1   # the re-check inside color_test fails
        self.assertIn("nothing written", ene.color_test(L, 0x71, hold_s=0))
        self.assertFalse([t for t in bus.trace if t["args"][1:3] == [0, ene.VALUE_WRITE_CMD]], "no value writes")

    def test_a_busy_bus_never_raises_or_trips(self):
        bus = VirtualPiix4({0x71: VirtualEne()})
        L = lighting(bus)
        bus.busy_for = 3
        self.assertIsNone(L.verify(0x71), "identification stops at the first failed transfer")
        self.assertEqual([t for t in bus.trace if t["level"] == "trip"], [])


class LabSafetyChecks(unittest.TestCase):
    def test_forbidden_actions_are_blocked_by_unirgb_and_the_tripwire_works(self):
        lab = Lab()
        self.assertTrue(lab.run("try-save").startswith("BLOCKED"))
        self.assertTrue(lab.run("try-spd").startswith("BLOCKED"))
        self.assertTrue(lab.run("check-tripwire").startswith("TRIPWIRE"))
        self.assertFalse(any(d.saved for d in lab.bus.controllers.values()))

    def test_the_virtual_stick_trips_on_a_save_or_an_undocumented_register(self):
        stick = VirtualEne()
        stick.pointer = ene.APPLY_REG
        with self.assertRaises(Tripwire):
            stick.xfer(0, 0x01, 2, [0xAA])
        stick.pointer = 0x8021   # mode register: no supported flow writes it
        with self.assertRaises(Tripwire):
            stick.xfer(0, 0x01, 2, [0x01])


if __name__ == "__main__":
    unittest.main()
