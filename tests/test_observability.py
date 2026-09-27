import json
from pathlib import Path
import re
import tempfile
import unittest

from harness.server import Store


class ObservabilityTests(unittest.TestCase):
    def test_dashboard_metric_references_and_datasource(self):
        root = Path(__file__).resolve().parents[1]
        dashboard = json.loads((root / "observability/grafana/dashboards/harness.json").read_text())
        self.assertEqual(dashboard["uid"], "harness")
        ids = [panel["id"] for panel in dashboard["panels"]]
        self.assertEqual(len(ids), len(set(ids)))
        with tempfile.TemporaryDirectory() as tmp:
            metrics = Store(tmp).metrics()
        exported = set(re.findall(r"^([a-z_]+)(?:\{| )", metrics, re.MULTILINE))
        exported.update(re.findall(r"^# TYPE ([a-z_]+) counter", metrics, re.MULTILINE))
        for panel in dashboard["panels"]:
            self.assertEqual(panel["datasource"]["uid"], "harness-prometheus")
            for target in panel["targets"]:
                for name in re.findall(r"harness_[a-z_]+", target["expr"]):
                    self.assertIn(name, exported)


if __name__ == "__main__":
    unittest.main()
