"""Run identical task definitions through different model endpoints in this harness."""
import argparse
from collections import defaultdict
import json
import os
from pathlib import Path
import re
import sys

from harness.api_adapter import configuration, KEYS
from harness.engine import run
from harness.safety import Stop


def evaluate(manifest, output, tokens=12000, attempts=5, seconds=300):
    if not isinstance(manifest, dict) or not isinstance(manifest.get("models"), list) or not isinstance(manifest.get("tasks"), list):
        raise ValueError("Manifest must contain models and tasks arrays")
    models, tasks = manifest["models"], manifest["tasks"]
    if not models or not tasks:
        raise ValueError("At least one model and one task are required")
    for items in (models, tasks):
        names = []
        for item in items:
            if not isinstance(item, dict) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", item.get("id", "")):
                raise ValueError("Every model/task requires a unique alphanumeric id")
            names.append(item["id"])
        if len(names) != len(set(names)):
            raise ValueError("Duplicate model/task id")
    configured = []
    for model in models:
        provider = model.get("provider", "compatible")
        env = configuration(provider, model.get("api_base"), model.get("model", ""), os.environ.get(model.get("api_key_env", "AI_API_KEY"), ""))
        configured.append((model, env))
    for task in tasks:
        if not isinstance(task.get("repo"), str) or not Path(task["repo"]).is_dir() or not isinstance(task.get("issue"), str) or not task["issue"].strip():
            raise ValueError("Task requires an existing repository path and issue")
        if not isinstance(task.get("test"), list) or not task["test"] or not all(isinstance(a, str) and a for a in task["test"]):
            raise ValueError("Every task requires a test command array")
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    summary = {"evaluation": "model_comparison_within_ai_harness", "tokens_per_task": tokens,
               "attempts_per_task": attempts, "seconds_per_task": seconds, "rows": rows,
               "warning": "Verification is against the supplied command, not an independent held-out benchmark. No competitor agent is evaluated."}
    for model, env in configured:
        for task in tasks:
            destination = output / model["id"] / task["id"]
            args = argparse.Namespace(repo=task["repo"], issue=task["issue"], test=task["test"], mock=None,
                                      adapter=[sys.executable, str(Path(__file__).parent / "harness/api_adapter.py")],
                                      adapter_env=env, model_label=model["model"], output=str(destination), tokens=tokens,
                                      attempts=attempts, seconds=seconds, command_seconds=min(seconds, 120), quiet=True)
            try:
                code = run(args)
                report = json.loads((destination / "report.json").read_text())
            except (Stop, OSError, ValueError) as exc:
                code, report = 2, {"status": "error", "error": str(exc)}
            row = {"model_id": model["id"], "model": model["model"], "provider": model.get("provider", "compatible"),
                   "task_id": task["id"], "exit_code": code, "report": report}
            rows.append(row)
            (output / "summary.json").write_text(json.dumps(summary, indent=2))
    totals = defaultdict(lambda: {"tasks": 0, "verified_fixes": 0, "estimated_tokens": 0, "reported_tokens": 0, "complete_usage_tasks": 0, "elapsed_seconds": 0})
    for row in rows:
        total, report = totals[row["model_id"]], row["report"]
        total["tasks"] += 1
        total["verified_fixes"] += report["status"] == "verified_candidate"
        total["estimated_tokens"] += report.get("estimated_tokens", 0)
        total["reported_tokens"] += report.get("provider_input_tokens", 0) + report.get("provider_output_tokens", 0)
        total["complete_usage_tasks"] += bool(report.get("provider_usage_complete"))
        total["elapsed_seconds"] += report.get("elapsed_seconds", 0)
    summary["totals"] = dict(totals)
    (output / "summary.json").write_text(json.dumps(summary, indent=2))
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest")
    parser.add_argument("--output", required=True, help="New output directory")
    parser.add_argument("--tokens", type=int, default=12000)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--seconds", type=int, default=300)
    args = parser.parse_args()
    if min(args.tokens, args.attempts, args.seconds) <= 0:
        parser.error("Budgets must be positive")
    try:
        summary = evaluate(json.loads(Path(args.manifest).read_text()), args.output, args.tokens, args.attempts, args.seconds)
    except (OSError, ValueError) as exc:
        parser.exit(2, str(exc) + "\n")
    print(json.dumps(summary["totals"], indent=2))
    return 0 if all(row["report"]["status"] == "verified_candidate" for row in summary["rows"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
