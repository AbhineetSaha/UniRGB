"""In-process fakes of external control paths. They model the documented wire
formats only. Passing tests against them proves our encoding is self-consistent,
not that real servers accept it. How to report real-hardware results: docs/testing.md."""
from __future__ import annotations

import json
import socket
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class FakeHid:
    def __init__(self, vid, pid, usage_page, usage, product=None, manufacturer=None, feature_len=0):
        self.vid, self.pid, self.usage_page, self.usage = vid, pid, usage_page, usage
        self.product, self.manufacturer, self.feature_len = product, manufacturer, feature_len
        self.input_len = self.output_len = 0
        self.interface_number = None

    @property
    def vidpid(self):
        return f"{self.vid:04X}:{self.pid:04X}"


class LengthRequired(Exception):
    pass


class FakeChroma:
    """Minimal Chroma SDK REST server: root, per-session uri, heartbeat, effects, delete."""

    def __init__(self):
        self.calls: list[tuple[str, str, object]] = []
        self.sessions: set[int] = set()
        self.next_port_id = 1
        self.result_code = 0
        fake = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a): pass

            def _reply(self, code, obj):
                data = json.dumps(obj).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _body(self):
                if self.headers.get("Content-Length") is None:
                    # real RzSDKServer (HTTP.sys) answers 411 to PUT/POST without Content-Length
                    # (observed with curl -X PUT); DELETE without it is accepted
                    fake.calls.append(("411", self.path, None))
                    raise LengthRequired
                n = int(self.headers["Content-Length"])
                return json.loads(self.rfile.read(n)) if n else None

            def handle_one_request(self):
                try:
                    super().handle_one_request()
                except LengthRequired:
                    self._reply(411, {})

            def _session(self):
                parts = self.path.strip("/").split("/")
                if len(parts) >= 2 and parts[0] == "s" and int(parts[1]) in fake.sessions:
                    return int(parts[1]), parts[2:]
                return None, None

            def do_GET(self):
                fake.calls.append(("GET", self.path, None))
                if self.path == "/razer/chromasdk":
                    return self._reply(200, {"core": "9.9", "device": "9.9", "version": "9.9"})
                self._reply(404, {})

            def do_POST(self):
                body = self._body()
                fake.calls.append(("POST", self.path, body))
                if self.path == "/razer/chromasdk":
                    sid = fake.next_port_id
                    fake.next_port_id += 1
                    fake.sessions.add(sid)
                    host = self.headers.get("Host")
                    return self._reply(200, {"sessionid": sid, "uri": f"http://{host}/s/{sid}/chromasdk"})
                self._reply(404, {})

            def do_PUT(self):
                body = self._body()
                fake.calls.append(("PUT", self.path, body))
                sid, rest = self._session()
                if sid is None:
                    return self._reply(404, {"result": 6})
                self._reply(200, {"tick": 1} if rest[-1] == "heartbeat" else {"result": fake.result_code})

            def do_DELETE(self):
                fake.calls.append(("DELETE", self.path, None))
                sid, _ = self._session()
                if sid is None:
                    return self._reply(404, {"result": 6})
                fake.sessions.discard(sid)
                self._reply(200, {"result": 0})

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.srv.daemon_threads = True
        self.port = self.srv.server_address[1]
        self.base = f"http://127.0.0.1:{self.port}/razer/chromasdk"
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()

    def effects(self, endpoint):
        return [b for m, p, b in self.calls if m == "PUT" and p.endswith("/" + endpoint)]

    def close(self):
        self.srv.shutdown()
        self.srv.server_close()


# ---------------- OpenRGB ----------------
def _s(text: str) -> bytes:
    b = text.encode() + b"\x00"
    return struct.pack("<H", len(b)) + b


def encode_controller(name, location, zones, proto=3, ctype=0, vendor="Vendor"):
    """zones: list of (name, led_count). Builds an OpenRGB controller-data blob."""
    body = struct.pack("<i", ctype) + _s(name)
    if proto >= 1:
        body += _s(vendor)
    body += _s("desc") + _s("1.0") + _s("SER") + _s(location)
    modes = [("Direct", 0), ("Static", 1)]
    body += struct.pack("<H", len(modes)) + struct.pack("<i", 0)
    for mn, val in modes:
        body += _s(mn) + struct.pack("<iIII", val, 0, 0, 0)
        if proto >= 3:
            body += struct.pack("<II", 0, 100)
        body += struct.pack("<III", 0, 0, 0)
        if proto >= 3:
            body += struct.pack("<I", 100)
        body += struct.pack("<II", 0, 0) + struct.pack("<H", 1) + struct.pack("<I", 0x00FF00)
    body += struct.pack("<H", len(zones))
    total = 0
    for zi, (zn, cnt) in enumerate(zones):
        body += _s(zn) + struct.pack("<iIII", 0, cnt, cnt, cnt)
        if zi == 0:   # first zone carries a 1x2 matrix to exercise the matrix path
            body += struct.pack("<H", 16) + struct.pack("<II", 1, 2) + struct.pack("<II", 0, 1)
        else:
            body += struct.pack("<H", 0)
        total += cnt
    body += struct.pack("<H", total) + b"".join(_s(f"LED {i}") + struct.pack("<I", i) for i in range(total))
    body += struct.pack("<H", total) + b"".join(struct.pack("<I", 0x0000FF) for _ in range(total))
    return struct.pack("<I", 4 + len(body)) + body


class FakeOpenRGB:
    def __init__(self, controllers, server_proto=3):
        self.controllers = controllers   # list of (name, location, zones)
        self.server_proto = server_proto
        self.received: list[tuple[int, int, bytes]] = []
        self.bare_connections = 0
        self.connections = 0
        self.sock = socket.socket()
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(4)
        self.port = self.sock.getsockname()[1]
        self._stop = False
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while not self._stop:
            try:
                c, _ = self.sock.accept()
            except OSError:
                return
            threading.Thread(target=self._client, args=(c,), daemon=True).start()

    def _client(self, c):
        proto = 0
        self.connections += 1
        got_any = False
        try:
            while True:
                hdr = b""
                while len(hdr) < 16:
                    chunk = c.recv(16 - len(hdr))
                    if not chunk:
                        if not got_any:
                            self.bare_connections += 1
                        return
                    got_any = True
                    hdr += chunk
                magic, dev, pkt, size = struct.unpack("<4sIII", hdr)
                payload = b""
                while len(payload) < size:
                    payload += c.recv(size - len(payload))
                self.received.append((dev, pkt, payload))
                send = lambda p, d, body: c.sendall(struct.pack("<4sIII", b"ORGB", d, p, len(body)) + body)
                if pkt == 40:
                    proto = min(self.server_proto, struct.unpack("<I", payload)[0])
                    send(40, 0, struct.pack("<I", self.server_proto))
                elif pkt == 0:
                    send(100, 0, b"")   # unsolicited packet the client must skip
                    send(0, 0, struct.pack("<I", len(self.controllers)))
                elif pkt == 1:
                    n, loc, zones, *ctype = self.controllers[dev]
                    send(1, dev, encode_controller(n, loc, zones, proto, ctype=ctype[0] if ctype else 0))
        except OSError:
            pass
        finally:
            c.close()

    def close(self):
        self._stop = True
        self.sock.close()
