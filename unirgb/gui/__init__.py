"""UniRGB's native window (Tk, standard library). It calls the app in-process: no web server, no browser."""
from __future__ import annotations

import logging
import queue
import threading

log = logging.getLogger("unirgb.gui")


class Bridge:
    """Runs blocking work off the Tk thread and hands results back to it. Tk is only touched on its own thread."""

    def __init__(self, root, interval_ms: int = 50):
        self.root, self._q, self._interval = root, queue.Queue(), interval_ms
        root.after(interval_ms, self._drain)

    def call_soon(self, fn, *args) -> None:
        """From any thread: run fn(*args) on the Tk thread."""
        self._q.put((fn, args))

    def run(self, work, done=None) -> None:
        """Run work() on a worker thread, then done(result or exception) on the Tk thread."""
        def target():
            try:
                result = work()
            except Exception as e:   # handed to done(), never lost
                result = e
            if done:
                self.call_soon(done, result)
        threading.Thread(target=target, daemon=True).start()

    def _drain(self) -> None:
        while True:
            try:
                fn, args = self._q.get_nowait()
            except queue.Empty:
                break
            try:
                fn(*args)
            except Exception:   # one failing callback must not stop the loop
                log.exception("UI callback failed")
        self.root.after(self._interval, self._drain)
