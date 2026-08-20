"""Whole-session leak gate (CLAUDE.md rule #1): asserts none of this
package's known synthetic PII fixture values ever showed up in a log record
or an exception's text, anywhere in the test session -- not just in the
handful of classes test_leak_guards.py checks directly via repr().

Ordered last by maskflow_core.testing.pytest_collection_modifyitems (wired
in conftest.py) so LEAK_POOL has seen everything the session produced by the
time this runs.
"""

import pytest
from maskflow_core.testing import LEAK_POOL, assert_no_leaks

# Every synthetic PII-shaped literal used as a fixture value anywhere in
# this package's tests -- see test_masking.py, test_mask_with_policy.py,
# test_leak_guards.py, test_registry.py.
_KNOWN_PII_FIXTURE_VALUES = (
    "MARK-A-1111",
    "MARK-B-2222",
    "MARK-A-3333",
    "GADGET-123456",
    "GADGET-654321",
    "WID-123456",
    "245-11-2222",
)


@pytest.mark.leak
def test_no_pii_leaked_during_test_session() -> None:
    assert_no_leaks(LEAK_POOL, _KNOWN_PII_FIXTURE_VALUES)
