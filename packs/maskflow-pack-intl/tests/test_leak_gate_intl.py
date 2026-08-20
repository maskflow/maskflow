"""Whole-session leak gate (CLAUDE.md rule #1): asserts none of
fixtures/pii_samples.py's 100+ labeled PII values ever showed up in a log
record or an exception's text, anywhere in the test session.

Ordered last by maskflow_core.testing.pytest_collection_modifyitems (wired
in conftest.py) so LEAK_POOL has seen everything the session produced by the
time this runs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import pytest  # noqa: E402 -- sys.path setup must precede the fixtures import
from fixtures.pii_samples import POSITIVE_SAMPLES  # noqa: E402
from maskflow_core.testing import LEAK_POOL, assert_no_leaks  # noqa: E402

_KNOWN_PII_FIXTURE_VALUES = tuple(
    value for sample in POSITIVE_SAMPLES for _pii_type, value in sample.expected
)


@pytest.mark.leak
def test_no_pii_leaked_during_test_session() -> None:
    assert_no_leaks(LEAK_POOL, _KNOWN_PII_FIXTURE_VALUES)
