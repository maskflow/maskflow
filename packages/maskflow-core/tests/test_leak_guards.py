"""Guards against PII reaching logs, exceptions, repr, or test output (rule #1)."""

import pytest
from maskflow_core.entities import Finding, PIIType


@pytest.mark.leak
def test_finding_repr_excludes_raw_value() -> None:
    secret_type = PIIType.register("SECRET_ID")
    finding = Finding(secret_type, "245-11-2222", 0, 11, 0.95)
    assert "245-11-2222" not in repr(finding)
    assert "SECRET_ID" in repr(finding)
