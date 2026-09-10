"""The regression gate: every installed integration must mask exactly what
the core engine masks, and round-trip byte-exact, over a 300-doc subset of
indiapii-v1.0. A divergence is a wrapper bug. Marked `benchmark` -- it runs
the full detect() pipeline per doc per adapter.
"""

from __future__ import annotations

import pytest

from bench.integrations.harness import run_parity

_EXPECTED = {"litellm", "langchain", "llamaindex", "mcp"}


@pytest.mark.benchmark
def test_every_integration_is_faithful_to_core() -> None:
    _doc_ids, tallies, skipped = run_parity(limit=300)

    # In the full-groups CI leg nothing should be skipped; locally, tolerate
    # a missing package but require at least langchain (a root dep).
    present = set(tallies)
    assert "langchain" in present, skipped
    assert present <= _EXPECTED

    failures = []
    for name, t in tallies.items():
        if t.detection_matches != t.docs:
            failures.append(
                f"{name}: detection parity {t.detection_matches}/{t.docs} "
                f"(wrapper-only {dict(t.extra_types)}, missed {dict(t.missed_types)})"
            )
        if t.roundtrip_exact != t.docs:
            failures.append(
                f"{name}: round-trip {t.roundtrip_exact}/{t.docs}, {t.roundtrip_fail_docs}"
            )
        if t.streaming_exact != t.docs:
            failures.append(
                f"{name}: streaming {t.streaming_exact}/{t.docs}, {t.streaming_fail_docs}"
            )

    assert not failures, "\n".join(failures)
