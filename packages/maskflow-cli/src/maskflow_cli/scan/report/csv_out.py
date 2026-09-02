"""ScanSummary -> CSV: the severity/breakdown table flattened, one row per
entity type, for spreadsheet pivots. (Provider/day cross-products stay in
the JSON output -- a single flat CSV keyed by every dimension is unwieldy
and mostly zeros.)"""

from __future__ import annotations

import csv
import io

from .summary import ScanSummary


def render_csv(summary: ScanSummary) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "entity_type",
            "severity",
            "instances",
            "distinct_values",
            "distinct_is_lower_bound",
            "estimated",
            "providers",
            "why_it_matters",
        ]
    )
    for r in summary.severity_rows:
        writer.writerow(
            [
                r.entity_type,
                r.severity,
                r.count,
                r.distinct,
                int(r.distinct_is_lower_bound),
                int(r.estimated),
                "; ".join(r.providers),
                r.why_it_matters,
            ]
        )
    return buf.getvalue()
