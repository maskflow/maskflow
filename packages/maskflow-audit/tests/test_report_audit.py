"""The report: versioned, deterministic, and provably value-free."""

from __future__ import annotations

import ast
import json
import pathlib
from datetime import datetime, timezone

import pytest
from maskflow_audit.api import run_audit
from maskflow_audit.report import FORMATS, render
from maskflow_audit.report.summary import AUDIT_SCHEMA_VERSION

_APP = (
    "from openai import OpenAI\n"
    "client = OpenAI()\n"
    "def summarize(cur):\n"
    "    row = cur.fetchone()\n"
    "    return client.chat.completions.create(messages=row['aadhaar'])\n"
)

_FIXED = datetime(2026, 10, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_schema_version_is_the_first_key(tree) -> None:
    """A consumer must be able to check the version without parsing it all,
    and `--ci` must be able to refuse a baseline it cannot read."""
    rendered = render(run_audit(tree(_APP)), "json")
    assert json.loads(rendered)["schema_version"] == AUDIT_SCHEMA_VERSION
    assert rendered.lstrip().startswith('{\n  "schema_version"')


def test_two_runs_are_byte_identical_apart_from_the_timestamp(tree) -> None:
    """Determinism is the product: a gate that flickers gets switched off."""
    root = tree(_APP)
    first = render(run_audit(root, now=_FIXED), "json")
    second = render(run_audit(root, now=_FIXED), "json")
    assert first == second


def test_the_only_moving_field_is_generated_at(tree) -> None:
    root = tree(_APP)
    a = json.loads(render(run_audit(root, now=_FIXED), "json"))
    b = json.loads(render(run_audit(root), "json"))
    a["scope"].pop("generated_at")
    b["scope"].pop("generated_at")
    assert a == b


def test_the_config_fingerprint_ignores_the_checkout_path(tmp_path: pathlib.Path) -> None:
    """A CI runner and a laptop must agree, or a baseline is unusable."""
    one, two = tmp_path / "a", tmp_path / "b"
    for directory in (one, two):
        directory.mkdir()
        (directory / "app.py").write_text(_APP, encoding="utf-8")
    assert (
        run_audit(one).methodology.config_fingerprint
        == run_audit(two).methodology.config_fingerprint
    )


def test_render_rejects_an_unknown_format(tree) -> None:
    with pytest.raises(ValueError, match="unknown format"):
        render(run_audit(tree(_APP)), "xml")


def test_the_format_surface_is_pinned() -> None:
    # Asserting the surface keeps the CLI's --format validation and the
    # renderer registry from drifting apart.
    assert FORMATS == ("json", "html")


def test_the_methodology_states_its_limits(tree) -> None:
    """An honest report says what it did not look at.

    A clean audit means "nothing known was found", not "nothing exists",
    and the report has to say so itself -- the number is useless without it.
    """
    methodology = run_audit(tree(_APP)).methodology
    assert "canar" in methodology.limits_note.lower()
    assert "unknown" in methodology.limits_note.lower()
    assert "typescript" in methodology.not_detected_note.lower()
    assert methodology.sinks_known > 0
    assert methodology.detector_versions


def test_the_dpdp_appendix_marker_is_carried_into_json(tree) -> None:
    # Same marker name as the scan report's, so the substitution one-liner
    # documented in docs/dpdp-rule6.md works on both.
    data = json.loads(render(run_audit(tree(_APP)), "json"))
    assert data["dpdp_appendix_slot"] == "<!-- DPDP_RULE6_APPENDIX -->"


class TestNoValueAccess:
    """Static guard: the renderers cannot reach a value even in principle.

    Same technique as maskflow-evidence's test_derive_no_value_access --
    an AST inspection rather than a behavioural test, so it holds for code
    paths no test happens to exercise.
    """

    FORBIDDEN_ATTRS = {"text", "original", "masked_text"}
    FORBIDDEN_CALLS = {"read_text", "read_bytes", "open", "unparse", "get_source_segment"}

    @staticmethod
    def _report_modules() -> list[pathlib.Path]:
        import maskflow_audit.report as report_pkg

        directory = pathlib.Path(report_pkg.__file__).parent
        modules = sorted(directory.glob("*.py"))
        assert modules, "no report modules found -- the guard would pass vacuously"
        return modules

    def test_no_report_module_reads_a_value_attribute(self) -> None:
        offenders: list[str] = []
        for path in self._report_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            offenders += [
                f"{path.name}:{node.lineno} .{node.attr}"
                for node in ast.walk(tree)
                if isinstance(node, ast.Attribute) and node.attr in self.FORBIDDEN_ATTRS
            ]
        assert not offenders, f"a report module reads a value attribute: {offenders}"

    def test_no_report_module_reads_source_from_disk(self) -> None:
        """The report renders from AuditSummary and nothing else.

        A renderer that could re-open the audited file could quote it, and
        the leak argument would no longer be answerable by inspecting the
        data model.
        """
        offenders: list[str] = []
        for path in self._report_modules():
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = (
                    node.func.attr
                    if isinstance(node.func, ast.Attribute)
                    else getattr(node.func, "id", "")
                )
                if name in self.FORBIDDEN_CALLS:
                    offenders.append(f"{path.name}:{node.lineno} {name}()")
        assert not offenders, f"a report module reads source: {offenders}"
