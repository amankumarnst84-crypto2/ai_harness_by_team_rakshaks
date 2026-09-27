import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

from harness.analysis import scan, compare
from harness.engine import run
from harness.safety import git
from harness.server import Store
from harness.terminal import Terminal


class AutoAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.repo = self.base / "repo"
        self.repo.mkdir()
        git(self.repo, "init")
        git(self.repo, "config", "user.name", "Analysis Tests")
        git(self.repo, "config", "user.email", "tests@example.invalid")
        self.files({"calc.py": "def add(a, b):\n    return a - b\n",
                    "service.py": "from calc import add\ndef total():\n    return add(2, 3)\n",
                    "tests/test_service.py": "from service import total\nassert total() == 5\n"})

    def files(self, values):
        for name, value in values.items():
            path = self.repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        git(self.repo, "add", ".")
        git(self.repo, "commit", "-m", "fixture")

    def scan(self, **kwargs):
        return scan(self.repo, {"PATH": os.environ.get("PATH", "")}, lambda: 10, **kwargs)

    def run_model(self, response):
        mock = self.base / "response.json"
        mock.write_text(json.dumps(response))
        args = argparse.Namespace(repo=str(self.repo), issue="Inspect code", test=None, auto_check=True,
                                  mock=str(mock), adapter=None, output=str(self.base / "result"),
                                  attempts=2, tokens=12000, seconds=30, command_seconds=10, quiet=True)
        code = run(args)
        report = json.loads((self.base / "result/report.json").read_text())
        return code, report

    def test_syntax_checks_do_not_execute_source(self):
        marker = self.base / "MUST_NOT_EXIST"
        self.files({"danger.py": "from pathlib import Path\nPath(" + repr(str(marker)) + ").write_text('executed')\n"})
        result = self.scan()
        self.assertFalse(marker.exists())
        self.assertTrue(result["complete"])
        self.assertFalse(result["behavior_verified"])
        self.assertEqual(result["diagnostics"], [])

    def test_graph_includes_dependencies_and_test_relationships(self):
        graph = self.scan()["graph"]
        self.assertIn({"from": "service.py", "to": "calc.py", "kind": "import"}, graph)
        self.assertIn({"from": "tests/test_service.py", "to": "service.py", "kind": "test_import"}, graph)

    def test_multi_file_candidate_is_static_not_verified(self):
        code, report = self.run_model({"edits": [
            {"path": "calc.py", "old": "return a - b", "new": "return a + b"},
            {"path": "service.py", "old": "add(2, 3)", "new": "add(3, 2)"}]})
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "static_candidate")
        self.assertEqual(report["verification"], "static_passed")
        self.assertEqual(report["comparison"]["changed_files"], ["calc.py", "service.py"])
        self.assertIn("tests/test_service.py", report["comparison"]["affected_files"])
        self.assertFalse(report["comparison"]["behavior_verified"])
        self.assertIn("return a - b", (self.repo / "calc.py").read_text())

    def test_review_can_finish_without_forcing_edits(self):
        code, report = self.run_model({"plan": "Review needs behavioral tests", "findings": [
            {"path": "calc.py", "message": "Addition currently subtracts; confirm expected behavior."}], "edits": []})
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "review_complete")
        self.assertFalse(report["changed"])
        self.assertEqual(len(report["findings"]), 1)

    def test_review_can_finish_when_model_returns_empty_edits_without_findings(self):
        code, report = self.run_model({"plan": "The code appears correct. No concrete bug found.", "edits": []})
        self.assertEqual(code, 0)
        self.assertEqual(report["status"], "review_complete")
        self.assertFalse(report["changed"])
        self.assertEqual(report["findings"], [])
        self.assertIn("No concrete bug found", report["review_summary"])

    def test_syntax_failure_and_before_after_comparison(self):
        self.files({"broken.py": "def broken(:\n    pass\n"})
        before = self.scan()
        self.assertTrue(before["diagnostics"])
        (self.repo / "broken.py").write_text("def broken():\n    pass\n")
        after = self.scan()
        delta = compare(before, after)
        self.assertEqual(delta["resolved_diagnostics"], 1)
        self.assertEqual(delta["introduced_diagnostics"], 0)

    def test_unsupported_language_is_explicitly_partial(self):
        self.files({"app.ts": "const value: number = 1;\n"})
        result = self.scan()
        self.assertFalse(result["complete"])
        self.assertEqual(result["skipped"][0]["path"], "app.ts")

    def test_scan_limit_is_reported(self):
        result = self.scan(max_files=1)
        self.assertFalse(result["complete"])
        self.assertEqual(len(result["checked_files"]), 1)

    @unittest.skipUnless(shutil.which("node"), "Node.js unavailable")
    def test_js_graph_and_syntax_without_running_code(self):
        marker = self.base / "JS_MUST_NOT_EXIST"
        self.files({"index.js": "const lib = require('./lib');\nrequire('fs').writeFileSync(" + json.dumps(str(marker)) + ", 'executed');\n",
                    "lib.js": "module.exports = 1;\n"})
        result = self.scan()
        self.assertFalse(marker.exists())
        self.assertIn({"from": "index.js", "to": "lib.js", "kind": "import"}, result["graph"])
        self.assertFalse(result["diagnostics"])

    def test_static_apply_requires_explicit_extra_consent(self):
        store = Store(self.base / "runs")
        terminal = Terminal(store, writer=lambda _: None)
        terminal.selected_job = lambda: {"mode": "model", "patch": "patch", "report": {"status": "static_candidate"}}
        with self.assertRaisesRegex(ValueError, "explicit static-patch approval"):
            terminal.apply()

    def test_behavioral_audit_request_and_parse(self):
        from harness.analysis import build_audit_request, parse_audit_response
        req = build_audit_request("Fix math error", "+return a + b", ["calc.py"], ["service.py"],
                                  [{"from": "service.py", "to": "calc.py", "kind": "import"}])
        self.assertIn("calc.py", req["changed_files"])
        self.assertIn("service.py", req["affected_downstream_files"])
        self.assertIn("service.py imports calc.py", req["dependency_relationships"])
        
        ok, reason = parse_audit_response('{"intentional": true, "reason": "Consistent addition"}')
        self.assertTrue(ok)
        self.assertEqual(reason, "Consistent addition")
        
        bad, bad_reason = parse_audit_response('{"intentional": false, "reason": "Breaks API"}')
        self.assertFalse(bad)
        self.assertEqual(bad_reason, "Breaks API")

    def test_behavioral_audit_included_in_candidate_report(self):
        code, report = self.run_model({"edits": [
            {"path": "calc.py", "old": "return a - b", "new": "return a + b"},
            {"path": "service.py", "old": "add(2, 3)", "new": "add(3, 2)"}]})
        self.assertEqual(code, 0)
        self.assertIn("behavioral_audit", report)
        self.assertTrue(report["behavioral_audit"]["intentional"])


if __name__ == "__main__":
    unittest.main()
