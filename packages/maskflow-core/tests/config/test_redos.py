from __future__ import annotations

import pytest
from maskflow_core.config import redos
from maskflow_core.config.redos import (
    UnsafePatternError,
    check_pattern_safety,
    check_pattern_safety_with_probe,
    safe_match,
)


@pytest.mark.parametrize(
    "pattern",
    [
        r"(a+)+",
        r"(a*)*",
        r"(\d+)+",
        r"(a|a)*",
        r"(a|ab)*",
    ],
)
def test_rejects_classic_catastrophic_shapes(pattern: str) -> None:
    with pytest.raises(UnsafePatternError):
        check_pattern_safety(pattern)


@pytest.mark.parametrize(
    "pattern",
    [
        r"\bEMP-\d{6}\b",
        r"\bDEMO-\d+\b",
        r"[a-z]+@[a-z]+\.[a-z]{2,10}",
        r"(abc|def)",
        r"\d{1,20}",
    ],
)
def test_accepts_safe_patterns(pattern: str) -> None:
    check_pattern_safety(pattern)  # must not raise


def test_rejects_invalid_regex_syntax() -> None:
    with pytest.raises(UnsafePatternError):
        check_pattern_safety(r"(unclosed")


def test_safe_match_rejects_oversized_input() -> None:
    import re

    compiled = re.compile(r"abc")
    with pytest.raises(UnsafePatternError):
        safe_match(compiled, "x" * 20, max_len=10)


def test_safe_match_matches_within_cap() -> None:
    import re

    compiled = re.compile(r"abc")
    assert safe_match(compiled, "xxabcxx", max_len=10) is not None


def test_full_check_accepts_safe_pattern_through_probe() -> None:
    check_pattern_safety_with_probe(r"\bEMP-\d{6}\b")  # must not raise


def test_probe_rejects_slow_match(monkeypatch: pytest.MonkeyPatch) -> None:
    # A zero budget makes any *real* match time (measured in the child,
    # microseconds) exceed it -- deterministically exercises the slow-match
    # rejection path without a genuinely catastrophic regex.
    monkeypatch.setattr(redos, "_PROBE_MATCH_BUDGET_SECONDS", 0.0)
    with pytest.raises(UnsafePatternError, match="budget"):
        redos._adversarial_probe(r"abc")


def test_probe_rejects_genuine_catastrophic_backtracking(monkeypatch: pytest.MonkeyPatch) -> None:
    # `(0+){10}1` is a real evil regex the static shape check misses -- the
    # `{10}` counted repeat isn't an unbounded quantifier, so the inner `0+`
    # is never examined. Against a run of 0s with no trailing 1 it partitions
    # the run every possible way and backtracks catastrophically (>100s for a
    # 40-char probe locally). `0` is also the probe alphabet's lowest char, so
    # the generated probes actually hit it. The probe step is what has to
    # catch it; timeouts are trimmed so the hang is detected in ~1s.
    check_pattern_safety(r"(0+){10}1")  # sanity: the static layer lets it through
    monkeypatch.setattr(redos, "_PROBE_STARTUP_CEILING_SECONDS", 3.0)
    monkeypatch.setattr(redos, "_PROBE_HANG_TIMEOUT_SECONDS", 0.5)
    with pytest.raises(UnsafePatternError, match="did not complete"):
        redos._adversarial_probe(r"(0+){10}1")


def test_probe_measures_match_time_not_spawn_latency(monkeypatch: pytest.MonkeyPatch) -> None:
    # Regression for the CI flake: with the budget set well below typical
    # `spawn` startup (~0.1-1s) but far above an actual safe-pattern match
    # (~microseconds), a trivial pattern must still pass -- proving the
    # budget clock runs only around `compiled.search()` inside the child.
    monkeypatch.setattr(redos, "_PROBE_MATCH_BUDGET_SECONDS", 0.02)
    redos._adversarial_probe(r"\bEMP-\d{6}\b")  # must not raise
