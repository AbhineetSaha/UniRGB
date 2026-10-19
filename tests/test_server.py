import http.client
import json
import tempfile
import threading
import unittest
from pathlib import Path

from unirgb.adapters.simulated import SimulatedAdapter
from unirgb.app import App, HidCache
from unirgb.server import make_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.app = App(adapters=[SimulatedAdapter()], hid_cache=HidCache(lambda: []),
                      scenes_path=Path(cls.tmp.name) / "s.json", simulate=True)
        cls.app.rescan()
        cls.srv = make_server(cls.app, port=0)
        cls.port = cls.srv.server_address[1]
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        cls.app.shutdown()
        cls.tmp.cleanup()

    def req(self, method, path, body=None, token=True, host=None):
        c = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        h = {"Host": host or f"127.0.0.1:{self.port}"}
        if token:
            h["X-UniRGB-Token"] = self.srv.token
        data = None
        if body is not None:
            data = json.dumps(body)
            h["Content-Type"] = "application/json"
        c.request(method, path, data, h)
        r = c.getresponse()
        raw = r.read()
        c.close()
        try:
            return r.status, json.loads(raw)
        except ValueError:
            return r.status, raw

    def test_index_embeds_token(self):
        st, body = self.req("GET", "/", token=False)
        self.assertEqual(st, 200)
        self.assertIn(self.srv.token.encode(), body)

    def test_favicon(self):
        st, body = self.req("GET", "/favicon.ico", token=False)
        self.assertEqual(st, 200)
        self.assertEqual(body[:4], bytes([0, 0, 1, 0]), "ICO header")

    def test_state(self):
        st, body = self.req("GET", "/api/state", token=False)
        self.assertEqual(st, 200)
        self.assertEqual({d["info"]["id"] for d in body["devices"]}, {"sim:strip", "sim:fan"})

    def test_csrf_and_host_checks(self):
        st, _ = self.req("POST", "/api/rescan", token=False)
        self.assertEqual(st, 403)
        st, _ = self.req("GET", "/api/state", host="evil.example:80")
        self.assertEqual(st, 403)

    def test_apply_restore_and_errors(self):
        st, body = self.req("POST", "/api/devices/sim%3Afan/apply", {"state": {"mode": "static", "color": "#00ff00"}})
        self.assertEqual((st, body["ok"]), (200, True))
        st, body = self.req("POST", "/api/devices/sim%3Afan/apply", {"state": {"mode": "static", "color": "#00ff00", "brightness": 300}})
        self.assertEqual(st, 400)
        st, body = self.req("POST", "/api/devices/sim%3Afan/apply", {"state": {"mode": "disco", "color": "#00ff00"}})
        self.assertEqual(st, 409)
        st, body = self.req("POST", "/api/devices/sim%3Afan/restore")
        self.assertTrue(body["ok"])
        st, _ = self.req("GET", "/api/nope", token=False)
        self.assertEqual(st, 404)

    def test_scene_flow(self):
        self.req("POST", "/api/devices/sim%3Astrip/apply", {"state": {"mode": "static", "color": "#123456"}})
        st, body = self.req("POST", "/api/scenes", {"name": "Test", "capture": True})
        self.assertEqual(st, 200, body)
        st, body = self.req("POST", "/api/scenes/Test/apply")
        self.assertTrue(all(r["ok"] for r in body["results"].values()))
        st, raw = self.req("GET", "/api/scenes/export", token=False)
        self.assertIn("Test", raw["scenes"] if isinstance(raw, dict) else json.loads(raw)["scenes"])
        st, _ = self.req("DELETE", "/api/scenes/Test")
        self.assertEqual(st, 200)
        st, _ = self.req("POST", "/api/scenes/Missing/apply")
        self.assertEqual(st, 404)


if __name__ == "__main__":
    unittest.main()
