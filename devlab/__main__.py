"""python -m devlab [--port N]: the Device Lab at http://127.0.0.1:47850/ (virtual devices only)."""
from __future__ import annotations

import argparse
import json
import threading
import webbrowser
from contextlib import nullcontext
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from unirgb_smbus import ene
from unirgb_smbus.bus import ReadOnlySmbus
from unirgb_smbus.probe import probe

from .virtual_smbus import Tripwire, VirtualEne, VirtualPiix4

PAGE = Path(__file__).with_name("lab.html")


class Lab:
    def __init__(self):
        self.lock = threading.Lock()   # one scenario at a time
        self.last = ""
        self.reset()

    def reset(self):
        self.bus = VirtualPiix4({0x71: VirtualEne(), 0x73: VirtualEne(((0, 140, 255),) * 8)})
        self.lighting = None

    def _lighting(self) -> ene.EneLighting:
        if self.lighting is None:   # same order as a real run: probe, then only confirmed controllers
            confirmed = {f["address"] for f in probe(ReadOnlySmbus(self.bus, nullcontext())) if f["ene"]}
            self.lighting = ene.EneLighting(ene.EneReader(self.bus, nullcontext(), confirmed))
        return self.lighting

    def state(self) -> dict:
        return {"devices": [{"address": f"0x{a:02X}", "name": "AUDA0-E6K5-0101 (virtual)", "leds": d.leds(),
                             "direct": d.direct_active, "saved": d.saved} for a, d in sorted(self.bus.controllers.items())],
                "trace": self.bus.trace[-400:], "busy_for": self.bus.busy_for, "last": self.last}

    def run(self, action: str, addr: int = 0x71, color: str = "#ff0000") -> str:
        rgb = tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))
        try:
            if action == "probe":
                found = probe(ReadOnlySmbus(self.bus, nullcontext()))
                return "found: " + (", ".join(f"0x{f['address']:02X} ({'ENE' if f['ene'] else 'not ENE'})" for f in found) or "nothing")
            if action == "identify":
                info = self._lighting().verify(addr)
                if info is None:
                    return f"0x{addr:02X}: identification stopped at a failed transfer (bus busy or no answer)"
                return f"0x{addr:02X}: {info['name']}, LED count {info['led_count_candidates']}"
            if action == "rehearse":   # step 2, exactly as it would run on a real stick, with a short hold
                return ene.color_test(self._lighting(), addr, rgb, hold_s=3.0)
            if action == "set":
                L = self._lighting()
                L.verify(addr)
                ok = L.set_colors(addr, [rgb] * ene.LED_COUNT) and L.set_direct(addr, True)
                return "set" if ok else "the controller stopped answering"
            if action == "release":
                L = self._lighting()
                L.verify(addr)
                return "handed back" if L.set_direct(addr, False) else "the controller stopped answering"
            if action == "try-save":
                L = self._lighting()
                L.verify(addr)
                L.write_register(addr, ene.APPLY_REG, 0xAA)
                return "NOT BLOCKED: UniRGB sent the save command"
            if action == "try-spd":
                ene.EneReader(self.bus, nullcontext(), {0x50})
                return "NOT BLOCKED: UniRGB accepted an SPD hub address"
            if action == "check-tripwire":   # bypasses UniRGB on purpose, to prove the lab itself catches it
                self.bus.execute("ioctl_smbus_xfer", [0x50, 1, 0x00, 2], 1)
                return "the lab did not catch a transfer to an SPD hub"
            if action == "fault-busy":
                self.bus.busy_for = 6
                return "the next 6 transfers will fail as if another tool held the bus"
            if action == "fault-unplug":
                self.bus.controllers.pop(addr, None)
                return f"0x{addr:02X} no longer answers"
            if action == "reset":
                self.reset()
                return "lab reset"
            return f"unknown action {action}"
        except ValueError as e:
            return f"BLOCKED by UniRGB before reaching the bus: {e}"
        except Tripwire as e:
            return f"TRIPWIRE: {e}"


def make_server(lab: Lab, port: int) -> ThreadingHTTPServer:
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _guard(self) -> bool:
            if self.headers.get("Host") not in allowed_hosts:   # DNS rebinding
                self._send(403, {"error": "bad host"})
                return False
            return True

        def do_GET(self):
            if not self._guard():
                return
            if self.path == "/":
                return self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            if self.path == "/api/state":
                return self._send(200, lab.state())
            self._send(404, {"error": "not found"})

        def do_POST(self):
            if not self._guard():
                return
            if self.path != "/api/run" or self.headers.get("Content-Type") != "application/json":
                return self._send(400, {"error": "POST JSON to /api/run"})
            body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)) or b"{}")
            addr = int(str(body.get("address", "0x71")), 16)

            def work():
                with lab.lock:
                    lab.last = lab.run(str(body.get("action")), addr, str(body.get("color", "#ff0000")))

            if body.get("action") == "rehearse":   # runs for a few seconds; the page watches the LEDs meanwhile
                threading.Thread(target=work, daemon=True).start()
                return self._send(200, {"result": "rehearsal started"})
            work()
            self._send(200, {"result": lab.last})

    return ThreadingHTTPServer(("127.0.0.1", port), H)


def main() -> None:
    ap = argparse.ArgumentParser(description="UniRGB Device Lab (virtual devices only)")
    ap.add_argument("--port", type=int, default=47850)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    lab = Lab()
    srv = make_server(lab, args.port)
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Device Lab at {url} (virtual devices only; Ctrl+C to stop)")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
