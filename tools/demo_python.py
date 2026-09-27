"""Create a fresh Python practice project with a failing bug and regression tests."""

import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = ROOT / "build" / "demo_python"

CALC_SOURCE = """\"\"\"Statistics module with calculations.\"\"\"


def mean(values):
    data = list(values)
    if not data:
        raise ValueError("Cannot calculate mean of empty data")
    return sum(data) / len(data)


def median(values):
    data = sorted(values)
    if not data:
        raise ValueError("Cannot calculate median of empty data")
    mid = len(data) // 2
    # BUG: For even-sized data, it returns data[mid] instead of the average of the two middle items!
    return data[mid]
"""

TEST_SOURCE = """\"\"\"Regression test suite for calc module.\"\"\"

import unittest
from calc import mean, median


class CalcTests(unittest.TestCase):
    def test_mean_basic(self):
        self.assertEqual(mean([1, 2, 3]), 2)
        self.assertEqual(mean([10, 20, 30, 40]), 25)

    def test_mean_empty(self):
        with self.assertRaises(ValueError):
            mean([])

    def test_median_odd(self):
        self.assertEqual(median([3, 1, 2]), 2)
        self.assertEqual(median([5, 1, 3, 9, 7]), 5)

    def test_median_even(self):
        # Even number of elements: average of 2 and 3 is 2.5
        self.assertEqual(median([1, 2, 3, 4]), 2.5)
        # Even number of elements: average of 10 and 20 is 15.0
        self.assertEqual(median([10, 20]), 15.0)

    def test_median_empty(self):
        with self.assertRaises(ValueError):
            median([])


if __name__ == "__main__":
    unittest.main()
"""

ISSUE_TEXT = (
    "Fix median() in calc.py: when given an even number of elements, "
    "median must return the float average of the two middle elements ((data[mid-1] + data[mid]) / 2). "
    "Preserve odd-length behavior, empty-list error handling, and mean() function. "
    "Fix calc.py only; do not modify tests."
)


def setup_demo(target=None):
    repo = target or DEMO_DIR
    if repo.exists():
        import shutil
        shutil.rmtree(repo)
    repo.mkdir(parents=True, exist_ok=True)

    (repo / "calc.py").write_text(CALC_SOURCE)
    (repo / "test_calc.py").write_text(TEST_SOURCE)
    (repo / "README.md").write_text("# Demo Python Project\nA tiny statistics module for debugging tests.\n")

    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Demo User"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "demo@localhost"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "Initial commit with buggy median"], cwd=repo, check=True)

    return repo


if __name__ == "__main__":
    repo_path = setup_demo()
    test_cmd = [sys.executable, "test_calc.py"]
    print("=" * 60)
    print("DEMO BUGGY PYTHON REPOSITORY CREATED!")
    print("=" * 60)
    print(f"Repository Path : {repo_path}")
    print(f"Verification Cmd: {json.dumps(test_cmd)}")
    print(f"Issue           : {ISSUE_TEXT}")
    print("=" * 60)
    print("\nCopy-paste these into your RAKSHAK Setup tab, or run:")
    print(f"python3 -m harness --repo '{repo_path}' --issue '{ISSUE_TEXT}' --test '{json.dumps(test_cmd)}' --output build/demo_result --provider deepseek")
