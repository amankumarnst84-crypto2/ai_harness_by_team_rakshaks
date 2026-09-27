import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from harness.config import Settings
from harness.engine import run
from harness.fixtures import create_fixture
from harness.retrieval import Index, MAX_FILE_BYTES
from harness.safety import git
from harness.server import Store
from harness.tui import RakshakTUI, ConfirmApply
from textual.widgets import Button, Input, Static, TextArea, TabbedContent
from tools.submission import check, package, source_files


class SubmissionTests(unittest.TestCase):
    def test_runtime_key_only_no_provider_fallback(self):
        settings = Settings.from_env({"AI_API_KEY": "runtime-only-sentinel",
                                      "DEEPSEEK_API_KEY": "must-not-win"})
        self.assertEqual(settings.key, "runtime-only-sentinel")
        self.assertNotIn(settings.key, repr(settings))
        self.assertEqual(settings.model, "deepseek-v4-pro")
        self.assertEqual(Settings.from_env({"DEEPSEEK_API_KEY": "ignored"}).key, "")

    def test_prescribed_model_and_endpoint_kept(self):
        settings = Settings.from_env({"AI_API_KEY": "test-only",
                                     "AI_PROVIDER": "compatible",
                                     "AI_MODEL": "college-qwen",
                                     "AI_BASE_URL": "https://college.example/v1"})
        with tempfile.TemporaryDirectory() as tmp:
            store = Store(tmp)
            settings.connect(store)
            self.assertEqual(store.adapter_env["HARNESS_MODEL"], "college-qwen")
            self.assertEqual(store.adapter_env["HARNESS_API_KEY"], "test-only")

    def test_settings_validate_budgets_and_missing_key(self):
        for env in ({"HARNESS_TOKENS": "10"}, {"HARNESS_ATTEMPTS": "0"},
                    {"AI_BASE_URL": "http://remote.example"}):
            with self.assertRaises(ValueError):
                Settings.from_env(env)
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ValueError, "AI_API_KEY"):
                Settings.from_env({}).connect(Store(tmp))

    def test_current_submission_has_no_detected_embedded_keys(self):
        self.assertGreater(len(check()), 20)

    def test_package_excludes_local_data_and_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in ("requirements.txt", "README.md", "SUBMISSION.md"):
                (root / name).write_text("fixture")
            (root / "Makefile").write_text("setup:\nrun:\ntest:\nclean:\n")
            (root / ".env.example").write_text("AI_API_KEY=\n")
            for folder in (".git", ".venv", ".harness-data"):
                (root / folder).mkdir()
                (root / folder / "private.txt").write_text("private")
            (root / ".env").write_text("PRIVATE")
            (root / "big.js").write_text("generated")
            with zipfile.ZipFile(package(root)) as archive:
                names = archive.namelist()
                self.assertIn("rakshak/Makefile", names)
                self.assertFalse(any("private" in name or "big.js" in name or name == "rakshak/.env" for name in names))
            (root / "README.md").write_text("sk" + "-" + "x" * 32)
            with self.assertRaisesRegex(ValueError, "possible credential"):
                check(root)

    def test_large_files_bounded_and_unchanged_cache_reused(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp) / "fixture")
            root = Path(fixture["repo"])
            (root / "large.js").write_text("x" * (MAX_FILE_BYTES + 1))
            git(root, "add", ".")
            git(root, "commit", "-m", "large fixture")
            index = Index(root)
            _, _, stats = index.select(fixture["issue"])
            self.assertEqual(stats["skipped_files"], 1)
            self.assertEqual(stats["skipped_bytes"], MAX_FILE_BYTES + 1)
            with patch.object(Path, "open", side_effect=AssertionError("unchanged files should use cache")):
                index.refresh()
            self.assertGreater(index.cache_hits, 0)

    def test_live_patch_available_before_candidate_verification(self):
        with tempfile.TemporaryDirectory() as tmp:
            fixture = create_fixture(Path(tmp) / "fixture")
            output = Path(tmp) / "result"
            observed = []
            def event(record):
                if record["event"] == "edited":
                    observed.append((output / "candidate.patch").read_text())
            args = argparse.Namespace(**fixture, output=str(output), adapter=None,
                                      attempts=2, seconds=20, command_seconds=3,
                                      tokens=12000, quiet=True, on_event=event)
            self.assertEqual(run(args), 0)
            self.assertTrue(observed[0].startswith("diff --git"))
            self.assertEqual(git(Path(fixture["repo"]), "status", "--porcelain"), "")


class TUITests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.settings = replace(Settings.from_env({}), data=self.root / "runs")

    async def test_launch_small_and_large_no_key_or_repo_mutation(self):
        for size in ((80, 24), (140, 46)):
            workspace = self.root / ("work-" + str(size[0]))
            workspace.mkdir()
            app = RakshakTUI(workspace=workspace, settings=self.settings)
            async with app.run_test(size=size) as pilot:
                await pilot.pause()
                self.assertFalse((workspace / ".git").exists())
                self.assertEqual(app.query_one("#model", Input).value, "deepseek-v4-pro")
                self.assertFalse(app.query_one("#run", Button).disabled)
                for name in ("issue", "actions", "views", "pipeline", "errors"):
                    region = app.query_one("#" + name).region
                    self.assertGreater(region.width, 0)
                    self.assertLessEqual(region.right, size[0])
                    self.assertLessEqual(region.bottom, size[1])

    async def test_demo_automatic_modification_pipeline_and_patch(self):
        app = RakshakTUI(workspace=self.root, settings=self.settings)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#demo")
            for _ in range(100):
                await pilot.pause(.1)
                if app.finished:
                    break
            self.assertIsNotNone(app.finished)
            job = app.store.detail(app.selected)
            self.assertEqual(job["status"], "verified_candidate")
            self.assertTrue(job["patch"])
            self.assertEqual(app.stage, 5)
            self.assertTrue(app.query_one("#apply", Button).disabled)
            self.assertFalse(app.query_one("#run", Button).disabled)
            self.assertTrue(any(event["event"] == "edited" for event in job["events"]))
            self.assertTrue(app.query_one("#errors").lines)
            await pilot.press("ctrl+p")
            await pilot.pause(.2)
            self.assertEqual(app.query_one("#views", TabbedContent).active, "patch-tab")
            self.assertTrue(app.query_one("#patch").lines)

    async def test_live_run_requires_runtime_key_and_does_not_execute_issue(self):
        app = RakshakTUI(workspace=self.root, settings=self.settings)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#issue", TextArea).load_text("touch should-not-exist")
            await pilot.click("#run")
            for _ in range(30):
                await pilot.pause(.1)
                if not app.busy:
                    break
            self.assertFalse(app.busy)
            self.assertIn("AI_API_KEY", str(app.query_one("#run-status", Static).render()))
            self.assertFalse((self.root / "should-not-exist").exists())
            self.assertIsNone(app.store.active)

    async def test_apply_requires_explicit_confirmation(self):
        app = RakshakTUI(workspace=self.root, settings=self.settings)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#apply", Button).disabled = False
            await pilot.click("#apply")
            self.assertIsInstance(app.screen, ConfirmApply)
            await pilot.click("#dismiss")
            self.assertFalse(isinstance(app.screen, ConfirmApply))


if __name__ == "__main__":
    unittest.main()
