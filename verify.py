"""Run the standard-library suite and save reviewable test evidence."""
import contextlib
import json
from pathlib import Path
import unittest


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    evidence = root / "evidence"
    evidence.mkdir(exist_ok=True)
    with (evidence / "test-results.txt").open("w") as stream:
        with contextlib.redirect_stdout(stream), contextlib.redirect_stderr(stream):
            suite = unittest.defaultTestLoader.discover(str(root / "tests"))
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    summary = {"tests": result.testsRun, "passed": result.wasSuccessful(), "failures": len(result.failures), "errors": len(result.errors), "skipped": len(result.skipped)}
    (evidence / "test-summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    raise SystemExit(0 if result.wasSuccessful() else 1)
