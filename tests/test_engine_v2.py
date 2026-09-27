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
from harness.safety import Stop, clean, command, edit, git, protected_file


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

    def test_python_syntax_rejection_is_atomic(self):
        original = (self.repo / "invoice.py").read_bytes()
        other = self.repo / "other.py"
        other.write_text("value = 1\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "second source")
        with self.assertRaisesRegex(Stop, "Python syntax rejected.*invoice.py"):
            edit(self.repo, [
                {"path": "other.py", "old": "value = 1", "new": "value = 2"},
                {"path": "invoice.py", "old": "    discounted =", "new": "        discounted ="},
            ], self.args.test)
        self.assertEqual((self.repo / "invoice.py").read_bytes(), original)
        self.assertEqual(other.read_text(), "value = 1\n")

    def test_invalid_batch_preserves_previous_valid_candidate(self):
        response = json.loads(Path(self.args.mock).read_text())
        edit(self.repo, response["edits"], self.args.test)
        before = git(self.repo, "diff")
        with self.assertRaisesRegex(Stop, "Python syntax rejected"):
            edit(self.repo, [{"path": "invoice.py", "old": "    return", "new": "return"}], self.args.test)
        self.assertEqual(git(self.repo, "diff"), before)

    def test_syntax_rejection_recovers_without_testing_broken_candidate(self):
        fixture = json.loads(Path(self.args.mock).read_text())
        bad = {"edits": [{"path": "invoice.py", "old": "    discounted =", "new": "        discounted ="}]}
        self.adapter("print(json.dumps(" + repr(bad) + " if r['attempt']==1 else " + repr(fixture) + "))\n")
        self.assertEqual(run(self.args), 0)
        events = [json.loads(line) for line in (self.base / "result/trace.jsonl").read_text().splitlines()]
        rejected = [e for e in events if e["event"] == "edit_rejected"]
        self.assertIn("No edits applied", rejected[0]["detail"])
        self.assertEqual(len([e for e in events if e["event"] == "test_started"]), 2)
        self.assertEqual(self.result()["model_calls"], 2)
        self.assertNotIn("IndentationError", (self.base / "result/candidate.patch").read_text())

    def test_usage_recorded_even_when_estimate_exceeds_budget(self):
        self.args.tokens = 3000
        self.response({"plan": "x" * 14000, "edits": [],
                       "usage": {"input_tokens": 900, "output_tokens": 3500}})
        self.assertEqual(run(self.args), 2)
        result = self.result()
        self.assertEqual(result["provider_input_tokens"], 900)
        self.assertEqual(result["provider_output_tokens"], 3500)
        self.assertTrue(result["provider_usage_complete"])
        self.assertEqual(result["budget_used_tokens"], max(result["estimated_tokens"], 4400))
        self.assertEqual(result["budget_remaining_tokens"], 0)
        self.assertFalse(result["changed"])

    def test_budget_stop_explains_output_reserve(self):
        self.args.tokens = 10000
        self.response({"read": [{"path": "invoice.py", "start_line": 1, "end_line": 3}],
                       "usage": {"input_tokens": 8500, "output_tokens": 100}})
        self.assertEqual(run(self.args), 2)
        result = self.result()
        self.assertEqual(result["model_calls"], 1)
        self.assertEqual(result["budget_remaining_tokens"], 1400)
        self.assertIn("1,400 remaining", result["error"])
        self.assertIn("reserved for output", result["error"])

    def test_mixed_noop_and_real_edit_keeps_progress(self):
        good = json.loads(Path(self.args.mock).read_text())["edits"][0]
        edit(self.repo, [{"path": "invoice.py", "old": "return", "new": "return"}, good], self.args.test)
        self.assertIn(good["new"], (self.repo / "invoice.py").read_text())

    def test_noop_only_is_rejected(self):
        with self.assertRaisesRegex(Stop, "makes no change"):
            edit(self.repo, [{"path": "invoice.py", "old": "return", "new": "return"}], self.args.test)
        self.assertFalse(git(self.repo, "diff"))

    def test_recovery_supplies_only_fresh_focus_source(self):
        good = json.loads(Path(self.args.mock).read_text())
        bad = {"edits": [{"path": "invoice.py", "old": "    discounted =", "new": "        discounted ="}]}
        self.adapter(
            "if r['attempt'] == 1:\n    answer=" + repr(bad) + "\n"
            "else:\n"
            "    assert r['recovery']['focus_file']=='invoice.py'\n"
            "    assert all(f['path']=='invoice.py' for f in r['files'])\n"
            "    assert any('    discounted = subtotal' in f['content'] for f in r['files'])\n"
            "    assert 'No edits' in r['recovery']['reason']\n"
            "    answer=" + repr(good) + "\n"
            "print(json.dumps(answer))\n")
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["model_calls"], 2)
        self.assertIn('"event": "recovery"', (self.base / "result/trace.jsonl").read_text())

    def test_repeated_noop_stops_after_focused_retry(self):
        self.args.attempts = 5
        self.response({"edits": [{"path": "invoice.py", "old": "return", "new": "return"}]})
        self.assertEqual(run(self.args), 2)
        self.assertEqual(self.result()["model_calls"], 3)
        self.assertIn("Repeated", self.result()["error"])
        self.assertFalse(self.result()["changed"])

    def test_truncated_provider_output_gets_focused_retry(self):
        good = json.loads(Path(self.args.mock).read_text())
        self.adapter("if r['attempt']==1:\n    answer={'adapter_error':'Output truncated', 'edits':[]}\n"
                     "else:\n    assert r['recovery']['focus_file']=='invoice.py'\n    answer=" + repr(good) + "\nprint(json.dumps(answer))\n")
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["model_calls"], 2)

    def test_recovery_accepts_four_independent_edits(self):
        path = self.repo / "invoice.py"
        path.write_text(path.read_text() + "\nflag_a = 0\nflag_b = 0\nflag_c = 0\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "four edit fixture")
        good = json.loads(Path(self.args.mock).read_text())
        good["edits"] += [{"path": "invoice.py", "old": "flag_" + name + " = 0", "new": "flag_" + name + " = 1"} for name in "abc"]
        bad = {"edits": [{"path": "invoice.py", "old": "absent", "new": "replacement"}]}
        self.adapter("print(json.dumps(" + repr(bad) + " if r['attempt']==1 else " + repr(good) + "))\n")
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["model_calls"], 2)
        patch = (self.base / "result/candidate.patch").read_text()
        for name in "abc":
            self.assertIn("+flag_" + name + " = 1", patch)

    def test_complete_focus_includes_late_methods_and_honors_budget(self):
        path = self.repo / "engine.js"
        path.write_text("// unrelated line\n" * 330 + "function destroy() { return 'late'; }\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "long focused source")
        index = Index(self.repo)
        files, _, _ = index.select("engine", 20000, [{"path": "engine.js", "start_line": 1, "end_line": 200}], focus="engine.js")
        self.assertEqual(len(files), 1)
        self.assertFalse(files[0]["truncated"])
        self.assertIn("function destroy", files[0]["content"])
        limited, _, _ = index.select("engine", 600, focus="engine.js")
        self.assertLessEqual(len(json.dumps(limited)), 600)
        self.assertTrue(limited[0]["truncated"])

    def test_failed_candidate_retry_sees_accepted_changes_and_file_tail(self):
        path = self.repo / "invoice.py"
        path.write_text(path.read_text() + "# context line\n" * 300 + "flag = 0\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "partial progress fixture")
        good = json.loads(Path(self.args.mock).read_text())
        partial = {"edits": [{"path": "invoice.py", "old": "flag = 0", "new": "flag = 1"}]}
        self.adapter("if r['attempt']==1:\n    answer=" + repr(partial) + "\n"
                     "else:\n"
                     "    assert r['recovery']['reason']=='Candidate tests still fail'\n"
                     "    assert any('flag = 1' in f['content'] and not f['truncated'] for f in r['files'])\n"
                     "    answer=" + repr(good) + "\nprint(json.dumps(answer))\n")
        self.assertEqual(run(self.args), 0)
        self.assertEqual(self.result()["model_calls"], 2)

    def test_test_discovery_names_are_read_only(self):
        for name in ["testinvoice.py", "test.py", "InvoiceTest.java", "InvoiceTests.cs", "invoice.SPEC.ts"]:
            self.assertTrue(protected_file(name), name)
        path = self.repo / "testinvoice.py"
        path.write_text("assert False\n")
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "discovery test")
        with self.assertRaisesRegex(Stop, "read-only"):
            edit(self.repo, [{"path": path.name, "old": "assert False", "new": "assert True"}],
                 [sys.executable, "-m", "unittest", "discover"])

    def test_json_secrets_are_redacted_from_retrieved_source(self):
        sentinel = "dummy-review-only-credential"
        (self.repo / "config.json").write_text(json.dumps({"api_key": sentinel, "nested": {"password": sentinel}}))
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "redaction fixture")
        files, _, _ = Index(self.repo).select("config api_key", 10000)
        self.assertNotIn(sentinel, json.dumps(clean(files)))
        self.assertEqual(clean({"api_key": sentinel}), {"api_key": "[REDACTED]"})
        value = clean(json.dumps({"api_key": sentinel, "normal": "keep"}))
        self.assertEqual(json.loads(value), {"api_key": "[REDACTED]", "normal": "keep"})
        escaped = json.dumps({"api_key": 'dummy"quoted\\value, tail', "normal": "keep"})
        self.assertEqual(json.loads(clean(escaped)), {"api_key": "[REDACTED]", "normal": "keep"})

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
