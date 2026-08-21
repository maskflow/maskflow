from __future__ import annotations

import pytest
from maskflow_cli.config.schema import RootConfig
from pydantic import ValidationError


def test_root_config_defaults() -> None:
    config = RootConfig()
    assert config.maskflow.packs == []
    assert config.maskflow.default_strategy.value == "replace"
    assert config.entities == {}
    assert config.exclusions.values == []


def test_valid_full_config() -> None:
    config = RootConfig.model_validate(
        {
            "maskflow": {"packs": ["india"], "default_strategy": "replace"},
            "entities": {"AADHAAR": {"enabled": True, "threshold": 0.6, "strategy": "mask"}},
            "custom": {
                "EMPLOYEE_ID": {"pattern": r"\bEMP-\d{6}\b", "score": 0.9, "context": ["employee"]}
            },
            "exclusions": {"values": ["test@example.com"], "patterns": [r"\bDEMO-\d+\b"]},
        }
    )
    assert config.entities["AADHAAR"].threshold == 0.6
    assert config.custom["EMPLOYEE_ID"].score == 0.9


def test_unknown_top_level_key_rejected() -> None:
    with pytest.raises(ValidationError):
        RootConfig.model_validate({"maskflw": {}})


def test_unknown_entity_field_rejected() -> None:
    with pytest.raises(ValidationError):
        RootConfig.model_validate({"entities": {"PAN": {"threshod": 0.5}}})


@pytest.mark.parametrize("bad_name", ["aadhaar", "1AADHAAR", "AADHAAR-1", ""])
def test_entity_name_shape_rejected(bad_name: str) -> None:
    with pytest.raises(ValidationError):
        RootConfig.model_validate({"entities": {bad_name: {"enabled": True}}})


def test_threshold_out_of_range_rejected() -> None:
    with pytest.raises(ValidationError):
        RootConfig.model_validate({"entities": {"AADHAAR": {"threshold": 1.5}}})


def test_unknown_strategy_rejected() -> None:
    with pytest.raises(ValidationError):
        RootConfig.model_validate({"maskflow": {"default_strategy": "not_a_strategy"}})


def test_custom_entity_requires_pattern_and_score() -> None:
    with pytest.raises(ValidationError):
        RootConfig.model_validate({"custom": {"EMPLOYEE_ID": {"score": 0.9}}})
