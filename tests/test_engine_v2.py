import argparse
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from harness.engine import run
from harness.fixtures import create_fixture
from harness.retrieval import Index, compact_feedback
from harness.safety import Stop, clean, command, edit, git


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        fixture = create_fixture(self.base / "fixture")
        self.repo = Path(fixture["repo"])
        self.args = argparse.Namespace(**fixture, output=str(self.base / "result"), adapter=None,
                                       attempts=3, seconds=20, command_seconds=3, tokens=12000, quiet=True)

    def result(self):
        return json.loads((self.base / "result/report.json").read_text())

    def response(self, value):
        Path(self.args.mock).write_text(json.dumps(value))

    def adapter(self, source):
        path = self.base / "adapter.py"
        path.write_text("import json,sys\nr=json.load(open(sys.argv[-1]))\n" + source)
        self.args.mock = None
        self.args.adapter = [sys.executable, str(path)]

    def test_empty_edit_is_not_verified(self):
        self.response({"plan": "done", "edits": []})
        self.assertEqual(run(self.args), 2)
        self.assertFalse(self.result()["changed"])
        self.assertEqual(self.result()["model_calls"], 2)
        self.assertIn("Repeated", self.result()["error"])

    def test_in_memory_credential_redacted_from_evidence(self):
        fixture = json.loads(Path(self.args.mock).read_text())
        self.adapter("import os\nresponse=" + repr(fixture) + "\nresponse['plan']=os.environ['HARNESS_API_KEY']\nprint(json.dumps(response))\n")
        self.args.adapter_env = {"HARNESS_API_KEY": "test-opaque-credential-123456"}
        self.assertEqual(run(self.args), 0)
        text = (self.base / "result/trace.jsonl").read_text()
        self.assertNotIn("test-opaque-credential-123456", text)
        self.assertIn("[REDACTED]", text)

    def test_tests_and_test_configuration_are_protected(self):
        for name in ["check.py", "tests/test_x.py", "package.json", "pyproject.toml"]:
            if not (self.repo / name).exists():
                (self.repo / name).parent.mkdir(exist_ok=True)
                (self.repo / name).write_text("original")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "more fixtures")
        for name in ["check.py", "tests/test_x.py", "package.json", "pyproject.toml"]:
            with self.assertRaises(Stop):
                edit(self.repo, [{"path": name, "old": (self.repo / name).read_text(), "new": "pass"}], self.args.test)

    def test_baseline_already_passing_is_not_reproduced_fix(self):
        self.args.test = [sys.executable, "-c", "print('passes regardless')"]
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["status"], "tests_pass_candidate")

    def test_verifier_modifying_source_invalidates_patch(self):
        self.args.test = [sys.executable, "-c", "from pathlib import Path; Path('invoice.py').write_text('changed')"]
        self.assertEqual(run(self.args), 2)
        self.assertEqual(self.result()["verification"], "invalid")
        self.assertEqual((self.base / "result/candidate.patch").read_text(), "")
        self.assertIn("discounted", (self.repo / "invoice.py").read_text())

    def test_malformed_response_is_recoverable(self):
        fixture = json.loads(Path(self.args.mock).read_text())
        self.adapter("print('not JSON' if r['attempt']==1 else json.dumps(" + repr(fixture) + "))\n")
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["model_calls"], 2)

    def test_read_then_repair(self):
        fixture = json.loads(Path(self.args.mock).read_text())
        self.adapter("print(json.dumps({'plan':'inspect','read':[{'path':'invoice.py','start_line':1,'end_line':3}]} if r['attempt']==1 else " + repr(fixture) + "))\n")
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["model_calls"], 2)

    def test_bad_read_is_rejected_without_escape(self):
        self.response({"read": [{"path": "../outside", "start_line": 1, "end_line": 4}]})
        self.assertEqual(run(self.args), 2)
        self.assertIn("Requested read", (self.base / "result/trace.jsonl").read_text())

    def test_provider_usage_is_separate_and_enforced(self):
        response = json.loads(Path(self.args.mock).read_text())
        response["usage"] = {"input_tokens": 999999, "output_tokens": 100}
        self.response(response)
        self.assertEqual(run(self.args), 2)
        result = self.result()
        self.assertEqual(result["provider_input_tokens"], 999999)
        self.assertIn("Provider-reported", result["error"])
        self.assertFalse(result["changed"])

    def test_tiny_budget_prevents_model_call(self):
        self.args.tokens = 1
        self.assertEqual(run(self.args), 2)
        self.assertEqual(self.result()["model_calls"], 0)

    def test_cancel_before_work(self):
        self.args.cancel = threading.Event()
        self.args.cancel.set()
        self.assertEqual(run(self.args), 2)
        self.assertEqual(self.result()["status"], "cancelled")

    def test_running_process_cancellation(self):
        cancel = threading.Event()
        timer = threading.Timer(.1, cancel.set)
        timer.start()
        try:
            result = command([sys.executable, "-c", "import time;time.sleep(30)"], self.repo, 10, cancel=cancel)
            self.assertEqual(result["reason"], "cancelled")
        finally:
            timer.join()

    def test_deep_retrieval_and_cache_invalidation(self):
        root = Path(create_fixture(self.base / "deep", large=True)["repo"])
        index = Index(root)
        selected, _, stats = index.select(self.args.issue, 4000)
        self.assertTrue(any("subtotal * (1 + discount_percent / 100)" in f["content"] for f in selected))
        self.assertLess(stats["selected_context_tokens_estimate"], stats["eligible_full_source_tokens_estimate"] / 4)
        index.select(self.args.issue, 4000)
        self.assertGreater(index.cache_hits, 0)
        path = root / "invoice.py"
        path.write_text(path.read_text().replace("1 + discount_percent", "1 - discount_percent"))
        selected, _, _ = index.select(self.args.issue, 4000)
        self.assertTrue(any("1 - discount_percent" in f["content"] for f in selected))

    def test_sensitive_and_symlink_files_excluded(self):
        (self.repo / "secret.txt").write_text("PRIVATE_MATERIAL")
        (self.repo / "link.py").symlink_to(self.repo / "invoice.py")
        git(self.repo, "add", ".")
        files, _, _ = Index(self.repo).select("PRIVATE_MATERIAL link invoice")
        self.assertFalse(any(f["path"] in {"secret.txt", "link.py"} for f in files))

    def test_bounded_feedback_and_valid_json_redaction(self):
        result = compact_feedback({"code": 1, "stdout": "noise\n" * 10000, "stderr": "AssertionError: expected 5\n"})
        self.assertLessEqual(len(result["output"]), 3001)
        self.assertIn("AssertionError", result["output"])
        value = clean({"content": 'password="abc"\nnext="quoted"'})
        self.assertEqual(json.loads(json.dumps(value)), value)


if __name__ == "__main__":
    unittest.main()
