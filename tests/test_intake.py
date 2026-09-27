import os
from pathlib import Path
import tempfile
import unittest

from harness.intake import is_git_url, is_github_issue_url, parse_github_url, resolve_issue, resolve_repo
from harness.safety import edit, find_and_replace_tolerant, git


class IntakeTests(unittest.TestCase):
    def test_url_detection(self):
        self.assertTrue(is_git_url("https://github.com/oksaumya/veriswe.git"))
        self.assertTrue(is_git_url("https://github.com/oksaumya/veriswe"))
        self.assertTrue(is_git_url("git@github.com:oksaumya/veriswe.git"))
        self.assertFalse(is_git_url("/path/to/local/dir"))

        self.assertTrue(is_github_issue_url("https://github.com/oksaumya/veriswe/issues/12"))
        self.assertTrue(is_github_issue_url("https://github.com/owner/repo/pull/99"))
        self.assertFalse(is_github_issue_url("https://github.com/owner/repo"))

    def test_parse_github_url(self):
        issue_info = parse_github_url("https://github.com/oksaumya/veriswe/issues/42")
        self.assertIsNotNone(issue_info)
        self.assertEqual(issue_info["type"], "issue")
        self.assertEqual(issue_info["owner"], "oksaumya")
        self.assertEqual(issue_info["repo"], "veriswe")
        self.assertEqual(issue_info["num"], "42")
        self.assertEqual(issue_info["repo_url"], "https://github.com/oksaumya/veriswe.git")

        repo_info = parse_github_url("https://github.com/oksaumya/veriswe")
        self.assertIsNotNone(repo_info)
        self.assertEqual(repo_info["type"], "repo")
        self.assertEqual(repo_info["owner"], "oksaumya")
        self.assertEqual(repo_info["repo"], "veriswe")

    def test_resolve_issue_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            issue_file = Path(tmp) / "task.md"
            issue_file.write_text("Fix critical memory leak in worker")
            resolved = resolve_issue(f"@{issue_file}")
            self.assertEqual(resolved, "Fix critical memory leak in worker")

    def test_resolve_local_non_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / "plain_code"
            folder.mkdir()
            (folder / "app.py").write_text("print('hello')\n")
            resolved = resolve_repo(str(folder))
            self.assertEqual(resolved, folder.resolve())
            self.assertTrue((folder / ".git").is_dir())
            self.assertEqual(git(folder, "status", "--porcelain").strip(), "")

    def test_tolerant_replacement_indentation_shift(self):
        # Test case: file has 8 spaces, model provided 4 spaces
        content = (
            "class Service:\n"
            "    def calculate(self, x):\n"
            "        y = x * 2\n"
            "        return y\n"
        )
        old_text = "def calculate(self, x):\n    y = x * 2\n    return y"
        new_text = "def calculate(self, x):\n    y = x * 3\n    return y"

        result = find_and_replace_tolerant(content, old_text, new_text)
        self.assertIsNotNone(result)
        self.assertIn("        y = x * 3\n", result)

    def test_tolerant_replacement_markdown_fences(self):
        content = "def add(a, b):\n    return a - b\n"
        old_fenced = "```python\nreturn a - b\n```"
        new_fenced = "```python\nreturn a + b\n```"
        result = find_and_replace_tolerant(content, old_fenced, new_fenced)
        self.assertIsNotNone(result)
        self.assertIn("return a + b", result)


if __name__ == "__main__":
    unittest.main()
