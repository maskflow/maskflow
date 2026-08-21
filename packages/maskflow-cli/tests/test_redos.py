from __future__ import annotations

import pytest
from maskflow_cli.config import redos
from maskflow_cli.config.redos import (
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


def test_probe_rejects_on_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    # An unreasonably small budget makes even a trivial pattern "time out"
    # against child-process spawn overhead alone -- a deterministic way to
    # exercise the timeout->rejection path without a genuinely catastrophic
    # regex (which the static check would normally catch first anyway).
    monkeypatch.setattr(redos, "_PROBE_TIMEOUT_SECONDS", 0.0001)
    with pytest.raises(UnsafePatternError, match="took longer than"):
        redos._adversarial_probe(r"abc")
