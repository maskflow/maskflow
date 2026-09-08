from __future__ import annotations

from maskflow_core.config.schema import EvidenceSection, validate_root_config
from maskflow_evidence import EvidenceConfig


def test_defaults_are_disabled() -> None:
    cfg = EvidenceConfig()
    assert cfg.enabled is False
    assert cfg.sink == "file"


def test_from_env_reads_prefixed_vars() -> None:
    env = {
        "MASKFLOW_GATEWAY_EVIDENCE_ENABLED": "true",
        "MASKFLOW_GATEWAY_EVIDENCE_SINK": "stdout",
        "MASKFLOW_GATEWAY_EVIDENCE_SERVICE": "gw",
        "UNRELATED": "x",
    }
    cfg = EvidenceConfig.from_env("MASKFLOW_GATEWAY_EVIDENCE_", env)
    assert cfg.enabled is True
    assert cfg.sink == "stdout"
    assert cfg.service == "gw"


def test_from_rootconfig_reads_evidence_section() -> None:
    root, issues = validate_root_config(
        {"evidence": {"enabled": True, "sink": "file", "path": "x.log", "service": "app"}}
    )
    assert not issues
    cfg = EvidenceConfig.from_rootconfig(root)
    assert cfg.enabled is True
    assert cfg.path == "x.log"
    assert cfg.service == "app"


def test_from_rootconfig_missing_section_is_disabled() -> None:
    cfg = EvidenceConfig.from_rootconfig(object())
    assert cfg.enabled is False


def test_syslog_address() -> None:
    assert EvidenceConfig(sink="syslog").syslog_address() == "/dev/log"
    assert EvidenceConfig(sink="syslog", syslog_host="h", syslog_port=5514).syslog_address() == (
        "h",
        5514,
    )


def test_core_schema_rejects_bad_sink() -> None:
    _root, issues = validate_root_config({"evidence": {"sink": "smoke-signals"}})
    assert any(i.path == ("evidence", "sink") for i in issues)


def test_core_schema_webhook_requires_url() -> None:
    _root, issues = validate_root_config({"evidence": {"sink": "webhook"}})
    assert any(i.path == ("evidence", "url") for i in issues)


def test_core_schema_unknown_key_flagged() -> None:
    _root, issues = validate_root_config({"evidence": {"enabledd": True}})
    assert any(i.path == ("evidence", "enabledd") for i in issues)


def test_evidence_section_default_matches_config_default() -> None:
    section = EvidenceSection()
    cfg = EvidenceConfig.from_rootconfig(type("R", (), {"evidence": section})())
    assert cfg == EvidenceConfig()
