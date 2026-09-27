import argparse
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from harness.engine import run
from harness.safety import command, git
from tools.presentation import prepare


@unittest.skipUnless(shutil.which("node"), "Node.js needed for JavaScript presentation")
class PresentationTests(unittest.TestCase):
    def test_new_projects_are_independent_and_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            first, second = prepare(directory), prepare(directory)
            self.assertNotEqual(first["repo"], second["repo"])
            source = (Path(first["repo"]) / "invoice.js").read_text()
            self.assertGreaterEqual(len(source.splitlines()), 40)
            self.assertLessEqual(len(source.splitlines()), 50)
            self.assertEqual(git(Path(first["repo"]), "status", "--porcelain"), "")
            baseline = command(first["test"], first["repo"], 10)
            self.assertNotEqual(baseline["code"], 0)
            self.assertIn("discount", baseline["stdout"])

    def test_offline_edit_verify_apply_flow(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            config = prepare(base)
            response = base / "mock.json"
            response.write_text(json.dumps({"edits": [
                {"path": "invoice.js", "old": "1 + discountPercent / 100", "new": "1 - discountPercent / 100"},
                {"path": "invoice.js", "old": "subtotal > threshold", "new": "subtotal >= threshold"},
            ]}))
            result = base / "result"
            args = argparse.Namespace(**config, mock=str(response), adapter=None, output=str(result),
                                      attempts=2, tokens=12000, seconds=30, command_seconds=10, quiet=True)
            self.assertEqual(run(args), 0)
            report = json.loads((result / "report.json").read_text())
            self.assertEqual(report["mode"], "simulation")
            self.assertEqual(report["status"], "verified_candidate")
            self.assertEqual(report["baseline_verification"], "failed")
            repo = Path(config["repo"])
            self.assertIn("1 + discountPercent", (repo / "invoice.js").read_text())
            git(repo, "apply", "--check", str(result / "candidate.patch"))
            git(repo, "apply", str(result / "candidate.patch"))
            self.assertEqual(command(config["test"], repo, 10)["code"], 0)

    def test_missing_node_is_actionable(self):
        with tempfile.TemporaryDirectory() as directory, patch("tools.presentation.shutil.which", return_value=None):
            with self.assertRaisesRegex(ValueError, "requires Node.js"):
                prepare(directory)


if __name__ == "__main__":
    unittest.main()
