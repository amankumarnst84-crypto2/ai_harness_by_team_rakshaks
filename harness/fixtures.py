"""Deterministic fixtures exercise the pipeline, never stand in for model evaluation."""
import json
from pathlib import Path
import sys

from .safety import git


CASES = [
    {"name": "invoice", "issue": "Fix invoice_total: a percentage discount must reduce the subtotal before tax is applied.",
     "source": "def invoice_total(subtotal, discount_percent, tax_percent):\n    discounted = subtotal * (1 + discount_percent / 100)\n    return round(discounted * (1 + tax_percent / 100), 2)\n",
     "check": "from invoice import invoice_total\nassert invoice_total(100, 20, 10) == 88, '20% discount then 10% tax should yield 88'\nassert invoice_total(100, 0, 0) == 100\nassert invoice_total(50, 100, 12) == 0\nprint('3 invoice regression checks passed')\n",
     "old": "subtotal * (1 + discount_percent / 100)", "new": "subtotal * (1 - discount_percent / 100)"},
    {"name": "pagination", "issue": "Fix page_count: partial pages must count as one page, while an empty result has zero pages.",
     "source": "def page_count(total, page_size):\n    if page_size <= 0:\n        raise ValueError('page_size must be positive')\n    return total // page_size\n",
     "check": "from pagination import page_count\nassert page_count(11, 10) == 2\nassert page_count(20, 10) == 2\nassert page_count(0, 10) == 0\nprint('3 pagination regression checks passed')\n",
     "old": "return total // page_size", "new": "return (total + page_size - 1) // page_size"},
    {"name": "ranges", "issue": "Fix contains_point in ranges.py: interval end is exclusive and start is inclusive.",
     "source": "def contains_point(start, end, point):\n    return start <= point <= end\n",
     "check": "from ranges import contains_point\nassert contains_point(2, 5, 2)\nassert contains_point(2, 5, 4)\nassert not contains_point(2, 5, 5)\nprint('3 interval regression checks passed')\n",
     "old": "return start <= point <= end", "new": "return start <= point < end"},
]


def create_fixture(base, case=0, large=False):
    base = Path(base)
    repo = base / "repo"
    spec = CASES[case]
    repo.mkdir(parents=True, exist_ok=False)
    git(repo, "init")
    git(repo, "config", "user.name", "Harness fixture")
    git(repo, "config", "user.email", "fixture@example.invalid")
    prefix = ""
    if large:
        prefix = "".join("# Historical record %04d: archived migration notes without active behavior.\n" % i for i in range(800))
    (repo / (spec["name"] + ".py")).write_text(prefix + spec["source"])
    (repo / "check.py").write_text(spec["check"])
    for i in range(24):
        (repo / ("archive_%02d.py" % i)).write_text("".join("# archived unrelated catalog row %04d value_%d\n" % (j, i) for j in range(100)))
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Deliberately failing debugging fixture")
    response = base / "response.json"
    response.write_text(json.dumps({"plan": "Fixture diagnosis: " + spec["issue"],
                                   "edits": [{"path": spec["name"] + ".py", "old": spec["old"], "new": spec["new"]}]}))
    return {"repo": str(repo), "mock": str(response), "issue": spec["issue"], "test": [sys.executable, "check.py"]}
