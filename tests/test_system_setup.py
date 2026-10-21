import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from unirgb import system_setup as ss

SID = "S-1-5-21-1111111111-2222222222-3333333333-1001"


class FakeRun:
    def __init__(self, rc=None):
        self.calls, self.rc = [], rc or {}

    def __call__(self, cmd):
        self.calls.append(cmd)
        key = "pawnio" if cmd[0].endswith("PawnIO_setup.exe") else cmd[1]
        return SimpleNamespace(returncode=self.rc.get(key, 0), stdout="", stderr="")


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.app = root / "app"
        (self.app / "pawnio" / "modules").mkdir(parents=True)
        self.exe = self.app / "UniRGB.exe"
        self.exe.write_bytes(b"exe")
        (self.app / "pawnio" / "PawnIO_setup.exe").write_bytes(b"setup")
        (self.app / "pawnio" / "modules" / "SmbusPIIX4.bin").write_bytes(b"mod")
        self.dst = root / "Program Files" / "UniRGB Hardware Helper"

    def tearDown(self):
        self.tmp.cleanup()

    def test_task_xml_runs_the_protected_copy_elevated_without_triggers(self):
        x = ss.task_xml(SID, Path(r"C:\Program Files\UniRGB Hardware Helper\UniRGB.exe"))
        self.assertIn("<RunLevel>HighestAvailable</RunLevel>", x)
        self.assertIn(f"<UserId>{SID}</UserId>", x)
        self.assertIn(f"<Arguments>{ss.HELPER_ARG}</Arguments>", x)
        self.assertNotIn("Trigger", x)
        self.assertIn("Program Files", x)

    def test_bad_sid_is_rejected(self):
        for bad in ("", "S-1-5-18", "S-1-5-21-1-2-3-4 & calc", "x"):
            with self.assertRaises(ValueError):
                ss.task_xml(bad, self.exe)

    def test_enable_installs_pawnio_when_missing_and_registers_task(self):
        run, states = FakeRun(), iter(["not-installed", "running"])
        steps = ss.enable(SID, self.exe, run=run, driver=lambda: next(states), dst=self.dst)
        self.assertEqual(run.calls[0][1:], ["-install", "-silent"])
        self.assertEqual(run.calls[1][:2], ["schtasks", "/create"])
        self.assertTrue((self.dst / "UniRGB.exe").is_file() and (self.dst / "modules" / "SmbusPIIX4.bin").is_file())
        self.assertIn("installed PawnIO", steps[0])

    def test_enable_skips_installer_when_driver_present(self):
        run = FakeRun()
        ss.enable(SID, self.exe, run=run, driver=lambda: "running", dst=self.dst)
        self.assertFalse(any(c[0].endswith("PawnIO_setup.exe") for c in run.calls))

    def test_failed_driver_install_stops_before_copying(self):
        with self.assertRaises(RuntimeError):
            ss.enable(SID, self.exe, run=FakeRun({"pawnio": 1603}), driver=lambda: "not-installed", dst=self.dst)
        self.assertFalse((self.dst / "UniRGB.exe").exists())

    def test_disable_removes_only_its_own_files(self):
        ss.enable(SID, self.exe, run=FakeRun(), driver=lambda: "running", dst=self.dst)
        (self.dst / "someone-elses.txt").write_text("keep")
        run = FakeRun()
        ss.disable(run=run, dst=self.dst)
        self.assertEqual([c[:2] for c in run.calls], [["schtasks", "/end"], ["schtasks", "/delete"]],
                         "the running helper is ended before its files are deleted")
        self.assertFalse((self.dst / "UniRGB.exe").exists())
        self.assertTrue((self.dst / "someone-elses.txt").exists())

    def test_disable_leaves_no_folder_behind(self):
        ss.enable(SID, self.exe, run=FakeRun(), driver=lambda: "running", dst=self.dst)
        (self.dst / "helper.log").write_text("log")
        ss.disable(run=FakeRun(), dst=self.dst)
        self.assertFalse(self.dst.exists())

    def test_status_flags_an_app_update_as_stale(self):
        ss.enable(SID, self.exe, run=FakeRun(), driver=lambda: "running", dst=self.dst)
        st = ss.status(self.exe, run=FakeRun(), dst=self.dst)
        self.assertFalse(st["stale"])
        self.exe.write_bytes(b"new exe, different size")
        os.utime(self.exe, (1, 1))
        self.assertTrue(ss.status(self.exe, run=FakeRun(), dst=self.dst)["stale"])

    def test_leftover_service_without_its_library_counts_as_not_installed(self):
        # what uninstalling PawnIO left on a real machine: service entry stopped, PawnIOLib.dll gone
        dll = self.dst / "PawnIOLib.dll"
        self.assertEqual(ss.driver_state(lambda _: "stopped", dll), "not-installed")
        dll.parent.mkdir(parents=True)
        dll.write_bytes(b"dll")
        self.assertEqual(ss.driver_state(lambda _: "stopped", dll), "stopped")

    def test_enable_starts_a_stopped_driver(self):
        run, states = FakeRun(), iter(["stopped", "running"])
        steps = ss.enable(SID, self.exe, run=run, driver=lambda: next(states), dst=self.dst)
        self.assertEqual(run.calls[0], ["sc", "start", "PawnIO"])
        self.assertIn("started the PawnIO driver", steps)

    def test_status_is_not_ready_without_the_driver(self):
        ss.enable(SID, self.exe, run=FakeRun(), driver=lambda: "running", dst=self.dst)
        st = ss.status(self.exe, run=FakeRun(), dst=self.dst, driver=lambda: "not-installed")
        self.assertFalse(st["ready"])


if __name__ == "__main__":
    unittest.main()
