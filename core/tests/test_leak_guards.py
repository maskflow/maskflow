"""Guards against PII reaching logs, exceptions, repr, or test output (rule #1)."""
import pytest

from maskflow_core.entities import Finding, PIIType


@pytest.mark.leak
def test_finding_repr_excludes_raw_value():
    finding = Finding(PIIType.SSN, "245-11-2222", 0, 11, 0.95)
    assert "245-11-2222" not in repr(finding)
    assert "SSN" in repr(finding)
