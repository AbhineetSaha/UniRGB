"""Local HTTP API + UI host. Loopback only.

Request hardening:
  * binds 127.0.0.1 and rejects any Host header that is not loopback (DNS rebinding)
  * every mutating request needs X-UniRGB-Token, a per-run random value embedded
    in the served page; other origins cannot read it (CSRF)
"""
from __future__ import annotations

import json
import logging
import secrets
import sys
import threading
import time
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .core.models import LightingState

log = logging.getLogger("unirgb.server")
UI_FILE = Path(__file__).parent / "ui" / "index.html"
MAX_BODY = 256 * 1024


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def make_server(app, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    token = secrets.token_urlsafe(24)

    class Handler(BaseHTTPRequestHandler):
        server_version = "UniRGB"

        def log_message(self, fmt, *args):
            log.debug("%s %s", self.address_string(), fmt % args)

        # ---------- plumbing ----------
        def _host_ok(self) -> bool:
            h = (self.headers.get("Host") or "").rsplit(":", 1)[0].strip("[]").lower()
            return h in ("127.0.0.1", "localhost", "::1")

        def _send(self, status: int, body, ctype="application/json", extra=None):
            data = body if isinstance(body, bytes) else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Content-Security-Policy",
                             "default-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "script-src 'self' 'unsafe-inline'; frame-ancestors 'none'")
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ApiError(413, "request too large")
            raw = self.rfile.read(n) if n else b""
            ctype = self.headers.get("Content-Type", "")
            if not raw:
                return {}
            if "json" in ctype:
                try:
                    return json.loads(raw)
                except ValueError:
                    raise ApiError(400, "invalid JSON")
            return raw.decode("utf-8", "replace")

        def _dispatch(self, method: str):
            if not self._host_ok():
                return self._send(403, {"error": "forbidden host"})
            if method != "GET" and not secrets.compare_digest(self.headers.get("X-UniRGB-Token", ""), token):
                return self._send(403, {"error": "missing or bad token"})
            path = urlparse(self.path).path
            parts = [unquote(p) for p in path.strip("/").split("/") if p]
            try:
                status, body, *rest = route(method, parts, self)
                self._send(status, body, *rest)
            except ApiError as e:
                self._send(e.status, {"error": str(e)})
            except ValueError as e:
                self._send(400, {"error": str(e)})
            except Exception as e:   # never let one request take the server down
                log.exception("request failed")
                self._send(500, {"error": f"internal error: {e}"})

        def do_GET(self): self._dispatch("GET")
        def do_POST(self): self._dispatch("POST")
        def do_DELETE(self): self._dispatch("DELETE")

    def state_payload():
        return {
            "version": app_version(), "simulate": app.simulate,
            "devices": [r.to_dict() for r in app.orch.registry.snapshot()],
            "health": {n: asdict(h) for n, h in app.orch.health().items()},
            "adapters": {n: {"control_path": a.control_path, "priority": a.priority} for n, a in app.orch.adapters.items()},
            "scenes": {n: {d: s.to_dict() for d, s in devs.items()} for n, devs in app.scenes.list().items()},
            "scene_store": {"path": str(app.scenes.path), "load_error": app.scenes.load_error},
            "last_scan": app.last_scan, "last_scan_ms": round(app.last_scan_ms, 1),
        }

    def route(method, parts, h):
        if method == "GET" and parts == ["favicon.ico"]:
            return 200, (UI_FILE.parent / "logo.ico").read_bytes(), "image/x-icon"
        if method == "GET" and parts in ([], ["index.html"]):
            html = UI_FILE.read_text(encoding="utf-8").replace("__UNIRGB_TOKEN__", token)
            return 200, html.encode(), "text/html; charset=utf-8"
        if parts[:1] != ["api"]:
            raise ApiError(404, "not found")
        p = parts[1:]
        if method == "GET" and p == ["state"]:
            return 200, state_payload()
        if method == "POST" and p == ["quit"]:
            # release device sessions, then let the main loop exit
            threading.Thread(target=app.request_quit, daemon=True).start()
            return 200, {"ok": True, "message": "UniRGB is shutting down; vendor apps take lighting back"}
        if method == "POST" and p == ["rescan"]:
            app.rescan(full=True)
            return 200, state_payload()
        if method == "GET" and p == ["diagnostics"]:
            return 200, {"health": {n: asdict(x) for n, x in app.orch.health().items()},
                         "hid_error": app.hid.error,
                         "hid": [i.to_dict() for i in app.hid.get()], "time": time.time()}
        if len(p) == 3 and p[0] == "devices":
            dev, action = p[1], p[2]
            if method == "POST" and action == "apply":
                body = h._body()
                state = LightingState.from_dict(body.get("state") if isinstance(body, dict) else None)
                res = app.orch.apply(dev, state)
                return (200 if res.ok else 409), {"ok": res.ok, "message": res.message,
                                                  "confirmation": res.confirmation.value}
            if method == "POST" and action == "restore":
                res = app.orch.restore(dev)
                return (200 if res.ok else 409), {"ok": res.ok, "message": res.message}
            if method == "POST" and action == "configure":
                body = h._body()
                if not isinstance(body, dict):
                    raise ApiError(400, "expected JSON object")
                res = app.orch.configure(dev, body)
                return (200 if res.ok else 409), {"ok": res.ok, "message": res.message}
            if method == "GET" and action == "status":
                return 200, app.orch.status(dev)
            if method == "POST" and action == "cpu-helper":
                rec = app.orch.registry.get(dev)
                adapter = app.orch.adapters.get(rec.info.adapter) if rec else None
                if not hasattr(adapter, "start_cpu_helper"):
                    raise ApiError(404, "device has no CPU helper")
                res = adapter.start_cpu_helper()
                return (200 if res.ok else 409), {"ok": res.ok, "message": res.message}
        if p == ["scenes"] and method == "POST":
            body = h._body()
            if not isinstance(body, dict):
                raise ApiError(400, "expected JSON object")
            name = body.get("name", "")
            if body.get("capture"):
                devices = {r.info.id: r.desired for r in app.orch.registry.snapshot() if r.desired}
            else:
                devices = {d: LightingState.from_dict(s) for d, s in (body.get("devices") or {}).items()}
            app.scenes.put(name, devices)
            return 200, {"ok": True, "scenes": sorted(app.scenes.list())}
        if p == ["scenes", "export"] and method == "GET":
            return 200, app.scenes.serialize().encode(), "application/json", \
                {"Content-Disposition": 'attachment; filename="unirgb-scenes.json"'}
        if p == ["scenes", "import"] and method == "POST":
            body = h._body()
            text = body if isinstance(body, str) else json.dumps(body)
            return 200, {"ok": True, "imported": app.scenes.import_json(text)}
        if len(p) == 3 and p[0] == "scenes" and p[2] == "apply" and method == "POST":
            try:
                results = app.scenes.apply(p[1], app.orch)
            except KeyError:
                raise ApiError(404, "no such scene")
            return 200, {"results": {d: {"ok": r.ok, "message": r.message} for d, r in results.items()}}
        if len(p) == 2 and p[0] == "scenes" and method == "DELETE":
            return (200 if app.scenes.delete(p[1]) else 404), {"ok": True}
        raise ApiError(404, "not found")

    def app_version():
        from .app import VERSION
        return VERSION

    class _Server(ThreadingHTTPServer):
        # On Windows SO_REUSEADDR lets a second process bind the same port, which
        # would defeat the single-instance check and create duplicate device sessions.
        allow_reuse_address = sys.platform != "win32"

    srv = _Server((host, port), Handler)
    srv.daemon_threads = True
    srv.token = token   # exposed for tests
    return srv
