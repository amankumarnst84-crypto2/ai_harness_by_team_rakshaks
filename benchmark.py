"""Reproducible retrieval/pipeline microbenchmark; NOT a model capability score."""
import argparse
import json
import re
from pathlib import Path
import tempfile

from harness.engine import run
from harness.fixtures import CASES, create_fixture
from harness.retrieval import Index, estimate, words
from harness.safety import git


def legacy_context(index, issue):
    terms = set(re.findall(r"[a-zA-Z_]{3,}", issue.lower()))
    ranked = sorted(index.files, key=lambda f: (-sum(3 * (w in f["path"].lower()) + (w in f["content"].lower()) for w in terms), f["path"]))
    selected, remaining = [], 16000
    for file in ranked:
        if remaining <= 0:
            break
        content = file["content"][:remaining]
        selected.append({"path": file["path"], "content": content, "truncated": len(content) < len(file["content"])})
        remaining -= len(content)
    return selected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="evidence/microbenchmark.json")
    args = parser.parse_args()
    rows = []
    with tempfile.TemporaryDirectory(prefix="harness-benchmark-") as tmp:
        for number, spec in enumerate(CASES):
            base = Path(tmp) / spec["name"]
            fixture = create_fixture(base, number, large=True)
            root = Path(fixture["repo"])
            index = Index(root)
            files, repo_map, stats = index.select(fixture["issue"])
            previous = legacy_context(index, fixture["issue"])
            options = argparse.Namespace(**fixture, output=str(base / "result"), adapter=None, attempts=3,
                                         seconds=30, command_seconds=5, tokens=12000, quiet=True)
            exit_code = run(options)
            report = json.loads((base / "result/report.json").read_text())
            git(root, "apply", "--check", str(base / "result/candidate.patch"))
            rows.append({"case": spec["name"], "model": "predetermined fixture response",
                         "legacy_prefix_tokens_estimate": estimate(previous),
                         "ranked_context_tokens_estimate": stats["selected_context_tokens_estimate"],
                         "eligible_full_source_tokens_estimate": stats["eligible_full_source_tokens_estimate"],
                         "legacy_contains_bug": any(spec["old"] in f["content"] for f in previous),
                         "ranked_contains_bug": any(spec["old"] in f["content"] for f in files),
                         "pipeline_exit_code": exit_code, "report": report,
                         "original_unchanged": not git(root, "status", "--porcelain").strip()})
    result = {"kind": "synthetic_retrieval_and_pipeline_microbenchmark", "real_model_evaluated": False,
              "notes": "Three deliberately simple bugs deep in long files, with unrelated source. Fixture repairs are prewritten. Token counts are UTF-8 bytes/4 estimates; not billing or SWE-bench scores.",
              "cases": rows}
    path = Path(args.output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return 0 if all(r["pipeline_exit_code"] == 0 and r["ranked_contains_bug"] and r["original_unchanged"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
