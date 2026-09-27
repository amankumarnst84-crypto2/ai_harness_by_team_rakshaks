"""RAKSHAK terminal workspace backed by the verified debugging engine."""
import argparse
import asyncio
from dataclasses import replace
import getpass
import json
import os
import threading
import sys
import warnings
from pathlib import Path

from rich.syntax import Syntax
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Label, RichLog, Static, TabbedContent, TabPane, TextArea

from .config import Settings
from .analysis import DEFAULT_ISSUE
from .safety import Stop, clean
from .server import Store
from .terminal import Terminal, argv as command_argv, terminal_text

STAGES = ("Baseline", "Retrieve", "Model", "Modify", "Verify", "Review")


class ConfirmApply(ModalScreen):
    DEFAULT_CSS = """
    ConfirmApply { align: center middle; background: $background 70%; }
    ConfirmApply > Vertical { width: 62; max-width: 95%; height: auto; padding: 1 2; background: $surface; border: solid $warning; }
    ConfirmApply Horizontal { height: 3; margin-top: 1; }
    """

    def __init__(self, static_only=False):
        super().__init__()
        self.static_only = static_only

    def compose(self):
        with Vertical():
            yield Static(("Only static checks passed. Runtime behavior is NOT verified. Apply anyway?" if self.static_only else "Apply this tested patch to the original repository?") + "\nChanges stay uncommitted. The repository must still be clean.")
            with Horizontal():
                yield Button("Cancel", id="dismiss")
                yield Button("Apply patch", id="confirm", variant="warning")

    def on_button_pressed(self, event):
        self.dismiss(event.button.id == "confirm")


class RakshakTUI(App):
    TITLE = "RAKSHAK | Verified AI Harness"
    ENABLE_COMMAND_PALETTE = False
    CSS = """
    Screen { background: #181a1b; color: #e2e7e5; }
    #header { height: 3; padding: 1 2; background: #24282a; color: #6fe3bd; text-style: bold; }
    #workspace { height: 1fr; }
    #sidebar { width: 34; min-width: 26; padding: 0 1; border-right: solid #42494b; }
    #main { width: 1fr; padding: 0 1; }
    .section { margin-top: 1; color: #6fe3bd; text-style: bold; height: auto; }
    .muted { color: #a3ada9; height: auto; }
    Label { margin-top: 1; height: 1; }
    Input { height: 3; background: #222628; }
    #workspace-info { height: 2; }
    #pipeline { height: 6; }
    #model-status { height: 2; }
    #metrics { height: 5; }
    #errors { height: 1fr; min-height: 4; border-top: solid #c28f5c; color: #ffb7ad; }
    #settings-scroll { padding: 0 1; }
    #issue { height: 5; border: solid #64716d; }
    #actions { height: 3; margin: 1 0; }
    #actions Button { min-width: 9; width: 1fr; margin-right: 1; }
    #views { height: 1fr; }
    TabPane { padding: 0; }
    RichLog { height: 1fr; background: #181a1b; }
    #history-select { height: 3; }
    #run-status { height: auto; min-height: 1; color: #e9cf85; }
    .compact #sidebar { width: 27; min-width: 27; }
    .compact #header { height: 2; padding: 0 1; }
    .compact #issue { height: 3; }
    .compact #actions { margin: 0; }
    .compact #main { padding: 0; }
    .compact #workspace-info, .compact #token-title, .compact #metrics, .compact #telemetry { display: none; }
    """
    BINDINGS = [
        Binding("ctrl+r", "run", "Run", priority=True),
        Binding("ctrl+x", "cancel", "Stop", priority=True),
        Binding("ctrl+p", "patch", "Patch", priority=True),
        Binding("ctrl+l", "focus_issue", "Issue", priority=True),
        Binding("ctrl+q", "safe_quit", "Quit", priority=True),
        Binding("ctrl+c", "cancel", "Stop", priority=True),
    ]

    def __init__(self, workspace=None, argv=None, settings=None, store=None, **kwargs):
        super().__init__(**kwargs)
        self.settings = settings or Settings.from_env()
        self.store = store or Store(self.settings.data)
        self.workspace_dir = Path(workspace or os.environ.get("HARNESS_REPO", Path.cwd())).expanduser().resolve()
        self.selected = None
        self.seen = 0
        self.finished = None
        self.busy = False
        self.quitting = False
        self.reviewing = False
        self.stage = -1
        self.cancel_requested = threading.Event()
        self.terminal = Terminal(self.store, writer=self.log_message)

    def compose(self) -> ComposeResult:
        yield Static("RAKSHAK  /  VERIFIED AI HARNESS", id="header")
        with Horizontal(id="workspace"):
            with Vertical(id="sidebar"):
                yield Static("WORKSPACE", classes="section")
                yield Static(self.workspace_dir.name, id="workspace-info", markup=False)
                yield Static(self.settings.model + "\nAI_API_KEY: " + ("configured" if self.settings.key else "missing"), id="model-status", markup=False)
                yield Static("PIPELINE", classes="section")
                yield Static("\n".join("[ ] " + stage for stage in STAGES), id="pipeline", markup=False)
                yield Static("TOKEN EVIDENCE", id="token-title", classes="section")
                yield Static("No run yet", id="metrics", markup=False)
                yield Static("ERRORS / FAILURES", classes="section")
                yield RichLog(id="errors", min_width=1, wrap=True, markup=False, max_lines=300)
                yield Static("Telemetry: saved reports\nGrafana: optional", id="telemetry", classes="muted")
            with Vertical(id="main"):
                yield Label("Issue / follow-up requirement")
                yield TextArea(os.environ.get("HARNESS_ISSUE", ""), id="issue")
                with Horizontal(id="actions"):
                    yield Button("Run", id="run", variant="success")
                    yield Button("Stop", id="stop", disabled=True)
                    yield Button("Offline Demo", id="demo")
                    yield Button("Apply", id="apply", disabled=True, variant="warning")
                yield Static("Ready", id="run-status", markup=False)
                with TabbedContent(id="views"):
                    with TabPane("Activity", id="activity-tab"):
                        yield RichLog(id="activity", min_width=40, wrap=True, markup=False, max_lines=2000)
                    with TabPane("Code Diff", id="patch-tab"):
                        yield RichLog(id="patch", wrap=False, markup=False, max_lines=6000)
                    with TabPane("Checks", id="tests-tab"):
                        yield RichLog(id="tests", min_width=1, wrap=True, markup=False, max_lines=4000)
                    with TabPane("Context", id="context-tab"):
                        yield RichLog(id="context", min_width=1, wrap=True, markup=False, max_lines=2000)
                    with TabPane("History", id="history-tab"):
                        yield Input(placeholder="Run ID + Enter", id="history-select")
                        yield RichLog(id="history", min_width=1, wrap=True, markup=False, max_lines=1000)
                    with TabPane("Setup", id="setup-tab"):
                        with VerticalScroll(id="settings-scroll"):
                            yield Label("Repository")
                            yield Input(str(self.workspace_dir), id="repo")
                            yield Label("Verification command (optional)")
                            yield Input(os.environ.get("HARNESS_TEST", ""), placeholder="Automatic static checks", id="test")
                            yield Label("Exact prescribed model ID")
                            yield Input(self.settings.model, id="model")
                            yield Static(self.settings.provider + "\n" + self.settings.base, classes="muted", markup=False)
                            yield Label("Token budget")
                            yield Input(str(self.settings.tokens), type="integer", id="budget")
                            yield Label("Max attempts")
                            yield Input(str(self.settings.attempts), type="integer", id="attempts")
        yield Footer()

    def on_mount(self):
        self.log_message("Ready. Candidate edits run in a disposable Git checkout; original files stay unchanged until Apply.")
        self.log_message("Verification commands execute local code. Use only trusted repositories and commands.")
        self.set_interval(.2, self.poll_run)
        self.refresh_history()
        self.query_one("#issue", TextArea).focus()

    def on_resize(self, event):
        self.set_class(event.size.width < 100 or event.size.height < 32, "compact")

    def log_message(self, value):
        self.query_one("#activity", RichLog).write(Text(terminal_text(clean(str(value), [self.settings.key]))))

    def show_error(self, value):
        message = terminal_text(clean(str(value), [self.settings.key]))
        self.query_one("#errors", RichLog).write(Text(message))
        self.query_one("#run-status", Static).update(message[:180])
        self.log_message(message)

    def set_busy(self, busy):
        self.busy = busy
        for name in ("run", "demo"):
            self.query_one("#" + name, Button).disabled = busy
        for name in ("repo", "test", "model", "budget", "attempts"):
            self.query_one("#" + name, Input).disabled = busy
        self.query_one("#stop", Button).disabled = not busy
        self.query_one("#apply", Button).disabled = True

    def action_focus_issue(self):
        self.query_one("#issue", TextArea).focus()

    def action_patch(self):
        self.query_one("#views", TabbedContent).active = "patch-tab"

    def on_tabbed_content_tab_activated(self, event):
        if event.pane.id == "patch-tab" and self.selected:
            self.call_after_refresh(self.render_patch, self.store.detail(self.selected).get("patch", ""))

    def action_run(self):
        self.begin(False)

    def begin(self, demo=False):
        if self.busy or self.reviewing:
            return
        values = {name: self.query_one("#" + name, Input).value for name in ("repo", "test", "model", "budget", "attempts")}
        issue = self.query_one("#issue", TextArea).text.strip()
        if not issue:
            issue = DEFAULT_ISSUE
        self.set_busy(True)
        self.cancel_requested.clear()
        self.selected, self.finished, self.seen, self.stage = None, None, 0, -1
        self.query_one("#pipeline", Static).update("\n".join("[ ] " + stage for stage in STAGES))
        self.query_one("#metrics", Static).update("Preparing run")
        self.query_one("#activity", RichLog).clear()
        self.query_one("#errors", RichLog).clear()
        self.query_one("#patch", RichLog).clear()
        self.query_one("#tests", RichLog).clear()
        self.query_one("#context", RichLog).clear()
        self.query_one("#run-status", Static).update("Preparing isolated run...")
        self.launch_run(values, issue, demo)

    @work(thread=True, exclusive=True, group="launch")
    def launch_run(self, values, issue, demo):
        try:
            tokens, attempts = int(values["budget"]), int(values["attempts"])
            if not demo:
                from .intake import resolve_issue
                issue = resolve_issue(issue, values.get("repo", "")).strip() or DEFAULT_ISSUE
                current = replace(self.settings, model=values["model"].strip())
                current.connect(self.store)
                selector = Terminal(self.store, writer=lambda _: None)
                selector.choose_repo(values["repo"])
                self.terminal.repo = selector.repo
                test = command_argv(values["test"]) if values["test"].strip() else None
            else:
                test = None
            identity = self.store.start({"mode": "demo" if demo else "model", "repo": self.terminal.repo,
                                         "test": test, "issue": issue, "tokens": tokens, "attempts": attempts}, cancel=self.cancel_requested)
            self.call_from_thread(self.started, identity, issue, demo)
        except (ValueError, OSError, Stop) as exc:
            self.call_from_thread(self.set_busy, False)
            self.call_from_thread(self.query_one("#metrics", Static).update, "Not started / 0 calls")
            self.call_from_thread(self.show_error, str(exc))
            if self.quitting:
                self.call_from_thread(self.exit)

    def started(self, identity, issue, demo):
        self.selected, self.seen, self.finished, self.stage = identity, 0, None, -1
        self.terminal.selected = identity
        job = self.store.detail(identity)
        self.query_one("#workspace-info", Static).update(Path(job["repo"]).name)
        self.query_one("#model-status", Static).update(job["model"] + ("\nSimulation" if demo else "\nAI_API_KEY: configured"))
        self.log_message("\nSIMULATION: fixed model response, real edits and tests." if demo else "\nYOU > " + issue)
        self.query_one("#run-status", Static).update("Running " + identity)
        if self.quitting:
            self.action_cancel()

    def stage_update(self, stage, done=False):
        self.stage = stage
        rows = [("[x] " if i < stage or done else "[>] " if i == stage else "[ ] ") + name for i, name in enumerate(STAGES)]
        self.query_one("#pipeline", Static).update("\n".join(rows))

    def consume(self, event):
        kind = event["event"]
        stage = {"context": 1, "model_started": 2, "edited": 3, "read": 1}
        if kind in {"test_started", "analysis_started"}:
            self.stage_update(0 if event["phase"] == "baseline" else 4)
        elif kind in stage:
            self.stage_update(stage[kind])
        self.terminal.event(event)
        if kind in {"edit_rejected", "response_rejected", "stopped", "audit_flagged"}:
            self.show_error(event.get("detail", event.get("reason", "Behavioral regression flagged")))
        if kind == "edited":
            self.render_patch(self.store.detail(self.selected).get("patch", ""))
        if kind == "analysis":
            text = event["phase"].upper() + " / " + event["verification"] + "\n" + json.dumps(event["result"], indent=2)
            if event.get("comparison"):
                text += "\nBEFORE / AFTER\n" + json.dumps(event["comparison"], indent=2)
            self.query_one("#tests", RichLog).write(Text(terminal_text(text)))
            self.query_one("#context", RichLog).write(Text(terminal_text(json.dumps(event["result"].get("local_dependencies", []), indent=2))))
            if event["result"]["diagnostics"]:
                self.query_one("#errors", RichLog).write(Text(terminal_text(text[-4000:])))
        if kind == "findings":
            if event.get("findings"):
                self.query_one("#errors", RichLog).write(Text(terminal_text("AI review findings:\n" + json.dumps(event["findings"], indent=2))))
        if kind == "test":
            result = event["result"]
            text = event["phase"].upper() + " / " + event["verification"] + "\n" + result.get("stderr", "") + result.get("stdout", "")
            self.query_one("#tests", RichLog).write(Text(terminal_text(text)))
            if event["verification"] != "passed":
                self.query_one("#errors", RichLog).write(Text(terminal_text(text[-4000:])))
        if kind == "context":
            self.query_one("#context", RichLog).write(Text(json.dumps(event, indent=2)))
            self.query_one("#metrics", Static).update(
                "Context ~{:,} tokens\nIndexed {} / skipped {}".format(event["selected_context_tokens_estimate"], event["indexed_files"], event["skipped_files"]))
        if kind == "model_started":
            self.query_one("#run-status", Static).update("Model call {} / ~{} input tokens".format(event["attempt"], event["input_tokens_estimate"]))

    def poll_run(self):
        if not self.selected or self.finished == self.selected:
            return
        job = self.store.detail(self.selected)
        for event in job["events"][self.seen:]:
            self.consume(event)
        self.seen = len(job["events"])
        if job["status"] == "running":
            return
        self.finished = self.selected
        self.set_busy(False)
        report = job.get("report") or {}
        success = job["status"] in {"verified_candidate", "tests_pass_candidate"}
        static_candidate = job["status"] == "static_candidate"
        if static_candidate or job["status"] == "review_complete":
            self.stage_update(5, True)
        if static_candidate:
            self.query_one("#errors", RichLog).clear()
            self.query_one("#errors", RichLog).write(Text("Static checks passed.\nRuntime behavior NOT verified."))
        if success:
            self.stage_update(5, True)
            self.query_one("#errors", RichLog).clear()
            self.query_one("#errors", RichLog).write(Text("Current candidate tests passed.\nBaseline failures retained in Checks."))
        label = job["status"].upper().replace("_", " ")
        self.query_one("#run-status", Static).update(("OFFLINE SIMULATION / " if job["mode"] == "demo" else "") + label)
        self.terminal.summary(job)
        self.render_patch(job.get("patch", ""))
        self.query_one("#apply", Button).disabled = not ((success or static_candidate) and job["mode"] != "demo" and bool(job.get("patch")))
        provider_tokens = report.get("provider_input_tokens", 0) + report.get("provider_output_tokens", 0)
        budget_used = max(report.get("estimated_tokens", 0), provider_tokens)
        self.query_one("#metrics", Static).update(
            "Budget {:,} / {:,}\nRemaining {:,}\nEstimated {:,}\nProvider {}\nCalls {} / {:.1f}s".format(
                budget_used, job["tokens"], max(0, job["tokens"] - budget_used),
                report.get("estimated_tokens", 0),
                "{:,}".format(provider_tokens) if report.get("provider_usage_complete") else "partial / unavailable",
                report.get("model_calls", 0), report.get("elapsed_seconds", 0)))
        self.refresh_history()
        if self.quitting:
            self.exit()

    def render_patch(self, patch):
        view = self.query_one("#patch", RichLog)
        view.clear()
        view.write(Syntax(terminal_text(patch), "diff", theme="monokai", word_wrap=False) if patch else Text("No candidate patch."), scroll_end=False)
        view.scroll_home(animate=False)

    def refresh_history(self):
        view = self.query_one("#history", RichLog)
        view.clear()
        for job in self.store.summaries()[:100]:
            view.write(Text(terminal_text("{}  {}  {}\n{}".format(job["id"], job["status"], job.get("model", ""), job["issue"][:180]))))

    def on_input_submitted(self, event):
        if event.input.id == "history-select" and not self.busy and not self.reviewing:
            identity = event.value.strip()
            try:
                self.store.detail(identity)
            except KeyError:
                self.show_error("Unknown run ID")
                return
            self.selected, self.terminal.selected, self.seen, self.finished = identity, identity, 0, None
            job = self.store.detail(identity)
            for name in ("activity", "errors", "tests", "context", "patch"):
                self.query_one("#" + name, RichLog).clear()
            self.stage = -1
            self.query_one("#pipeline", Static).update("\n".join("[ ] " + stage for stage in STAGES))
            self.query_one("#workspace-info", Static).update(Path(job["repo"]).name)
            self.query_one("#model-status", Static).update(job["model"] + "\nHistorical run")
            self.query_one("#issue", TextArea).load_text(job["issue"])
            self.poll_run()

    def action_cancel(self):
        if self.busy:
            self.cancel_requested.set()
            self.query_one("#run-status", Static).update("Stopping; saving evidence...")
        if self.store.active:
            try:
                self.store.cancel(self.store.active)
                self.query_one("#run-status", Static).update("Stopping; saving evidence...")
            except ValueError:
                pass

    def action_safe_quit(self):
        if self.busy:
            self.quitting = True
            self.action_cancel()
        else:
            self.exit()

    async def apply_confirmed(self, accepted):
        self.reviewing = False
        if not accepted:
            return
        self.set_busy(True)
        try:
            # Terminal.apply rechecks clean status and exact base commit.
            messages = []
            reviewer = Terminal(self.store, writer=messages.append)
            reviewer.selected = self.selected
            await asyncio.to_thread(reviewer.apply, allow_static=True)
            for message in messages:
                self.log_message(message)
            self.query_one("#run-status", Static).update("Patch applied. Original repository has uncommitted changes.")
        except (ValueError, Stop, OSError) as exc:
            self.show_error(exc)
        finally:
            self.set_busy(False)
            if self.quitting:
                self.exit()

    def on_button_pressed(self, event):
        action = event.button.id
        if action == "run":
            self.begin()
        elif action == "demo":
            self.begin(True)
        elif action == "stop":
            self.action_cancel()
        elif action == "apply" and not self.busy:
            self.action_patch()
            self.reviewing = True
            job = self.store.detail(self.selected) if self.selected else {}
            self.push_screen(ConfirmApply(static_only=job.get("status") == "static_candidate"), self.apply_confirmed)


def runtime_settings():
    settings = Settings.from_env()
    if settings.key or not sys.stdin.isatty():
        return settings
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("API key for this session (hidden; Enter = offline only): ").strip()
    except EOFError:
        key = ""
    except getpass.GetPassWarning:
        raise ValueError("Hidden input is unavailable. Export AI_API_KEY in the launching terminal.") from None
    return replace(settings, key=key)


def main(argv=None):
    parser = argparse.ArgumentParser(description="RAKSHAK text-only debugging TUI")
    parser.add_argument("--repo")
    parser.add_argument("--test", help="Trusted verification command")
    parser.add_argument("--data")
    args = parser.parse_args(argv)
    try:
        settings = runtime_settings()
        if args.data:
            settings = replace(settings, data=Path(args.data).expanduser())
        if args.test:
            os.environ["HARNESS_TEST"] = args.test
        RakshakTUI(workspace=args.repo, settings=settings).run()
    except (ValueError, OSError) as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
