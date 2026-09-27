"""One small real-provider check using only a generated, non-private fixture."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from harness.config import Settings
from harness.engine import run
from harness.fixtures import create_fixture
from harness.server import Store


def main():
    settings = Settings.from_env()
    if not settings.key:
        raise SystemExit("AI_API_KEY is missing from this terminal environment. No API call made.")
    identity = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6]
    base = ROOT / "build/live-check" / identity
    store = Store(base / "runs")
    settings.connect(store)
    fixture = create_fixture(base / "fixture")
    fixture["mock"] = None
    args = argparse.Namespace(**fixture, output=str(base / "result"), adapter=store.adapter,
                              adapter_env=store.adapter_env, model_label=settings.model,
                              attempts=2, seconds=180, command_seconds=90, tokens=8000,
                              context_chars=6000, max_output_tokens=1500, quiet=True)
    print("Live provider:", settings.provider, "| Exact model:", settings.model)
    print("Generated fixture only; at most 2 API calls. This may incur provider charges.")
    code = run(args)
    report = json.loads((base / "result/report.json").read_text())
    print("Outcome:", report["status"])
    print("Provider tokens:", report["provider_input_tokens"] + report["provider_output_tokens"])
    print("Report:", base / "result/report.json")
    if report.get("error"):
        print(report["error"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
