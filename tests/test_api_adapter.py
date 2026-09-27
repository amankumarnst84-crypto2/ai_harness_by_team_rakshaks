from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import tempfile
from pathlib import Path
import unittest

from harness.api_adapter import call_api, complete, configuration


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.requests = []
        cls.content = json.dumps({"plan": "repair", "edits": [{"path": "app.py", "old": "a-b", "new": "a+b"}]})
        cls.finish = "stop"
        cls.reject_thinking = False

        class FakeProvider(BaseHTTPRequestHandler):
            def do_POST(self):
                payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                cls.requests.append({"path": self.path, "payload": payload, "authorization": self.headers.get("Authorization")})
                if cls.reject_thinking and "thinking" in payload:
                    body = json.dumps({"error": {"message": "unrecognized parameter thinking"}}).encode()
                    self.send_response(400)
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                result = {"choices": [{"message": {"content": cls.content}, "finish_reason": cls.finish}],
                          "usage": {"prompt_tokens": 100, "completion_tokens": 35, "prompt_tokens_details": {"cached_tokens": 40}}}
                body = json.dumps(result).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path.endswith("/redirect"):
                    self.send_response(302)
                    self.send_header("Location", "/models")
                    self.end_headers()
                    return
                if self.path.endswith("/denied"):
                    self.send_response(401)
                    self.end_headers()
                    self.wfile.write(b"sensitive body must not be echoed")
                    return
                body = json.dumps({"data": [{"id": "college-qwen"}, {"id": "college-deepseek"}]}).encode()
                self.send_response(200)
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *args):
                pass

        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = "http://127.0.0.1:%d/v1" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def test_provider_payloads_and_usage(self):
        for provider in ("groq", "deepseek", "qwen", "compatible"):
            env = configuration(provider, self.base, "college-model", "test-only-key")
            answer = complete({"instruction": "Return JSON", "issue": "fix", "max_output_tokens": 700}, env)
            sent = self.requests[-1]
            self.assertEqual(sent["path"], "/v1/chat/completions")
            self.assertEqual(sent["authorization"], "Bearer test-only-key")
            self.assertEqual(sent["payload"]["model"], "college-model")
            self.assertEqual(sent["payload"]["max_completion_tokens" if provider == "groq" else "max_tokens"], 700)
            self.assertEqual(answer["usage"], {"input_tokens": 100, "output_tokens": 35, "cached_input_tokens": 40})
            self.assertEqual(answer["edits"][0]["new"], "a+b")

    def test_malformed_and_truncated_output_preserves_usage(self):
        env = configuration("groq", self.base, "college-model", "test-only-key")
        old = type(self).content
        try:
            type(self).content = "malformed"
            answer = complete({"instruction": "JSON"}, env)
            self.assertEqual(answer["edits"], [])
            self.assertEqual(answer["usage"]["output_tokens"], 35)
            type(self).finish = "length"
            answer = complete({"instruction": "JSON"}, env)
            self.assertIn("cap", answer["plan"])
            self.assertEqual(answer["usage"]["input_tokens"], 100)
        finally:
            type(self).content, type(self).finish = old, "stop"

    def test_deepseek_text_only_bounded_non_thinking_payload(self):
        env = configuration("deepseek", self.base, "deepseek-v4-pro", "test-only-key")
        complete({"instruction": "Return JSON edits", "issue": "repair", "max_output_tokens": 900}, env)
        payload = self.requests[-1]["payload"]
        self.assertEqual(payload["model"], "deepseek-v4-pro")
        self.assertEqual(payload["thinking"], {"type": "disabled"})
        self.assertEqual(payload["temperature"], 0)
        self.assertEqual(payload["max_tokens"], 900)
        self.assertEqual(payload["response_format"], {"type": "json_object"})
        self.assertTrue(all(isinstance(message["content"], str) for message in payload["messages"]))
        self.assertNotIn("test-only-key", json.dumps(payload))

    def test_http_400_thinking_fallback_and_detail(self):
        old = type(self).reject_thinking
        try:
            type(self).reject_thinking = True
            env = configuration("deepseek", self.base, "deepseek-v4-pro", "test-only-key")
            answer = complete({"instruction": "Return JSON edits", "issue": "repair", "max_output_tokens": 900}, env)
            self.assertEqual(answer["edits"][0]["new"], "a+b")
            self.assertNotIn("thinking", self.requests[-1]["payload"])
        finally:
            type(self).reject_thinking = old

    def test_model_list(self):
        models = call_api(self.base, "test-only-key", "/models")
        self.assertEqual(models["data"][0]["id"], "college-qwen")

    def test_no_key_forwarding_on_redirect(self):
        with self.assertRaisesRegex(ValueError, "redirects"):
            call_api(self.base, "test-only-key", "/redirect")

    def test_provider_error_does_not_echo_body(self):
        with self.assertRaises(ValueError) as error:
            call_api(self.base, "test-only-key", "/denied")
        self.assertIn("401", str(error.exception))
        self.assertNotIn("sensitive body", str(error.exception))

    def test_endpoint_validation(self):
        for url in ("http://remote.example/v1", "https://key@remote.example/v1", "https://remote.example/v1?key=oops"):
            with self.assertRaises(ValueError):
                configuration("groq", url, "model", "fake")
        with self.assertRaisesRegex(ValueError, "API key"):
            configuration("groq", None, "model", "")

    def test_evaluation_with_two_fake_models_and_real_tests(self):
        from evaluate import evaluate
        from harness.fixtures import create_fixture
        old = type(self).content
        try:
            with tempfile.TemporaryDirectory() as tmp:
                fixture = create_fixture(Path(tmp) / "fixture")
                type(self).content = Path(fixture["mock"]).read_text()
                manifest = {"models": [{"id": name, "provider": "compatible", "api_base": self.base, "model": name} for name in ("fake-qwen", "fake-deepseek")],
                            "tasks": [{"id": "invoice", "repo": fixture["repo"], "issue": fixture["issue"], "test": fixture["test"]}]}
                summary = evaluate(manifest, Path(tmp) / "evaluation", tokens=12000, attempts=2, seconds=15)
                self.assertEqual(len(summary["rows"]), 2)
                for name in ("fake-qwen", "fake-deepseek"):
                    self.assertEqual(summary["totals"][name]["verified_fixes"], 1)
                    self.assertEqual(summary["totals"][name]["reported_tokens"], 135)
                    self.assertEqual(summary["totals"][name]["complete_usage_tasks"], 1)
                self.assertTrue((Path(tmp) / "evaluation/summary.json").exists())
        finally:
            type(self).content = old


if __name__ == "__main__":
    unittest.main()
