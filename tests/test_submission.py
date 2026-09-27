import argparse
import asyncio
from dataclasses import replace
import json
import os
from pathlib import Path
import tempfile
import threading
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile

from harness.config import Settings
from harness.engine import run
from harness.fixtures import create_fixture
from harness.retrieval import Index, MAX_FILE_BYTES
from harness.safety import git
from harness.server import Store
from harness.tui import RakshakTUI, ConfirmApply, runtime_settings
from textual.widgets import Button, Input, Static, TextArea, TabbedContent
from tools.submission import check, package, source_files


class SubmissionTests(unittest.TestCase):
    def test_runtime_prompt_does_not_persist_key_in_environment(self):
        with patch.dict(os.environ, {}, clear=True), patch("harness.tui.sys.stdin.isatty", return_value=True), patch("harness.tui.getpass.getpass", return_value="temporary-test-credential"):
            settings = runtime_settings()
            self.assertEqual(settings.key, "temporary-test-credential")
            self.assertNotIn("AI_API_KEY", os.environ)
            self.assertNotIn(settings.key, repr(settings))

    def test_existing_runtime_key_skips_prompt(self):
        with patch.dict(os.environ, {"AI_API_KEY": "existing-test-credential"}, clear=True), patch("harness.tui.getpass.getpass") as prompt:
            self.assertEqual(runtime_settings().key, "existing-test-credential")
            prompt.assert_not_called()

    def test_noninteractive_launch_never_prompts(self):
        with patch.dict(os.environ, {}, clear=True), patch("harness.tui.sys.stdin.isatty", return_value=False), patch("harness.tui.getpass.getpass") as prompt:
            self.assertEqual(runtime_settings().key, "")
            prompt.assert_not_called()

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
            metrics = str(app.query_one("#metrics", Static).render())
            self.assertIn("Budget", metrics)
            self.assertIn("Remaining", metrics)
            self.assertTrue(app.query_one("#errors").lines)
            errors = "".join(line.text for line in app.query_one("#errors").lines)
            self.assertNotIn("AssertionError", errors)
            self.assertIn("passed", errors)
            self.assertIn("OFFLINE SIMULATION", str(app.query_one("#run-status", Static).render()))
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

    async def test_stop_during_preparation_is_preserved(self):
        app = RakshakTUI(workspace=self.root, settings=self.settings)
        entered, release = threading.Event(), threading.Event()
        original = app.store.start

        def delayed_start(data, cancel=None):
            entered.set()
            release.wait(5)
            return original(data, cancel=cancel)

        async with app.run_test(size=(120, 40)) as pilot:
            with patch.object(app.store, "start", side_effect=delayed_start):
                app.begin(demo=True)
                try:
                    for _ in range(50):
                        await pilot.pause(.02)
                        if entered.is_set():
                            break
                    self.assertTrue(entered.is_set())
                    self.assertIsNone(app.store.active)
                    app.action_cancel()
                    self.assertTrue(app.cancel_requested.is_set())
                finally:
                    release.set()
                for _ in range(100):
                    await pilot.pause(.05)
                    if app.finished:
                        break
                self.assertIsNotNone(app.finished)
                job = app.store.detail(app.selected)
                self.assertEqual(job["status"], "cancelled")
                self.assertEqual(job["report"]["model_calls"], 0)

    async def test_history_replaces_stale_panels_and_workspace(self):
        app = RakshakTUI(workspace=self.root, settings=self.settings)
        async with app.run_test(size=(120, 40)) as pilot:
            app.begin(demo=True)
            for _ in range(100):
                await pilot.pause(.05)
                if app.finished:
                    break
            self.assertIsNotNone(app.finished)
            identity = app.selected
            job = app.store.detail(identity)
            for name in ("activity", "errors", "tests", "context"):
                app.query_one("#" + name).write("STALE_RUN_SENTINEL")
            app.query_one("#workspace-info", Static).update("wrong workspace")
            app.query_one("#model-status", Static).update("wrong model")
            app.on_input_submitted(SimpleNamespace(input=app.query_one("#history-select", Input), value=identity))
            await pilot.pause()
            self.assertIn(Path(job["repo"]).name, str(app.query_one("#workspace-info", Static).render()))
            self.assertIn("fixture", str(app.query_one("#model-status", Static).render()))
            self.assertEqual(app.query_one("#issue", TextArea).text, job["issue"])
            for name in ("activity", "errors", "tests", "context"):
                self.assertNotIn("STALE_RUN_SENTINEL", "".join(line.text for line in app.query_one("#" + name).lines))

    async def test_new_run_clears_previous_activity(self):
        app = RakshakTUI(workspace=self.root, settings=self.settings)
        async with app.run_test(size=(120, 40)) as pilot:
            app.log_message("PREVIOUS_RUN_FAILURE")
            app.begin(demo=True)
            for _ in range(100):
                await pilot.pause(.05)
                if app.finished:
                    break
            self.assertIsNotNone(app.finished)
            self.assertNotIn("PREVIOUS_RUN_FAILURE", "".join(line.text for line in app.query_one("#activity").lines))

    async def test_repo_only_run_and_static_apply_warning(self):
        fixture = create_fixture(self.root / "fixture")
        adapter = self.root / "offline_adapter.py"
        adapter.write_text("print(" + repr(Path(fixture["mock"]).read_text()) + ")\n")
        store = Store(self.root / "auto-runs", adapter=[sys.executable, str(adapter)])
        app = RakshakTUI(workspace=fixture["repo"], settings=self.settings, store=store)
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#test", Input).value = ""
            app.query_one("#issue", TextArea).load_text("")
            with patch.object(Settings, "connect", return_value=None):
                app.begin()
                for _ in range(150):
                    await pilot.pause(.05)
                    if app.finished:
                        break
            self.assertIsNotNone(app.finished)
            job = store.detail(app.selected)
            self.assertEqual(job["status"], "static_candidate")
            self.assertIsNone(job["test"])
            self.assertFalse(app.query_one("#apply", Button).disabled)
            self.assertIn("NOT verified", "".join(line.text for line in app.query_one("#errors").lines))
            await pilot.click("#apply")
            self.assertTrue(app.screen.static_only)
            await pilot.click("#dismiss")


if __name__ == "__main__":
    unittest.main()
