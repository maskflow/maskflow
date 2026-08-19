"""Guards against unbounded-regex backtracking blowing up on adversarial input (rule #3)."""

import time

import pytest
from maskflow_pack_intl.patterns import GENERIC_SECRET_ASSIGNMENT_RE

TIME_BUDGET_SECONDS = 1.0


@pytest.mark.benchmark
def test_generic_secret_pattern_stays_linear_on_adversarial_input():
    """A long word-run with no ':'/'=' used to make the two unbounded \\w*
    around the keyword alternation backtrack O(n^2) across every scan offset."""
    adversarial = "a" * 50_000 + " no separator here"

    start = time.monotonic()
    GENERIC_SECRET_ASSIGNMENT_RE.findall(adversarial)
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"GENERIC_SECRET_ASSIGNMENT_RE took {elapsed:.2f}s on adversarial input, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )
