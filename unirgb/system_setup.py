"""One-time privileged setup for the driver features (CPU temperature, RAM lighting).

The UI starts this once, elevated (one UAC prompt), as `UniRGB.exe --system-setup enable|disable`.

enable:  installs the PawnIO driver if it is missing (official installer bundled next to UniRGB.exe),
         copies UniRGB.exe and the PawnIO modules into HELPER_DIR under Program Files, and registers
         a scheduled task that runs that copy with highest privileges when the app asks for it.
         Later starts launch the helper through the task, with no prompt.
disable: deletes the task and the files it created. PawnIO stays installed: OpenRGB and
         LibreHardwareMonitor use the same driver.

Why the copy lives under Program Files: a task that silently runs something elevated is only safe if
that something cannot be replaced by a normal program, and the per-user install folder can be.
The task has no trigger and fixed arguments, so the unprivileged app can start it but not steer it.
The elevated side takes no paths from the app; it finds its inputs next to its own exe.
"""
from __future__ import annotations

import argparse
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from xml.sax.saxutils import escape

from .hostos import pawnio, windows_system

TASK_NAME = "UniRGB Hardware Helper"
HELPER_ARG = "--hardware-helper"
# Local and Microsoft accounts (S-1-5-21-...) and Microsoft Entra ID accounts (S-1-12-1-...).
SID_RE = re.compile(r"^S-1-(5-21|12-1)(-\d+){4}$")
PAWNIO_OK = (0, 3010)   # ERROR_SUCCESS, ERROR_SUCCESS_REBOOT_REQUIRED
_NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


def helper_dir() -> Path:
    pf = os.environ.get("ProgramW6432") or os.environ.get("ProgramFiles") or r"C:\Program Files"
    return Path(pf) / "UniRGB Hardware Helper"


def bundle_dir(exe: Path) -> Path:
    """PawnIO_setup.exe and modules\\*.bin, placed next to UniRGB.exe by the installer."""
    return exe.parent / "pawnio"


def task_xml(user_sid: str, exe: Path) -> str:
    if not SID_RE.match(user_sid):
        raise ValueError(f"not a user SID: {user_sid!r}")
    return f"""<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo><Description>Runs UniRGB's hardware helper with the rights the PawnIO driver needs, when UniRGB asks. Remove it from UniRGB Settings.</Description></RegistrationInfo>
  <Principals><Principal id="Author"><UserId>{user_sid}</UserId><LogonType>InteractiveToken</LogonType><RunLevel>HighestAvailable</RunLevel></Principal></Principals>
  <Settings><MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy><DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries><StopIfGoingOnBatteries>false</StopIfGoingOnBatteries><AllowStartOnDemand>true</AllowStartOnDemand><ExecutionTimeLimit>PT0S</ExecutionTimeLimit><Priority>7</Priority></Settings>
  <Actions Context="Author"><Exec><Command>"{escape(str(exe))}"</Command><Arguments>{HELPER_ARG}</Arguments></Exec></Actions>
</Task>
"""


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, creationflags=_NOWIN, timeout=300)


def driver_state(service_state=windows_system.service_state, dll: Path = pawnio.PAWNIO_DLL) -> str:
    """The PawnIO service state, or "not-installed" if its library is gone: uninstalling PawnIO can leave
    the service entry behind, and the helper cannot load the driver without PawnIOLib.dll."""
    state = service_state("PawnIO")
    return state if dll.is_file() else "not-installed"


def _end_helper(run, dst: Path) -> None:
    """Stop a running helper. Ending the task alone is not enough: the one-file exe runs a child process that
    outlives it and keeps UniRGB.exe locked. So: ask it over the pipe, end the task, then close any process still
    running the helper's own exe (matched by full path, never the UniRGB app)."""
    if dst == helper_dir():   # the real helper; tests use other folders and must not stop it
        try:
            from .hostos import pipe
            pipe.request({"op": "stop"}, timeout_s=1.0)
        except Exception:
            pass
    run(["schtasks", "/end", "/tn", TASK_NAME])
    exe = str(dst / "UniRGB.exe").replace("'", "''")
    run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
         "Get-CimInstance Win32_Process -Filter \"Name='UniRGB.exe'\" | "
         f"Where-Object {{ $_.ExecutablePath -eq '{exe}' }} | ForEach-Object {{ Stop-Process -Id $_.ProcessId -Force }}"])


def _while_running(action, end_helper, tries: int):
    """Run action; while a running helper keeps the file locked, stop it (the app may restart it) and retry."""
    for i in range(tries):
        try:
            return action()
        except PermissionError:
            if i == tries - 1:
                raise
            end_helper()
            time.sleep(0.25)


def enable(user_sid: str, src_exe: Path, run=_run, driver=driver_state, dst: Path | None = None,
           wait_tries: int = 20) -> list[str]:
    steps = []
    bundle, dst = bundle_dir(src_exe), dst or helper_dir()
    state = driver()
    if state == "not-installed":
        setup = bundle / "PawnIO_setup.exe"
        if not setup.is_file():
            raise FileNotFoundError(f"PawnIO installer missing: {setup}")
        rc = run([str(setup), "-install", "-silent"]).returncode
        if rc not in PAWNIO_OK:
            raise RuntimeError(f"PawnIO installer failed with code {rc}")
        if driver() == "not-installed":
            raise RuntimeError("PawnIO installer finished but the driver is not registered")
        steps.append("installed PawnIO" + (" (restart Windows to finish)" if rc == 3010 else ""))
    elif state != "running":
        run(["sc", "start", "PawnIO"])
        if driver() != "running":
            raise RuntimeError(f"PawnIO is installed but its driver will not start ({state}); restart Windows and try again")
        steps.append("started the PawnIO driver")
    else:
        steps.append("PawnIO already installed")

    (dst / "modules").mkdir(parents=True, exist_ok=True)
    _end_helper(run, dst)   # refreshing: the old helper keeps its .exe locked while it runs
    for src, target in [(src_exe, dst / "UniRGB.exe"),
                        *((m, dst / "modules" / m.name) for m in sorted((bundle / "modules").glob("*.bin")))]:
        _while_running(lambda: shutil.copy2(src, target), lambda: _end_helper(run, dst), wait_tries)
    steps.append(f"copied the helper to {dst}")

    with tempfile.TemporaryDirectory() as tmp:   # the elevated process's own temp folder
        xml = Path(tmp) / "task.xml"
        xml.write_text(task_xml(user_sid, dst / "UniRGB.exe"), encoding="utf-16")
        r = run(["schtasks", "/create", "/tn", TASK_NAME, "/xml", str(xml), "/f"])
    if r.returncode != 0:
        raise RuntimeError(f"could not register the task: {(r.stderr or r.stdout).strip()}")
    steps.append("registered the scheduled task")
    return steps


def disable(run=_run, dst: Path | None = None, wait_tries: int = 20) -> list[str]:
    dst = dst or helper_dir()
    _end_helper(run, dst)   # a running helper keeps its .exe locked
    run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"])   # fine if it was never created
    # Delete only what enable() and the helper created, never the folder blindly.
    for f in [dst / "UniRGB.exe", dst / "setup-result.json", dst / "helper.log", *(dst / "modules").glob("*.bin")]:
        try:
            _while_running(lambda: f.unlink(missing_ok=True), lambda: _end_helper(run, dst), wait_tries)
        except PermissionError:
            pass   # left behind; the folder stays and Settings still shows it
    for d in (dst / "modules", dst):
        try:
            d.rmdir()
        except OSError:
            pass
    return ["removed the scheduled task and the helper files"]


def status(exe: Path, run=_run, dst: Path | None = None, driver=driver_state) -> dict:
    """Unprivileged view for the UI: is the one-time setup in place and current?"""
    dst = dst or helper_dir()
    copy = dst / "UniRGB.exe"
    task = sys.platform == "win32" and run(["schtasks", "/query", "/tn", TASK_NAME]).returncode == 0
    stale = False
    if copy.is_file() and exe.is_file():
        a, b = exe.stat(), copy.stat()   # copy2 keeps the mtime, so an app update shows as a change
        stale = (a.st_size, int(a.st_mtime)) != (b.st_size, int(b.st_mtime))
    try:
        result = json.loads((dst / "setup-result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result = None
    drv = driver()
    return {"task": task, "helper": copy.is_file(), "stale": stale, "driver": drv,
            "ready": task and copy.is_file() and not stale and drv != "not-installed", "last_result": result}


def current_user_sid() -> str:
    out = _run(["whoami", "/user", "/fo", "csv", "/nh"]).stdout.strip()
    sid = out.rsplit(",", 1)[-1].strip().strip('"')
    if not SID_RE.match(sid):
        raise RuntimeError(f"could not read the current user's SID: {out!r}")
    return sid


def request(enable_: bool) -> tuple[bool, str]:
    """Called by the unprivileged app: start the elevated setup (one UAC prompt)."""
    if sys.platform != "win32":
        return False, "Windows only"
    if not getattr(sys, "frozen", False):
        return False, "The one-time setup only runs from the installed UniRGB.exe, not from source"
    args = f"--system-setup enable --user-sid {current_user_sid()}" if enable_ else "--system-setup disable"
    exe = Path(sys.executable)
    rc = ctypes.windll.shell32.ShellExecuteW(None, "runas", str(exe), args, str(exe.parent), 0)
    if rc <= 32:
        return False, "The Windows admin prompt was declined"
    return True, "Approve the Windows prompt; setup runs in the background"


def start_helper() -> bool:
    """Start the privileged helper through the task. No prompt once setup is done."""
    return sys.platform == "win32" and _run(["schtasks", "/run", "/tn", TASK_NAME]).returncode == 0


def main(argv: list[str]) -> int:
    """Entry point of the elevated process (`UniRGB.exe --system-setup ...`)."""
    ap = argparse.ArgumentParser(prog="UniRGB --system-setup")
    ap.add_argument("action", choices=("enable", "disable"))
    ap.add_argument("--user-sid", default="")
    args = ap.parse_args(argv)
    if not (sys.platform == "win32" and getattr(sys, "frozen", False) and ctypes.windll.shell32.IsUserAnAdmin()):
        return 2
    dst = helper_dir()
    try:
        steps = enable(args.user_sid, Path(sys.executable)) if args.action == "enable" else disable()
        result = {"ok": True, "action": args.action, "steps": steps, "at": time.time()}
    except Exception as e:   # reported to the UI through setup-result.json
        result = {"ok": False, "action": args.action, "error": str(e), "at": time.time()}
    if args.action == "enable":   # disable leaves nothing behind; the UI sees the task is gone
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "setup-result.json").write_text(json.dumps(result), encoding="utf-8")
    return 0 if result["ok"] else 1
