"""python -m unirgb [--simulate] [--no-window]"""
from __future__ import annotations

import argparse
import logging
import os
import signal
import subprocess
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .app import App, VERSION

ICON = Path(__file__).parent / "ui" / "logo.ico"


def _log_setup(verbose: bool) -> Path:
    base = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "UniRGB"
    base.mkdir(parents=True, exist_ok=True)
    path = base / "unirgb.log"
    handlers = [RotatingFileHandler(path, maxBytes=1_000_000, backupCount=2, encoding="utf-8")]
    if sys.stderr is not None:   # None under pythonw
        handlers.append(logging.StreamHandler(sys.stderr))
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, handlers=handlers,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    return path


def _relaunch(argv: list[str]) -> None:
    """Start a fresh UniRGB with its window showing (used after the one-time driver setup)."""
    args = [a for a in argv if a != "--no-window"]
    cmd = [sys.executable, *args] if getattr(sys, "frozen", False) else [sys.executable, "-m", "unirgb", *args]
    # a fresh one-file bootstrap, not a child that reuses this instance's unpacked files (deleted when we exit)
    env = {**os.environ, "PYINSTALLER_RESET_ENVIRONMENT": "1"}
    subprocess.Popen(cmd, env=env, close_fds=True, creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))


def _raise_priority(log) -> None:
    import ctypes   # above normal, not high: lighting stays responsive without starving games
    k32 = ctypes.windll.kernel32
    k32.GetCurrentProcess.restype = ctypes.c_void_p   # untyped, the 64-bit pseudo-handle is truncated
    k32.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
    if not k32.SetPriorityClass(k32.GetCurrentProcess(), 0x8000):   # ABOVE_NORMAL_PRIORITY_CLASS
        log.warning("could not raise process priority")


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--cpu-helper"]:   # how the packaged .exe starts its elevated sensor helper
        from .cpu_temp_helper import main as helper_main
        return helper_main(argv[1:])
    if argv[:1] == ["--hardware-helper"]:   # started elevated by the scheduled task; fixed arguments
        from .hardware_helper import main as hw_main
        return hw_main(argv[1:])
    if argv[:1] == ["--system-setup"]:   # elevated one-time setup started from Settings
        from .system_setup import main as setup_main
        return setup_main(argv[1:])
    ap = argparse.ArgumentParser(prog="unirgb", description="UniRGB unified device & RGB control center")
    ap.add_argument("--simulate", action="store_true", help="add clearly labelled simulated devices")
    ap.add_argument("--no-window", action="store_true", help="start in the background (tray icon only)")
    ap.add_argument("--openrgb-port", type=int, default=6742)
    ap.add_argument("--no-direct", action="store_true", help="disable direct HID adapters (vendor APIs only)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)

    win32 = sys.platform == "win32"
    instance = None
    if win32:
        from .hostos.instance import SingleInstance
        instance = SingleInstance()
        if not instance.first:   # already running: bring its window forward instead
            if not args.no_window:
                instance.show_existing()
            return 0
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # sharp text on scaled displays
        except (AttributeError, OSError):
            pass

    log_path = _log_setup(args.verbose)
    log = logging.getLogger("unirgb")
    log.info("UniRGB %s starting; log at %s", VERSION, log_path)
    app = App(simulate=args.simulate, direct=not args.no_direct, openrgb_port=args.openrgb_port)
    app.rescan(full=True)
    app.start_background()
    if win32:
        _raise_priority(log)

    import tkinter as tk
    from .gui import Bridge
    from .gui.dialogs import DiagnosticsDialog, ScenesDialog, SettingsDialog
    from .gui.window import MainWindow

    root = tk.Tk()
    if args.no_window:
        root.withdraw()
    if win32 and ICON.is_file():
        root.iconbitmap(default=str(ICON))
    bridge = Bridge(root)
    holder = {}

    def show():
        root.deiconify()
        root.lift()
        root.focus_force()

    win = MainWindow(root, app, bridge, VERSION, on_quit=app.request_quit,
                     open_settings=lambda first: SettingsDialog(holder["win"], first, on_restart=lambda: app.request_quit(True)),
                     open_scenes=lambda: ScenesDialog(holder["win"]),
                     open_diagnostics=lambda: DiagnosticsDialog(holder["win"]))
    holder["win"] = win
    root.protocol("WM_DELETE_WINDOW", root.withdraw)   # closing the window keeps UniRGB running in the tray

    tray = None
    if win32:
        from .hostos.tray import Tray
        tray = Tray(ICON, f"UniRGB {VERSION} is running", on_open=lambda: bridge.call_soon(show), on_quit=app.request_quit)
        tray.start()
        instance.watch(lambda: bridge.call_soon(show))
    if not app.prefs.prefs.setup_done:   # first start: ask which features to use
        show()
        root.after(300, lambda: win.open_settings(True))

    signal.signal(signal.SIGINT, lambda *_: app.request_quit())
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: app.request_quit())

    def watch_quit():
        if app.quit_requested.is_set():
            root.quit()
        else:
            root.after(200, watch_quit)
    root.after(200, watch_quit)
    try:
        root.mainloop()
    finally:
        log.info("shutting down: releasing device sessions")
        if tray:
            tray.stop()
        app.shutdown()
        try:
            root.destroy()
        except tk.TclError:
            pass
        if app.restart_requested:
            if instance:
                instance.release()   # the new process must become the first instance
            _relaunch(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main())
