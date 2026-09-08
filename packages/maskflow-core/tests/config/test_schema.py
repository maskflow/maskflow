from __future__ import annotations

import pytest
from maskflow_core.config.schema import RootConfig, validate_root_config


def test_root_config_defaults() -> None:
    config = RootConfig()
    assert config.maskflow.packs == []
    assert config.maskflow.default_strategy.value == "replace"
    assert config.entities == {}
    assert config.exclusions.values == []


def test_valid_full_config() -> None:
    config, issues = validate_root_config(
        {
            "maskflow": {"packs": ["india"], "default_strategy": "replace"},
            "entities": {"AADHAAR": {"enabled": True, "threshold": 0.6, "strategy": "mask"}},
            "custom": {
                "EMPLOYEE_ID": {
                    "pattern": r"\bEMP-\d{6}\b",
                    "score": 0.9,
                    "context": ["employee"],
                }
            },
            "exclusions": {"values": ["test@example.com"], "patterns": [r"\bDEMO-\d+\b"]},
        }
    )
    assert issues == []
    assert config.entities["AADHAAR"].threshold == 0.6
    assert config.entities["AADHAAR"].strategy is not None
    assert config.entities["AADHAAR"].strategy.value == "mask"
    assert config.custom["EMPLOYEE_ID"].score == 0.9


def test_unknown_top_level_key_rejected() -> None:
    _config, issues = validate_root_config({"maskflw": {}})
    assert issues
    assert issues[0].suggestion == "maskflow"


def test_unknown_entity_field_rejected() -> None:
    _config, issues = validate_root_config({"entities": {"PAN": {"threshod": 0.5}}})
    assert issues
    assert issues[0].suggestion == "threshold"


@pytest.mark.parametrize("bad_name", ["aadhaar", "1AADHAAR", "AADHAAR-1", ""])
def test_entity_name_shape_rejected(bad_name: str) -> None:
    _config, issues = validate_root_config({"entities": {bad_name: {"enabled": True}}})
    assert issues


def test_threshold_out_of_range_rejected() -> None:
    _config, issues = validate_root_config({"entities": {"AADHAAR": {"threshold": 1.5}}})
    assert issues


def test_threshold_wrong_type_rejected() -> None:
    _config, issues = validate_root_config({"entities": {"AADHAAR": {"threshold": "high"}}})
    assert issues


def test_unknown_strategy_rejected() -> None:
    _config, issues = validate_root_config({"maskflow": {"default_strategy": "not_a_strategy"}})
    assert issues


def test_strategy_typo_suggests_correction() -> None:
    _config, issues = validate_root_config({"maskflow": {"default_strategy": "maks"}})
    assert issues
    assert issues[0].suggestion == "mask"


def test_custom_entity_requires_pattern_and_score() -> None:
    _config, issues = validate_root_config({"custom": {"EMPLOYEE_ID": {"score": 0.9}}})
    assert issues
    assert any(i.path == ("custom", "EMPLOYEE_ID", "pattern") for i in issues)


def test_custom_entity_unsafe_pattern_rejected() -> None:
    _config, issues = validate_root_config(
        {"custom": {"EMPLOYEE_ID": {"pattern": r"(a+)+", "score": 0.9}}}
    )
    assert issues


def test_collects_multiple_errors_at_once() -> None:
    _config, issues = validate_root_config({"maskflw": {}, "entities": {"PAN": {"threshod": 0.5}}})
    assert len(issues) == 2


def test_not_a_table_reported_clearly() -> None:
    _config, issues = validate_root_config({"entities": "nope"})
    assert issues
    assert "table" in issues[0].message


# --- [evidence] section ------------------------------------------------


def test_evidence_defaults_off() -> None:
    config = RootConfig()
    assert config.evidence.enabled is False
    assert config.evidence.sink == "file"
    assert config.evidence.service == "maskflow"


def test_valid_evidence_section() -> None:
    config, issues = validate_root_config(
        {
            "evidence": {
                "enabled": True,
                "sink": "file",
                "path": "/var/log/mf-evidence.log",
                "max_bytes": 5_000_000,
                "backups": 3,
                "service": "kyc-bot",
                "environment": "prod",
            }
        }
    )
    assert issues == []
    assert config.evidence.enabled is True
    assert config.evidence.path == "/var/log/mf-evidence.log"
    assert config.evidence.max_bytes == 5_000_000


def test_evidence_unknown_key_rejected() -> None:
    _config, issues = validate_root_config({"evidence": {"snik": "file"}})
    assert issues
    assert issues[0].suggestion == "sink"


def test_evidence_bad_sink_rejected() -> None:
    _config, issues = validate_root_config({"evidence": {"sink": "smoke-signals"}})
    assert any(i.path == ("evidence", "sink") for i in issues)


def test_evidence_webhook_requires_url() -> None:
    _config, issues = validate_root_config({"evidence": {"sink": "webhook"}})
    assert any(i.path == ("evidence", "url") and "url" in i.message for i in issues)


def test_evidence_wrong_types_rejected() -> None:
    _config, issues = validate_root_config(
        {"evidence": {"enabled": "yes", "max_bytes": "big", "timeout": -1}}
    )
    paths = {i.path for i in issues}
    assert ("evidence", "enabled") in paths
    assert ("evidence", "max_bytes") in paths
    assert ("evidence", "timeout") in paths


def test_evidence_not_a_table_reported() -> None:
    _config, issues = validate_root_config({"evidence": "on"})
    assert issues
    assert "table" in issues[0].message
