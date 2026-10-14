import json
from pathlib import Path

from maskflow_agent import install

OTHER_HOOK = {"type": "command", "command": "echo", "args": ["hi"]}


def _write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def test_install_adds_every_event_and_keeps_other_settings(tmp_path: Path) -> None:
    path = tmp_path / ".claude" / "settings.json"
    _write(
        path,
        {
            "model": "sonnet",
            "permissions": {"allow": ["Read"]},
            "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [OTHER_HOOK]}]},
        },
    )
    settings = install.install(path)
    assert settings["model"] == "sonnet"
    assert settings["permissions"] == {"allow": ["Read"]}
    assert install.installed(path) == install.EXPECTED_EVENTS
    pre = settings["hooks"]["PreToolUse"]
    assert {"matcher": "Bash", "hooks": [OTHER_HOOK]} in pre
    ours = next(g for g in pre if g.get("matcher") == "*")["hooks"][0]
    assert ours["onFailure"] == "block"
    assert ours["args"][:2] == ["-m", "maskflow_agent"]


def test_install_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    install.install(path)
    first = path.read_text()
    install.install(path)
    assert path.read_text() == first


def test_uninstall_removes_only_ours(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    _write(path, {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [OTHER_HOOK]}]}})
    install.install(path)
    assert install.uninstall(path)
    assert json.loads(path.read_text()) == {
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [OTHER_HOOK]}]}
    }
    assert not install.uninstall(path)


def test_uninstall_drops_empty_hooks_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    install.install(path)
    install.uninstall(path)
    assert json.loads(path.read_text()) == {}
