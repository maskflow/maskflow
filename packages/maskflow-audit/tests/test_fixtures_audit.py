"""The audit, measured against audit-fixtures/.

"Accuracy is MEASURED and published, never asserted" applied to the audit
itself: six realistic apps, each with a committed expected.json, and the
report must match. The fixtures earned their place immediately -- fixture
02 caught the factory-chain gap (a Chroma collection obtained from
`get_or_create_collection` was invisible), fixture 03 caught maskedness
not propagating through a prompt template's `.format()`, and fixture 04
caught the trace depth bound silently dropping column names that fixture
01 found for the same SQL.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from maskflow_audit.api import run_audit


def _fixture_dirs(root: Path) -> list[Path]:
    return sorted(p for p in root.iterdir() if p.is_dir())


def test_the_fixture_tree_exists(fixtures_root: Path) -> None:
    dirs = _fixture_dirs(fixtures_root)
    assert len(dirs) == 6, [p.name for p in dirs]
    for directory in dirs:
        assert (directory / "app.py").is_file()
        assert (directory / "expected.json").is_file()


@pytest.mark.parametrize(
    "name",
    [
        "01-fastapi-support-copilot",
        "02-rag-kyc-chroma",
        "03-langchain-langfuse",
        "04-copilot-masked",
        "05-gateway-routed",
        "06-split-and-indirect",
    ],
)
def test_fixture_matches_its_expected_report(fixtures_root: Path, name: str) -> None:
    directory = fixtures_root / name
    expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
    summary = run_audit(directory)

    assert len(summary.flows) == expected["flow_count"], (
        f"{name}: expected {expected['flow_count']} flow(s), got "
        f"{[(f.sink_id, f.masking_status) for f in summary.flows]}"
    )

    for actual, want in zip(summary.flows, expected["flows"], strict=True):
        assert actual.file == want["file"]
        assert actual.sink_id == want["sink_id"]
        assert actual.category == want["category"]
        assert actual.provider == want["provider"]
        assert actual.masking_status == want["masking_status"], (
            f"{name}/{actual.sink_id}: expected {want['masking_status']}, "
            f"got {actual.masking_status} ({actual.masking_reason})"
        )
        assert actual.confidence == want["confidence"]
        assert list(actual.payload_args) == want["payload_args"]
        assert sorted({s.kind for s in actual.sources}) == want["source_kinds"]
        assert sorted({s.detail for s in actual.sources if s.detail}) == want["source_details"]
        if "host" in want:
            assert actual.host == want["host"]


def test_the_leaking_fixtures_report_at_least_one_unmasked_flow(fixtures_root: Path) -> None:
    """Guards against the suite passing vacuously.

    If a refactor made discovery find nothing at all, every per-field
    assertion above would still hold for a fixture with zero expected
    flows -- so assert the verdicts separately.
    """
    for directory in _fixture_dirs(fixtures_root):
        expected = json.loads((directory / "expected.json").read_text(encoding="utf-8"))
        summary = run_audit(directory)
        unmasked = [f for f in summary.flows if f.masking_status == "unmasked"]
        if expected["verdict"] == "leaks":
            assert unmasked, f"{directory.name} is expected to leak but no flow is unmasked"
        else:
            assert not unmasked, (
                f"{directory.name} is expected clean but "
                f"{[(f.sink_id, f.masking_reason) for f in unmasked]} is unmasked"
            )


def test_the_fixtures_contain_no_identifier_values(fixtures_root: Path) -> None:
    """The fixtures reference column and field NAMES, never values.

    CLAUDE.md rule 2: no real PII is ever committed, and a fixture that
    carried even a synthetic Aadhaar-shaped constant would be a committed
    PII-shaped value. Values enter a fixture only through the canary
    harness, which generates them per run.
    """
    import re

    # Any run of 10+ digits (optionally space/dash grouped) would be an
    # identifier-shaped constant.
    identifier_shaped = re.compile(r"(?:\d[ -]?){10,}")
    for directory in _fixture_dirs(fixtures_root):
        source = (directory / "app.py").read_text(encoding="utf-8")
        assert not identifier_shaped.search(source), (
            f"{directory.name}/app.py contains an identifier-shaped constant"
        )
