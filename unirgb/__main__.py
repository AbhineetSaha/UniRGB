"""python -m unirgb [--simulate] [--port N] [--no-window]"""
from __future__ import annotations

import argparse
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import webbrowser
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .app import App, VERSION
from .server import make_server

DEFAULT_PORT = 47821   # fixed so a second launch finds the first (single instance)


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


def _open_window(url: str) -> None:
    """Prefer an Edge/Chrome app window (no tabs or address bar); fall back to the default browser."""
    candidates = [shutil.which("msedge"),
                  r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                  r"C:\Program Files\Google\Chrome\Application\chrome.exe"]
    for exe in candidates:
        if exe and Path(exe).exists():
            subprocess.Popen([exe, f"--app={url}", "--window-size=1280,860"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
    webbrowser.open(url)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="unirgb", description="UniRGB unified device & RGB control center")
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--simulate", action="store_true", help="add clearly labelled simulated devices")
    ap.add_argument("--no-window", action="store_true", help="do not open the UI window")
    ap.add_argument("--openrgb-port", type=int, default=6742)
    ap.add_argument("--no-direct", action="store_true", help="disable direct HID adapters (vendor APIs only)")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    log_path = _log_setup(args.verbose)
    log = logging.getLogger("unirgb")

    url = f"http://127.0.0.1:{args.port}/"
    try:
        app = App(simulate=args.simulate, direct=not args.no_direct, openrgb_port=args.openrgb_port)
        srv = make_server(app, port=args.port)
    except OSError:
        log.info("UniRGB already running on %s; opening it", url)
        if not args.no_window:
            _open_window(url)
        return 0

    log.info("UniRGB %s starting; log at %s", VERSION, log_path)
    app.rescan(full=True)
    app.start_background()
    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, lambda *_: stop.set())
    threading.Thread(target=srv.serve_forever, name="http", daemon=True).start()
    log.info("UI at %s", url)
    if not args.no_window:
        _open_window(url)
    try:
        while not stop.wait(0.5):
            if app.quit_requested.is_set():
                break
    finally:
        log.info("shutting down: releasing device sessions")
        srv.shutdown()
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
