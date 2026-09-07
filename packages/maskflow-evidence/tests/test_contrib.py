from __future__ import annotations

import json
import pathlib

CONTRIB = pathlib.Path(__file__).parent.parent / "contrib"


def test_grafana_dashboard_is_valid_json() -> None:
    data = json.loads((CONTRIB / "grafana-dashboard.json").read_text())
    assert data["title"]
    assert data["panels"]
    # references the new gateway metric
    exprs = json.dumps(data)
    assert "maskflow_evidence_emitted_total" in exprs
    assert "maskflow_detections_total" in exprs
