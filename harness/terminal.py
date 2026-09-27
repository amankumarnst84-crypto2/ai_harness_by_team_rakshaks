"""Interactive terminal workspace. No HTTP listener or browser is started."""
import argparse
import getpass
import json
import os
from pathlib import Path
import re
import shlex
import sys
import time

from .api_adapter import BASES, KEYS, call_api
from .safety import Stop, git
from .server import Store

DEFAULT_DATA = Path(__file__).resolve().parents[1] / ".harness-data"
HELP = """Type a bug description to start debugging.

  /connect [provider] [model]  Groq, DeepSeek, Qwen, or compatible API
  /model MODEL                Change model on the current endpoint
  /models                     List model IDs from the provider
  /adapter JSON               Use a custom adapter command array
  /repo PATH                  Select a clean Git repository
  /test COMMAND               Verification command (shell quoting or JSON argv)
  /budget TOKENS              Set total estimated token budget
  /attempts N                 Set maximum model calls
  /run [ISSUE]                Run an issue, or retry the current issue
  /follow REQUIREMENT         Rerun with an additional requirement
  /new                        Clear the current issue
  /demo                       Fixed fixture response, real Git edits/tests
  /status                     Show configuration and selected run
  /history                    List saved runs
  /show RUN_ID                Select a previous run
  /patch                      Review the selected patch
  /tests                      Show baseline and candidate test output
  /context                    Show source selection and token evidence
  /apply                      Apply a reviewed, passing patch to its clean base
  /metrics                    Print Prometheus metrics
  /help                       Show these commands
  /quit                       Exit

Ctrl+C during a run stops the adapter/test process and saves the evidence.
API keys stay in memory; enter them only at the hidden key prompt.
"""


def terminal_text(value):
    text = str(value)
    text = re.sub(r"\x1b\][^\x07]*(?:\x07|\x1b\\)", "", text)
    text = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    return re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)


def argv(value):
    result = json.loads(value) if value.lstrip().startswith("[") else shlex.split(value)
    if not isinstance(result, list) or not result or not all(isinstance(s, str) and s for s in result):
        raise ValueError("Use a nonempty command or a JSON string array")
    return result


class Terminal:
    def __init__(self, store, reader=input, writer=print, secret_reader=getpass.getpass, color=False):
        self.store, self.read, self.write, self.read_secret = store, reader, writer, secret_reader
        self.color = color
        self.repo, self.test, self.issue, self.selected = None, None, "", None
        self.tokens, self.attempts = 12000, 5
        self.key_env = None

    def say(self, text="", kind=None):
        text = terminal_text(text)
        colors = {"title": "1;36", "ok": "32", "warn": "33", "error": "31", "muted": "90"}
        if self.color and kind in colors:
            text = "\033[" + colors[kind] + "m" + text + "\033[0m"
        self.write(text)

    def prompt(self, label, default=""):
        value = self.read(label + (" [" + default + "]" if default else "") + ": ").strip()
        return value or default

    def connect(self, value):
        parts = shlex.split(value)
        if len(parts) > 2:
            raise ValueError("Use /connect PROVIDER MODEL; enter credentials at the hidden prompt")
        provider = parts[0] if parts else self.prompt("Provider", "groq")
        if provider not in KEYS:
            raise ValueError("Provider must be groq, deepseek, qwen, or compatible")
        base = BASES.get(provider) or self.prompt("API base URL supplied by your provider/college")
        model = parts[1] if len(parts) > 1 else self.prompt("Exact model ID")
        key_name = self.key_env or "AI_API_KEY"
        key = os.environ.get(key_name, "")
        current = self.store.adapter_env
        if not key and current.get("HARNESS_PROVIDER") == provider and current.get("HARNESS_API_BASE") == base:
            key = current.get("HARNESS_API_KEY", "")
        if not key:
            if self.read_secret is getpass.getpass and not sys.stdin.isatty():
                raise ValueError("Export " + key_name + " or use an interactive terminal for the hidden key prompt")
            key = self.read_secret("API key (hidden, memory only; blank for local endpoint): ")
        self.store.configure({"provider": provider, "api_base": base, "model": model, "api_key": key})
        self.say("Configured " + provider + " / " + model + ". No generation call made yet.", "ok")

    def choose_repo(self, value):
        root = Path(value or self.prompt("Repository path")).expanduser().resolve()
        if not root.is_dir() or Path(git(root, "rev-parse", "--show-toplevel").strip()).resolve() != root:
            raise ValueError("Choose the root of an existing Git repository")
        if root == self.store.directory or root in self.store.directory.parents:
            raise ValueError("Run data must be outside this repository; restart with chat --data /outside/path")
        self.repo = str(root)
        self.issue = ""
        self.say("Repository: " + self.repo)

    def status(self):
        config = self.store.public_config()
        self.say("Repository  " + (self.repo or "not selected"))
        self.say("Model       " + (config["model"] if config["model_available"] else "not connected"))
        self.say("Tests       " + (shlex.join(self.test) if self.test else "not configured"))
        self.say("Budget      {:,} estimated tokens / {} attempts".format(self.tokens, self.attempts))
        self.say("Evidence    " + str(self.store.directory))
        if self.selected:
            job = self.store.detail(self.selected)
            self.say("Selected    " + self.selected + " / " + job["status"])

    def selected_job(self):
        if not self.selected:
            raise ValueError("No run selected. Use /run, /demo, or /show RUN_ID")
        return self.store.detail(self.selected)

    def event(self, event):
        kind = event["event"]
        stamp = "[{:.1f}s] ".format(event["elapsed_seconds"])
        if kind == "started":
            self.say(stamp + "Isolated checkout / " + event["mode"], "muted")
        elif kind == "test_started":
            self.say(stamp + "Running " + event["phase"] + " verification...", "muted")
        elif kind == "test":
            passed = event["verification"] == "passed"
            self.say(stamp + event["phase"].capitalize() + " tests: " + event["verification"].upper(), "ok" if passed else "warn")
        elif kind == "context":
            self.say(stamp + "Context: {} files indexed / {:,} estimated tokens selected".format(event["indexed_files"], event["selected_context_tokens_estimate"]), "muted")
        elif kind == "model_started":
            self.say(stamp + "Model call {}...".format(event["attempt"]))
        elif kind == "plan":
            self.say("\nAI > " + event["plan"], "title")
        elif kind == "edited":
            self.say(stamp + "Edited " + ", ".join(event["files"]))
        elif kind == "recovery":
            self.say(stamp + "Focused recovery: " + event["focus_file"] + " (fresh source, minimal edit)", "warn")
        elif kind == "read":
            self.say(stamp + "Model requested additional source ranges.", "muted")
        elif kind in {"edit_rejected", "response_rejected", "stopped"}:
            self.say(stamp + event["detail"], "warn")

    def summary(self, job):
        report = job.get("report") or {}
        self.say("\n" + job["status"].upper().replace("_", " "), "ok" if job["status"] in {"verified_candidate", "tests_pass_candidate"} else "warn")
        self.say("Tokens: {:,} estimated / {:,} budget | Calls: {} | Time: {:.1f}s".format(report.get("estimated_tokens", 0), report.get("token_budget", job.get("tokens", 0)), report.get("model_calls", 0), report.get("elapsed_seconds", 0)))
        if report.get("provider_usage_complete"):
            self.say("Provider usage: {:,} input + {:,} output tokens".format(report["provider_input_tokens"], report["provider_output_tokens"]))
        used = max(report.get("estimated_tokens", 0), report.get("provider_input_tokens", 0) + report.get("provider_output_tokens", 0))
        budget = report.get("token_budget", job.get("tokens", 0))
        self.say("Budget accounting: {:,} used / {:,}; {:,} remaining (max of estimate and reported usage).".format(used, budget, max(0, budget - used)))
        if report.get("error"):
            self.say(report["error"], "error")
        if job["status"] == "tests_pass_candidate":
            self.say("Baseline also passed; this command did not reproduce the reported bug.", "warn")
        self.say("Evidence: " + str(self.store.directory / job["id"] / "result"), "muted")
        self.say("/patch  /tests  /context  /follow REQUIREMENT", "muted")

    def start(self, issue="", demo=False):
        if not demo:
            if not self.repo:
                self.choose_repo("")
            if not self.test:
                self.test = argv(self.prompt("Verification command"))
            if not self.store.adapter:
                self.connect("")
            issue = issue or self.issue or self.prompt("Describe the bug")
            if not issue.strip():
                raise ValueError("Describe the bug first")
            self.issue = issue
        else:
            self.say("SIMULATION: predetermined model response, real checkout and tests.", "warn")
        identity = self.store.start({"mode": "demo" if demo else "model", "repo": self.repo,
                                     "test": self.test, "issue": issue, "tokens": self.tokens,
                                     "attempts": self.attempts})
        self.selected = identity
        self.say("\nRun " + identity + "  (Ctrl+C to stop)", "title")
        seen, stopping = 0, False
        while True:
            try:
                job = self.store.detail(identity)
                for record in job["events"][seen:]:
                    self.event(record)
                seen = len(job["events"])
                if job["status"] != "running":
                    self.summary(job)
                    return job
                time.sleep(.05)
            except KeyboardInterrupt:
                if not stopping:
                    try:
                        self.store.cancel(identity)
                    except ValueError:
                        pass
                    stopping = True
                    self.say("Stopping the active process; saving evidence...", "warn")

    def apply(self):
        job = self.selected_job()
        report = job.get("report") or {}
        if job["mode"] == "demo":
            raise ValueError("Simulation patches are for inspection only")
        if report.get("status") not in {"verified_candidate", "tests_pass_candidate"} or not job["patch"]:
            raise ValueError("Only a nonempty candidate with passing tests can be applied")
        root = Path(job["repo"])
        if git(root, "rev-parse", "HEAD").strip() != report.get("base_commit"):
            raise ValueError("Repository HEAD changed; rerun against the current commit")
        if git(root, "status", "--porcelain", "--untracked-files=all").strip():
            raise ValueError("Repository has local changes; patch was not applied")
        path = self.store.directory / job["id"] / "result/candidate.patch"
        git(root, "apply", "--check", str(path))
        git(root, "apply", str(path))
        self.say("Patch applied to " + str(root) + ". Changes are uncommitted.", "ok")

    def dispatch(self, line):
        if not line.startswith("/"):
            self.start(line)
            return True
        command, _, value = line.partition(" ")
        value = value.strip()
        if command in {"/quit", "/exit"}:
            return False
        if command == "/help":
            self.say(HELP)
        elif command == "/connect":
            self.connect(value)
        elif command == "/adapter":
            self.store.adapter = argv(value)
            self.store.adapter_env = {}
            self.say("Custom adapter configured.", "ok")
        elif command == "/model":
            env = self.store.adapter_env
            if not env or not value:
                raise ValueError("Connect a provider first, then use /model EXACT_MODEL_ID")
            self.store.configure({"provider": env["HARNESS_PROVIDER"], "api_base": env["HARNESS_API_BASE"], "model": value})
            self.say("Model: " + value, "ok")
        elif command == "/models":
            env = self.store.adapter_env
            if not env:
                raise ValueError("Use /connect first")
            result = call_api(env["HARNESS_API_BASE"], env["HARNESS_API_KEY"], "/models")
            self.say("\n".join(item["id"] for item in result.get("data", []) if isinstance(item, dict) and isinstance(item.get("id"), str)))
        elif command == "/repo":
            self.choose_repo(value)
        elif command == "/test":
            self.test = argv(value or self.prompt("Verification command"))
            self.say("Tests: " + shlex.join(self.test))
        elif command in {"/budget", "/attempts"}:
            number = int(value)
            low, high = (1000, 200000) if command == "/budget" else (1, 20)
            if not low <= number <= high:
                raise ValueError("Value must be between {} and {}".format(low, high))
            setattr(self, "tokens" if command == "/budget" else "attempts", number)
            self.status()
        elif command == "/run":
            self.start(value)
        elif command == "/follow":
            job = self.selected_job()
            if job["mode"] == "demo" or not value:
                raise ValueError("Select a real model run and use /follow ADDITIONAL_REQUIREMENT")
            self.repo, self.test = job["repo"], job["test"]
            self.start(job["issue"] + "\n\nAdditional requirement: " + value)
        elif command == "/new":
            self.issue = ""
            self.say("Current issue cleared. Repository and model retained.")
        elif command == "/demo":
            self.start(demo=True)
        elif command == "/status":
            self.status()
        elif command == "/history":
            jobs = self.store.summaries()
            if not jobs:
                self.say("No saved runs.")
            for job in jobs[:30]:
                self.say("{}  {:22}  {}  {}".format(job["id"], job["status"], job.get("model", job["mode"]), job["issue"][:90]))
        elif command == "/show":
            job = self.store.detail(value)
            self.selected = value
            self.summary(job)
        elif command == "/patch":
            patch = self.selected_job()["patch"]
            if not patch:
                self.say("No patch available.")
            for row in patch.splitlines():
                self.say(row, "ok" if row.startswith("+") else "error" if row.startswith("-") else None)
        elif command == "/tests":
            for event in self.selected_job()["events"]:
                if event["event"] == "test":
                    self.say(event["phase"].upper() + " / " + event["verification"].upper(), "title")
                    self.say(event["result"].get("stdout", "") + event["result"].get("stderr", ""))
        elif command == "/context":
            for event in self.selected_job()["events"]:
                if event["event"] == "context":
                    self.say("Attempt {}: {:,} selected / {:,} full-source estimated tokens".format(event["attempt"], event["selected_context_tokens_estimate"], event["eligible_full_source_tokens_estimate"]))
                    self.say("\n".join(dict.fromkeys(event["paths"])))
        elif command == "/apply":
            self.apply()
        elif command == "/metrics":
            self.say(self.store.metrics())
        else:
            raise ValueError("Unknown command. Use /help")
        return True

    def loop(self):
        self.say("\nAI HARNESS / TERMINAL", "title")
        self.say("Groq + Qwen + DeepSeek | bounded tokens | test-verified patches", "muted")
        self.status()
        self.say("\n/connect  /repo  /test  then describe the bug. /demo runs without a key.", "muted")
        while True:
            try:
                line = self.read("\nharness > ").strip()
                if line and not self.dispatch(line):
                    break
            except EOFError:
                break
            except KeyboardInterrupt:
                self.say("Input cancelled. /quit to exit.", "muted")
            except (ValueError, KeyError, OSError, Stop) as exc:
                self.say(str(exc), "error")
        self.store.adapter_env.clear()
        self.say("Session ended. Run evidence saved.", "muted")


def main(arguments=None):
    parser = argparse.ArgumentParser(description="AI Harness interactive terminal")
    parser.add_argument("--repo")
    parser.add_argument("--test", help="Quoted command or JSON argv array")
    parser.add_argument("--provider", choices=list(KEYS), default=os.environ.get("AI_PROVIDER"))
    parser.add_argument("--model", default=os.environ.get("AI_MODEL", "deepseek-v4-pro"))
    parser.add_argument("--api-base", default=os.environ.get("AI_BASE_URL"))
    parser.add_argument("--api-key-env")
    parser.add_argument("--adapter", help="Custom adapter command or JSON argv")
    parser.add_argument("--data", default=os.environ.get("HARNESS_DATA_DIR", str(DEFAULT_DATA)))
    parser.add_argument("--tokens", type=int, default=12000)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--plain", action="store_true", help="Disable colors; allow scripted stdin")
    args = parser.parse_args(arguments)
    if not args.provider and not args.adapter and os.environ.get("AI_API_KEY"):
        args.provider = "deepseek"
    if not args.plain and not sys.stdin.isatty():
        parser.error("Interactive mode requires a terminal; use chat --plain for scripted input or batch CLI flags")
    if not 1000 <= args.tokens <= 200000 or not 1 <= args.attempts <= 20:
        parser.error("Use 1000-200000 tokens and 1-20 attempts")
    if args.adapter and args.provider:
        parser.error("Choose an API provider or a custom adapter, not both")
    terminal = Terminal(Store(args.data), color=not args.plain and sys.stdout.isatty() and "NO_COLOR" not in os.environ)
    terminal.tokens, terminal.attempts, terminal.key_env = args.tokens, args.attempts, args.api_key_env
    try:
        if args.repo:
            terminal.choose_repo(args.repo)
        if args.test:
            terminal.test = argv(args.test)
        if args.adapter:
            terminal.store.adapter = argv(args.adapter)
        if args.provider:
            key_name = args.api_key_env or "AI_API_KEY"
            key = os.environ.get(key_name, "")
            if not key:
                if not sys.stdin.isatty():
                    parser.error("Export " + key_name + " before scripted execution")
                key = getpass.getpass("API key (hidden; memory only): ")
            terminal.store.configure({"provider": args.provider, "api_base": args.api_base or BASES.get(args.provider, ""), "model": args.model or terminal.prompt("Exact model ID"), "api_key": key})
        terminal.loop()
    except (ValueError, Stop, OSError, EOFError) as exc:
        parser.exit(2, str(exc) + "\n")
