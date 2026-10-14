from maskflow_cli.app import app
from typer.testing import CliRunner


def test_agent_passthrough_reaches_maskflow_agent() -> None:
    result = CliRunner().invoke(app, ["agent", "--version"])
    assert result.exit_code == 0
    assert "maskflow-agent" in result.output


def test_agent_install_writes_hooks(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(app, ["agent", "install", "--scope", "local", "--no-warm-up"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / ".claude" / "settings.local.json").is_file()
