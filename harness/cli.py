import argparse
import json
import math
import os
from pathlib import Path
import sys

from .engine import run
from .analysis import DEFAULT_ISSUE
from .retrieval import Index
from .safety import Stop, command, edit, git, redact, safe_path


def context(root, issue, limit=16000):
    return Index(root).select(issue, limit)[0]


def main():
    parser = argparse.ArgumentParser(description="AI Harness: token-conscious, test-verified debugging")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--issue", default=DEFAULT_ISSUE)
    parser.add_argument("--output", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--mock", help="JSON response fixture; explicitly simulated model")
    mode.add_argument("--adapter", type=json.loads, help="JSON argv array; receives request JSON path")
    mode.add_argument("--provider", choices=["groq", "deepseek", "qwen", "compatible"])
    parser.add_argument("--model", help="Exact provider or college model ID")
    parser.add_argument("--api-base", help="API base URL; required for Qwen or campus endpoints")
    parser.add_argument("--api-key-env", help="Environment variable containing the API key")
    parser.add_argument("--test", type=json.loads, help="JSON argv array; trusted command")
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--seconds", type=float, default=900)
    parser.add_argument("--command-seconds", type=float, default=60)
    parser.add_argument("--tokens", type=int, default=12000, help="Estimated token ceiling, not a billing guarantee")
    parser.add_argument("--context-chars", type=int, default=10000)
    parser.add_argument("--max-output-tokens", type=int, default=1500)
    args = parser.parse_args()
    from .intake import resolve_repo, resolve_issue
    try:
        args.repo = str(resolve_repo(args.repo))
    except Exception as exc:
        parser.error(f"Could not resolve repository '{args.repo}': {exc}")
    args.issue = resolve_issue(args.issue, args.repo)
    args.auto_check = not args.test
    if args.provider:
        from .api_adapter import configuration, KEYS
        try:
            args.adapter_env = configuration(args.provider, args.api_base, args.model or "", os.environ.get(args.api_key_env or "AI_API_KEY", ""))
            args.adapter = [sys.executable, str(Path(__file__).with_name("api_adapter.py"))]
            args.model_label = args.model
        except ValueError as exc:
            parser.error(str(exc))
    for name in ("attempts", "seconds", "command_seconds", "tokens", "context_chars", "max_output_tokens"):
        if not math.isfinite(getattr(args, name)) or getattr(args, name) <= 0:
            parser.error(name + " must be positive and finite")
    for value in (args.adapter, args.test):
        if value is not None and (not isinstance(value, list) or not value or not all(isinstance(x, str) and x for x in value)):
            parser.error("Commands must be nonempty JSON string arrays")
    try:
        raise SystemExit(run(args))
    except (Stop, OSError) as exc:
        parser.exit(2, str(exc) + "\n")

if __name__ == "__main__":
    main()
