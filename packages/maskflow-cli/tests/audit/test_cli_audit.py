"""`maskflow audit` through the real root app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from maskflow_cli.app import app
from typer.testing import CliRunner

runner = CliRunner()

_APP = (
    "from openai import OpenAI\n"
    "client = OpenAI()\n"
    "def summarize(cur):\n"
    "    row = cur.fetchone()\n"
    "    return client.chat.completions.create(messages=row['aadhaar'])\n"
)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    (tmp_path / "app.py").write_text(_APP, encoding="utf-8")
    return tmp_path


def test_writes_a_report_and_exits_zero(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "audit.json"
    result = runner.invoke(app, ["audit", str(project), "--out", str(out)])
    assert result.exit_code == 0, result.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["coverage"]["total_flows"] == 1
    assert data["flows"][0]["masking_status"] == "unmasked"


def _flat(output: str) -> str:
    """Rich wraps at a fixed width, so collapse whitespace before matching
    a phrase -- otherwise the assertion pins the wrap points instead."""
    return " ".join(output.split())


def test_prints_the_headline_and_the_unproven_caveat(project: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", str(project), "--out", str(tmp_path / "a.json")])
    assert result.exit_code == 0, result.output
    assert "0 of 1 LLM egress paths masked" in result.output
    # The report must never let a reader think a static finding was proven.
    assert "predicted, not proven" in _flat(result.output)


def test_quiet_suppresses_the_summary(project: Path, tmp_path: Path) -> None:
    out = tmp_path / "a.json"
    result = runner.invoke(app, ["audit", str(project), "--out", str(out), "--quiet"])
    assert result.exit_code == 0, result.output
    assert "LLM egress paths" not in result.output
    assert out.is_file()


def test_out_dash_writes_to_stdout(project: Path) -> None:
    result = runner.invoke(app, ["audit", str(project), "--out", "-", "--quiet"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["schema_version"] == "1"


def test_default_output_path_is_audit_json(
    project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    workdir = tmp_path / "cwd"
    workdir.mkdir()
    monkeypatch.chdir(workdir)
    result = runner.invoke(app, ["audit", str(project), "--quiet"])
    assert result.exit_code == 0, result.output
    assert (workdir / "audit.json").is_file()


def test_a_missing_path_exits_two(tmp_path: Path) -> None:
    result = runner.invoke(app, ["audit", str(tmp_path / "nope")])
    assert result.exit_code == 2, result.output
    assert "no such file or directory" in result.output


def test_an_unknown_format_exits_one(project: Path) -> None:
    result = runner.invoke(app, ["audit", str(project), "--format", "pdf"])
    assert result.exit_code == 1, result.output
    assert "--format must be one of" in result.output


def test_exclude_is_repeatable(tmp_path: Path) -> None:
    (tmp_path / "app.py").write_text(_APP, encoding="utf-8")
    for name in ("vendor", "examples"):
        (tmp_path / name).mkdir()
        (tmp_path / name / "x.py").write_text(_APP, encoding="utf-8")

    out = tmp_path / "a.json"
    result = runner.invoke(
        app,
        [
            "audit",
            str(tmp_path),
            "--exclude",
            "vendor",
            "--exclude",
            "examples",
            "--out",
            str(out),
            "--quiet",
        ],
    )
    assert result.exit_code == 0, result.output
    files = [f["file"] for f in json.loads(out.read_text(encoding="utf-8"))["flows"]]
    assert files == ["app.py"]


def test_a_clean_tree_reports_zero_without_failing(tmp_path: Path) -> None:
    (tmp_path / "plain.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    result = runner.invoke(app, ["audit", str(tmp_path), "--out", str(tmp_path / "a.json")])
    assert result.exit_code == 0, result.output
    # A clean report must not read as a clean bill of health.
    assert "not that none exist" in _flat(result.output)


def test_audit_is_registered_on_the_root_app() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    assert "audit" in result.output


class TestNewSurfaces:
    """--prove / --baseline / --ci / --handoff / --format html."""

    _LEAKY = (
        "import os, sqlite3, httpx\n"
        "DB = os.path.join(os.path.dirname(__file__), 'app.db')\n"
        "client = httpx.Client(base_url='https://api.openai.com')\n"
        "def summarize():\n"
        "    row = sqlite3.connect(DB).execute("
        "'SELECT customer_name, aadhaar FROM tickets').fetchone()\n"
        "    return client.post('/v1/chat/completions',\n"
        "        json={'messages': [{'role': 'user', 'content': f'{row[0]} {row[1]}'}]})\n"
    )

    @pytest.fixture
    def leaky_project(self, tmp_path: Path) -> Path:
        import sqlite3

        (tmp_path / "app.py").write_text(self._LEAKY, encoding="utf-8")
        (tmp_path / "run_flows.py").write_text("import app\napp.summarize()\n", encoding="utf-8")
        connection = sqlite3.connect(tmp_path / "app.db")
        connection.execute(
            "CREATE TABLE tickets (id INTEGER PRIMARY KEY, customer_name TEXT, aadhaar TEXT)"
        )
        connection.commit()
        connection.close()
        return tmp_path

    def test_html_is_self_contained(self, project: Path, tmp_path: Path) -> None:
        out = tmp_path / "r.html"
        result = runner.invoke(
            app, ["audit", str(project), "--format", "html", "--out", str(out), "--quiet"]
        )
        assert result.exit_code == 0, result.output
        html = out.read_text(encoding="utf-8")
        assert html.startswith("<!doctype html>")
        for needle in ("http://", "https://fonts", "cdn.", "<script src", "<link "):
            assert needle not in html, needle
        assert "DPDP Rule 6" in html
        assert "<!-- DPDP_RULE6_APPENDIX -->" in html
        assert "No raw PII value" in html

    def test_prove_confirms_the_leak_with_a_call_stack(
        self, leaky_project: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "a.json"
        result = runner.invoke(
            app,
            [
                "audit",
                str(leaky_project),
                "--prove",
                "--flows",
                "python run_flows.py",
                "--seed",
                "7",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        data = json.loads(out.read_text(encoding="utf-8"))
        assert data["coverage"]["confirmed_leaks"] == 1
        flow = data["flows"][0]
        assert flow["canary_status"] == "escaped"
        assert flow["confidence"] == "confirmed"
        escapes = flow["canary_escapes"]
        assert escapes and escapes[0]["host"] == "api.openai.com"
        assert escapes[0]["app_stack"], "the call stack is the evidence; it must be present"
        assert "LEAK PROVEN" in result.output

    def test_prove_writes_no_canary_value_into_the_report(
        self, leaky_project: Path, tmp_path: Path
    ) -> None:
        """The report is a document a DPO retains; it must carry no value."""
        out = tmp_path / "a.json"
        result = runner.invoke(
            app,
            [
                "audit",
                str(leaky_project),
                "--prove",
                "--flows",
                "python run_flows.py",
                "--seed",
                "7",
                "--quiet",
                "--out",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        from maskflow_audit.canary.manifest import build_manifest

        rendered = out.read_text(encoding="utf-8")
        for value in build_manifest(seed=7).values():
            assert value not in rendered

    def test_prove_restores_the_tree(self, leaky_project: Path, tmp_path: Path) -> None:
        """An audit that left canary rows behind would be a bug."""
        import sqlite3

        result = runner.invoke(
            app,
            [
                "audit",
                str(leaky_project),
                "--prove",
                "--flows",
                "python run_flows.py",
                "--quiet",
                "--out",
                str(tmp_path / "a.json"),
            ],
        )
        assert result.exit_code == 0, result.output
        connection = sqlite3.connect(leaky_project / "app.db")
        assert connection.execute("SELECT COUNT(*) FROM tickets").fetchone()[0] == 0

    def test_baseline_then_ci_passes_unchanged(self, project: Path, tmp_path: Path) -> None:
        base = tmp_path / "base.json"
        written = runner.invoke(
            app, ["audit", str(project), "--baseline", "--baseline-file", str(base), "--quiet"]
        )
        assert written.exit_code == 0, written.output
        assert base.is_file()

        gate = runner.invoke(app, ["audit", str(project), "--ci", "--baseline-file", str(base)])
        assert gate.exit_code == 0, gate.output
        assert "no new unmasked" in gate.output

    def test_ci_fails_on_a_newly_added_unmasked_call(self, project: Path, tmp_path: Path) -> None:
        base = tmp_path / "base.json"
        runner.invoke(
            app, ["audit", str(project), "--baseline", "--baseline-file", str(base), "--quiet"]
        )
        (project / "app.py").write_text(
            _APP + "def added(t):\n    client.chat.completions.create(messages=t)\n",
            encoding="utf-8",
        )
        gate = runner.invoke(app, ["audit", str(project), "--ci", "--baseline-file", str(base)])
        assert gate.exit_code == 1, gate.output
        assert "NEW unguarded egress path" in gate.output
        assert "::error::" in gate.output

    def test_ci_skips_without_a_baseline(self, project: Path, tmp_path: Path) -> None:
        gate = runner.invoke(
            app, ["audit", str(project), "--ci", "--baseline-file", str(tmp_path / "none.json")]
        )
        assert gate.exit_code == 0, gate.output
        assert "skipped" in gate.output

    def test_handoff_writes_a_task_file(
        self, project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        workdir = tmp_path / "cwd"
        workdir.mkdir()
        monkeypatch.chdir(workdir)
        result = runner.invoke(
            app, ["audit", str(project), "--handoff", "--quiet", "--out", str(tmp_path / "a.json")]
        )
        assert result.exit_code == 0, result.output
        tasks = (workdir / "maskflow-audit-tasks.md").read_text(encoding="utf-8")
        assert "## Task 1" in tasks
        assert "Never edit a test" in tasks

    def test_fix_without_a_model_points_at_handoff(self, project: Path, tmp_path: Path) -> None:
        result = runner.invoke(
            app, ["audit", str(project), "--fix", "--out", str(tmp_path / "a.json")]
        )
        assert result.exit_code == 0, result.output
        assert "--handoff" in _flat(result.output)

    def test_fix_and_handoff_are_mutually_exclusive(self, project: Path) -> None:
        result = runner.invoke(app, ["audit", str(project), "--fix", "--handoff"])
        assert result.exit_code == 1, result.output
        assert "alternatives" in result.output

    def test_allow_env_is_required_in_a_production_looking_env(
        self, leaky_project: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Seeding production would be a data incident caused by the tool
        that exists to prevent data incidents."""
        monkeypatch.setenv("APP_ENV", "production")
        refused = runner.invoke(
            app,
            [
                "audit",
                str(leaky_project),
                "--prove",
                "--flows",
                "python run_flows.py",
                "--out",
                str(tmp_path / "a.json"),
            ],
        )
        assert refused.exit_code == 2, refused.output
        assert "refusing to seed" in refused.output

        allowed = runner.invoke(
            app,
            [
                "audit",
                str(leaky_project),
                "--prove",
                "--flows",
                "python run_flows.py",
                "--allow-env",
                "--quiet",
                "--out",
                str(tmp_path / "b.json"),
            ],
        )
        assert allowed.exit_code == 0, allowed.output
