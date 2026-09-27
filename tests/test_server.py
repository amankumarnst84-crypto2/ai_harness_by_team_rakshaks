from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from harness.server import Handler, Store


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.store = Store(cls.temp.name)
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.store = cls.store
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = "http://127.0.0.1:" + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.temp.cleanup()

    def request(self, path, data=None, headers=None):
        opts = {"Content-Type": "application/json", "X-Harness-Token": self.store.csrf}
        opts.update(headers or {})
        request = Request(self.url + path, data=None if data is None else json.dumps(data).encode(), headers=opts)
        with urlopen(request, timeout=5) as response:
            return response.status, response.read().decode(), response.headers

    def test_cross_origin_and_wrong_token_rejected(self):
        for headers in [{"Origin": "https://untrusted.example"}, {"X-Harness-Token": "wrong"}, {"Host": "untrusted.example"}]:
            with self.assertRaises(HTTPError) as error:
                self.request("/api/runs", {"mode": "demo"}, headers)
            self.assertEqual(error.exception.code, 403)

    def test_connection_keeps_key_in_memory_and_requires_new_endpoint_key(self):
        try:
            _, body, _ = self.request("/api/connection", {"provider": "groq", "model": "test-model", "api_key": "test-opaque-value"})
            self.assertNotIn("test-opaque-value", body)
            self.assertTrue(json.loads(body)["has_key"])
            self.assertNotIn("test-opaque-value", self.request("/api/config")[1])
            reloaded = Store(self.temp.name)
            self.assertFalse(reloaded.public_config()["has_key"])
            with self.assertRaises(HTTPError):
                self.request("/api/connection", {"provider": "groq", "api_base": "https://different.example/v1", "model": "test-model", "api_key": ""})
        finally:
            self.request("/api/connection", {"disconnect": True})

    def test_exporter_skips_unfinished_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / "unfinished"
            directory.mkdir()
            (directory / "meta.json").write_text(json.dumps({"id": "unfinished", "created": "2026-01-01", "mode": "model", "status": "running"}))
            store = Store(tmp, metrics_only=True)
            self.assertEqual(store.summaries(), [])
            self.assertNotIn("harness_active_runs", store.metrics(include_active=False))

    def test_static_csp_and_no_traversal(self):
        code, body, headers = self.request("/")
        self.assertEqual(code, 200)
        self.assertIn("AI Harness", body)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        with self.assertRaises(HTTPError):
            self.request("/../../harness/server.py")

    def test_validation_and_missing_model(self):
        for data in [{"tokens": 1}, {"attempts": True}, {"mode": "model"}, [], {"mode": "unknown"}]:
            with self.assertRaises(HTTPError) as error:
                self.request("/api/runs", data)
            self.assertEqual(error.exception.code, 400)

    def test_run_artifacts_metrics_and_reload(self):
        _, body, _ = self.request("/api/runs", {"mode": "demo"})
        identity = json.loads(body)["id"]
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            job = json.loads(self.request("/api/runs/" + identity)[1])
            if job["status"] != "running":
                break
            time.sleep(.05)
        self.assertEqual(job["status"], "verified_candidate")
        self.assertTrue(job["patch"])
        self.assertIn("Simulation".lower(), job["report"]["mode"])
        self.assertIn("-    discounted", self.request("/api/runs/" + identity + "/patch")[1])
        metrics = self.request("/metrics")[1]
        self.assertIn('harness_runs_total{mode="demo",status="verified_candidate"} 1', metrics)
        self.assertNotIn("invoice.py", metrics)
        reloaded = Store(self.temp.name)
        self.assertEqual(reloaded.detail(identity)["status"], "verified_candidate")
        self.assertEqual(reloaded.metrics(), self.store.metrics())


if __name__ == "__main__":
    unittest.main()
