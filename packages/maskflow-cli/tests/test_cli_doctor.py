from __future__ import annotations

from dataclasses import dataclass

import maskflow_cli.commands.doctor_cmd as doctor_cmd_module
import maskflow_cli.doctor as doctor_module
import maskflow_pack_intl  # noqa: F401 -- side effect: populates PATTERNS/NER_RECOGNIZERS
import pytest
from maskflow_cli.app import app
from maskflow_cli.doctor import ComponentCheck, DoctorReport, EntityCheck
from typer.testing import CliRunner

runner = CliRunner()


@dataclass(frozen=True)
class _FakeEntityConfig:
    enabled: bool


def test_doctor_exits_nonzero_when_a_component_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        doctor_module,
        "_check_spacy",
        lambda: (
            ComponentCheck("spaCy", None, "error", "not installed"),
            ComponentCheck("spaCy model (en_core_web_sm)", None, "error", "unavailable"),
        ),
    )
    result = runner.invoke(app, ["doctor"], env={"HOME": "/nonexistent-home"})
    assert result.exit_code == 1
    assert "MaskFlow Doctor" in result.stdout
    assert "Not fully healthy" in result.stdout
    assert "PERSON_NAME" in result.stdout
    assert "disabled" in result.stdout


def test_doctor_exits_zero_when_fully_healthy(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_report = DoctorReport(
        components=[ComponentCheck("maskflow-core", "0.3.0", "ok")],
        entities=[EntityCheck("EMAIL", "pattern", True)],
    )
    monkeypatch.setattr(doctor_cmd_module, "run_checks", lambda: fake_report)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 0
    assert "All checks passed" in result.stdout


def test_entity_disabled_via_maskflowrc_reports_that_reason() -> None:
    resolved = doctor_module.ResolvedConfig(
        config=type("Cfg", (), {"entities": {"EMAIL": _FakeEntityConfig(enabled=False)}})(),
        provenance={},
        project_file=None,
        user_file=None,
    )
    checks = doctor_module._entity_checks(resolved, spacy_ready=True)
    email = next(c for c in checks if c.name == "EMAIL")
    assert not email.enabled
    assert "maskflowrc" in email.reason


def test_entity_disabled_via_missing_spacy_model() -> None:
    checks = doctor_module._entity_checks(None, spacy_ready=False)
    person = next(c for c in checks if c.name == "PERSON_NAME")
    assert not person.enabled
    assert "spaCy" in person.reason

    email = next(c for c in checks if c.name == "EMAIL")
    assert email.enabled
    assert email.detector == "pattern"
