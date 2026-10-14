"""The Claude Code plugin (plugins/maskflow-agent) stays in lockstep with the
package: same version everywhere, and the same hooks `maskflow-agent install`
writes."""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import maskflow_agent
import pytest
from maskflow_agent import doctor, install

REPO = Path(__file__).resolve().parents[3]
PLUGIN = REPO / "plugins" / "maskflow-agent"


def test_versions_match_the_package() -> None:
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    launcher = (PLUGIN / "scripts" / "maskflow-hook").read_text()
    pinned = re.search(r'^VERSION="([^"]+)"', launcher, re.M)
    assert pinned is not None
    assert manifest["version"] == pinned.group(1) == maskflow_agent.__version__


def test_marketplace_lists_the_plugin() -> None:
    market = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
    entry = next(p for p in market["plugins"] if p["name"] == "maskflow-agent")
    assert entry["source"] == "./plugins/maskflow-agent"


def test_plugin_hooks_match_install() -> None:
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    assert sorted(hooks) == install.EXPECTED_EVENTS
    for event, matcher, name, _timeout, extra in install._HOOKS:
        (group,) = hooks[event]
        assert group.get("matcher") == matcher
        (handler,) = group["hooks"]
        assert handler["command"] == "${CLAUDE_PLUGIN_ROOT}/scripts/maskflow-hook"
        assert handler["args"] == [name]
        for key, value in extra.items():  # e.g. onFailure: block on PreToolUse
            assert handler[key] == value


def test_launcher_is_valid_posix_sh_and_executable() -> None:
    launcher = PLUGIN / "scripts" / "maskflow-hook"
    assert launcher.stat().st_mode & 0o111
    subprocess.run(["sh", "-n", str(launcher)], check=True)


def test_launcher_denies_when_no_runtime(tmp_path: Path) -> None:
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "CLAUDE_PLUGIN_DATA": str(tmp_path)}
    out = subprocess.run(
        [str(PLUGIN / "scripts" / "maskflow-hook"), "pre-tool-use"],
        input="{}", capture_output=True, text=True, env=env, check=True,
    ).stdout  # fmt: skip
    assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize(
    ("entries", "expected"),
    [
        ([], None),
        ([{"id": "maskflow-agent@maskflow", "enabled": True, "scope": "user"}],
         "maskflow-agent@maskflow"),
        ([{"id": "maskflow-agent@maskflow", "enabled": False, "scope": "user"}], None),
        ([{"id": "maskflow-agent@maskflow", "enabled": True, "scope": "local",
           "projectPath": "/somewhere/else"}], None),
        ([{"id": "other@x", "enabled": True, "scope": "user"}], None),
    ],
)  # fmt: skip
def test_plugin_detection(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, entries: list[dict], expected: str | None
) -> None:
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: "/usr/bin/claude")

    def fake_run(*_args: object, **_kwargs: object) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess([], 0, stdout=json.dumps(entries))

    monkeypatch.setattr(doctor.subprocess, "run", fake_run)
    assert doctor._plugin_active(tmp_path) == expected


def test_plugin_detection_matches_this_project(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    entries = [{"id": "maskflow-agent@maskflow", "enabled": True, "scope": "local",
                "projectPath": str(tmp_path)}]  # fmt: skip
    monkeypatch.setattr(doctor.shutil, "which", lambda _name: "/usr/bin/claude")
    monkeypatch.setattr(
        doctor.subprocess,
        "run",
        lambda *_a, **_k: subprocess.CompletedProcess([], 0, stdout=json.dumps(entries)),
    )
    assert doctor._plugin_active(tmp_path) == "maskflow-agent@maskflow"
