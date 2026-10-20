import tempfile
import threading
import unittest
from pathlib import Path

from unirgb.adapters.simulated import SimulatedAdapter
from unirgb.core.adapter import AdapterHealth, DeviceAdapter, DiscoveredDevice
from unirgb.core.models import (Capabilities, Category, Color, Connection, DeviceInfo, LightingState, Support)
from unirgb.core.orchestrator import Orchestrator
from unirgb.core.scenes import SceneStore

RED, BLUE = Color(255, 0, 0), Color(0, 0, 255)


class ModelTests(unittest.TestCase):
    def test_color_parse(self):
        self.assertEqual(Color.parse("#ff8000"), Color(255, 128, 0))
        self.assertEqual(Color.parse("00ff00"), Color(0, 255, 0))
        self.assertEqual(Color.parse([1, 2, 3]), Color(1, 2, 3))
        for bad in ("#ff", "zzzzzz", [1, 2], 5):
            with self.assertRaises(ValueError):
                Color.parse(bad)
        with self.assertRaises(ValueError):
            Color(256, 0, 0)

    def test_scaled(self):
        self.assertEqual(Color(200, 100, 0).scaled(50), Color(100, 50, 0))
        self.assertEqual(Color(200, 100, 0).scaled(0), Color(0, 0, 0))

    def test_state_roundtrip_and_validation(self):
        s = LightingState(color=RED, brightness=40, zones={"a": BLUE})
        self.assertEqual(LightingState.from_dict(s.to_dict()).to_dict(), s.to_dict())
        for bad in ({"brightness": 101}, {"brightness": "x"}, {"zones": []}, None):
            with self.assertRaises(ValueError):
                LightingState.from_dict(bad)


def make(adapters=None, **kw):
    sim = SimulatedAdapter()
    o = Orchestrator(adapters or [sim], **kw)
    o.discover_all()
    return o, sim


class OrchestratorTests(unittest.TestCase):
    def tearDown(self):
        if hasattr(self, "o"):
            self.o.shutdown()

    def test_apply_and_readback(self):
        self.o, sim = make()
        r = self.o.apply("sim:strip", LightingState(color=RED, zones={"a": BLUE}))
        self.assertTrue(r.ok, r.message)
        rec = self.o.registry.get("sim:strip")
        self.assertEqual(rec.confirmed.zones["a"], BLUE)
        self.assertEqual(sim.read_state("sim:strip").color, RED)

    def test_validation(self):
        self.o, _ = make()
        cases = [
            ("sim:strip", LightingState(mode="rainbow", color=RED), "not supported"),
            ("sim:strip", LightingState(color=None), "needs a color"),
            ("sim:strip", LightingState(color=RED, zones={"zz": RED}), "unknown zone"),
            ("sim:fan", LightingState(color=RED, zones={"a": RED}), "per-zone"),
            ("nope", LightingState(color=RED), "unknown device"),
        ]
        for dev, st, msg in cases:
            r = self.o.apply(dev, st)
            self.assertFalse(r.ok)
            self.assertIn(msg, r.message)

    def test_read_only_device_rejected(self):
        class RO(DeviceAdapter):
            name = "ro"
            def health(self): return AdapterHealth(True)
            def discover(self):
                return [DiscoveredDevice(DeviceInfo("ro:x", "x", Category.OTHER, "ro"),
                                         Capabilities(color=Support.BLOCKED), Connection.MONITOR_ONLY)]
        self.o, _ = make([RO()])
        r = self.o.apply("ro:x", LightingState(color=RED))
        self.assertFalse(r.ok)

    def test_coalescing_latest_wins(self):
        sim = SimulatedAdapter(delay=0.05)
        self.o = Orchestrator([sim])
        self.o.discover_all()
        for i in range(50):
            self.o.apply("sim:fan", LightingState(color=Color(i, 0, 0)), wait=False)
        r = self.o.apply("sim:fan", LightingState(color=BLUE))
        self.assertTrue(r.ok)
        self.assertLess(len(sim.apply_log), 6, "queued writes should collapse")
        self.assertEqual(sim.apply_log[-1][1].color, BLUE)

    def test_adapter_exception_isolated(self):
        sim = SimulatedAdapter()
        other = SimulatedAdapter()
        other.name = "sim2"
        orig = other.discover
        other.discover = lambda: [DiscoveredDevice(DeviceInfo(d.info.id.replace("sim:", "sim2:"), d.info.name,
                                  d.info.category, "sim2"), d.caps) for d in orig()]
        self.o = Orchestrator([sim, other])
        self.o.discover_all()
        sim.raise_next = True
        r = self.o.apply("sim:fan", LightingState(color=RED))
        self.assertFalse(r.ok)
        self.assertIn("adapter error", r.message)
        self.assertTrue(self.o.apply("sim2:fan", LightingState(color=RED)).ok)
        self.assertTrue(self.o.apply("sim:fan", LightingState(color=RED)).ok, "adapter recovers")

    def test_discovery_exception_isolated(self):
        class Boom(DeviceAdapter):
            name = "boom"
            def health(self): return AdapterHealth(True)
            def discover(self): raise RuntimeError("kaput")
        self.o = Orchestrator([Boom(), SimulatedAdapter()])
        health = self.o.discover_all()
        self.assertFalse(health["boom"].available)
        self.assertIsNotNone(self.o.registry.get("sim:fan"))

    def test_timeout(self):
        sim = SimulatedAdapter(delay=0.5)
        self.o = Orchestrator([sim], op_timeout=0.1)
        self.o.discover_all()
        r = self.o.apply("sim:fan", LightingState(color=RED))
        self.assertFalse(r.ok)
        self.assertIn("timed out", r.message)

    def test_circuit_breaker(self):
        self.o, sim = make()
        sim.fail_next = 3
        for _ in range(3):
            self.assertFalse(self.o.apply("sim:fan", LightingState(color=RED)).ok)
        r = self.o.apply("sim:fan", LightingState(color=RED))
        self.assertIn("paused", r.message)
        self.o._breakers["sim"].open_until = 0
        self.assertTrue(self.o.apply("sim:fan", LightingState(color=RED)).ok)

    def test_disconnect_and_reconnect(self):
        self.o, sim = make()
        self.o.apply("sim:fan", LightingState(color=RED))
        sim.connected = False
        self.o.discover_all()
        self.assertEqual(self.o.registry.get("sim:fan").connection, Connection.UNAVAILABLE)
        self.assertFalse(self.o.apply("sim:fan", LightingState(color=RED)).ok)
        sim.connected = True
        self.o.discover_all()
        rec = self.o.registry.get("sim:fan")
        self.assertEqual(rec.connection, Connection.CONNECTED)
        self.assertEqual(rec.desired.color, RED, "desired state survives reconnect")

    def test_shadowing_prefers_writable_then_priority(self):
        class Mirror(DeviceAdapter):
            name, priority = "mirror", 5
            def __init__(self, writable): self.writable = writable
            def health(self): return AdapterHealth(True)
            def discover(self):
                caps = Capabilities(color=Support.SUPPORTED if self.writable else Support.BLOCKED, effects=["static"])
                return [DiscoveredDevice(DeviceInfo("mirror:fan", "m", Category.OTHER, "mirror", physical_key="sim:fan"), caps)]
        self.o = Orchestrator([SimulatedAdapter(), Mirror(writable=False)])
        self.o.discover_all()
        self.assertEqual(self.o.registry.get("mirror:fan").shadowed_by, "sim:fan")
        self.o.shutdown()
        self.o = Orchestrator([SimulatedAdapter(), Mirror(writable=True)])
        self.o.discover_all()
        self.assertEqual(self.o.registry.get("sim:fan").shadowed_by, "mirror:fan")
        r = self.o.apply("sim:fan", LightingState(color=RED))
        self.assertIn("controlled through", r.message)

    def test_concurrent_writers(self):
        self.o, sim = make()
        errors = []
        def worker(n):
            for i in range(25):
                r = self.o.apply("sim:strip" if n % 2 else "sim:fan", LightingState(color=Color(n, i, 0)))
                if not r.ok:
                    errors.append(r.message)
        ts = [threading.Thread(target=worker, args=(n,)) for n in range(8)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        self.assertEqual(errors, [])

    def test_restore_clears_state(self):
        self.o, sim = make()
        self.o.apply("sim:fan", LightingState(color=RED))
        self.assertTrue(self.o.restore("sim:fan").ok)
        rec = self.o.registry.get("sim:fan")
        self.assertIsNone(rec.desired)
        self.assertIsNone(sim.read_state("sim:fan"))


class SceneTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.path = Path(self.dir.name) / "scenes.json"

    def tearDown(self):
        self.dir.cleanup()

    def test_roundtrip_and_backup(self):
        s = SceneStore(self.path)
        s.put("Night", {"sim:fan": LightingState(color=BLUE, brightness=20)})
        s.put("Day", {"sim:fan": LightingState(color=RED)})
        self.assertTrue(self.path.with_suffix(".json.bak").exists())
        s2 = SceneStore(self.path)
        self.assertEqual(s2.list()["Night"]["sim:fan"].brightness, 20)
        self.assertTrue(s2.delete("Day"))
        self.assertNotIn("Day", SceneStore(self.path).list())

    def test_bad_names_and_empty(self):
        s = SceneStore(self.path)
        for bad in ("", "a/b", "x" * 60, "<script>"):
            with self.assertRaises(ValueError):
                s.put(bad, {"sim:fan": LightingState(color=RED)})
        with self.assertRaises(ValueError):
            s.put("ok", {})

    def test_corrupt_file_is_never_overwritten(self):
        self.path.write_text("{not json", encoding="utf-8")
        s = SceneStore(self.path)
        self.assertIsNotNone(s.load_error)
        s.put("x", {"sim:fan": LightingState(color=RED)})
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{not json")

    def test_import_export_apply(self):
        s = SceneStore(self.path)
        s.put("A", {"sim:fan": LightingState(color=RED), "sim:strip": LightingState(color=BLUE)})
        exported = s.serialize()
        other = SceneStore(Path(self.dir.name) / "o.json")
        self.assertEqual(other.import_json(exported), ["A"])
        with self.assertRaises(ValueError):
            other.import_json('{"version": 99, "scenes": {}}')
        o, sim = make()
        try:
            res = other.apply("A", o)
            self.assertTrue(all(r.ok for r in res.values()))
            self.assertEqual(sim.read_state("sim:strip").color, BLUE)
        finally:
            o.shutdown()


if __name__ == "__main__":
    unittest.main()
