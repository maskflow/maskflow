"""One test per precedence level (default < user file < project file < env
< CLI --set), plus a combined test walking the full chain -- per the
explicit requirement to test each level."""

from __future__ import annotations

from pathlib import Path

import pytest
from maskflow_cli.config.resolve import resolve_config


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


@pytest.fixture
def isolated_dirs(tmp_path: Path) -> tuple[Path, Path]:
    """(home, project) -- project has a .git so discovery treats it as the
    repo root, and project != home so project-file discovery is live."""
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    (project / ".git").mkdir()
    return home, project


def test_default_only(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    resolved = resolve_config(cwd=project, home=home, env={})
    assert resolved.config.maskflow.default_strategy.value == "replace"
    assert resolved.provenance[("maskflow", "default_strategy")].source == "default"


def test_user_file_only(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    _write(home / ".config" / "maskflow" / "config.toml", '[maskflow]\ndefault_strategy = "mask"\n')
    resolved = resolve_config(cwd=project, home=home, env={})
    assert resolved.config.maskflow.default_strategy.value == "mask"
    assert resolved.provenance[("maskflow", "default_strategy")].source == "user_file"


def test_project_file_overrides_user_file(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    _write(home / ".config" / "maskflow" / "config.toml", '[maskflow]\ndefault_strategy = "mask"\n')
    _write(project / ".maskflowrc", '[maskflow]\ndefault_strategy = "redact"\n')
    resolved = resolve_config(cwd=project, home=home, env={})
    assert resolved.config.maskflow.default_strategy.value == "redact"
    assert resolved.provenance[("maskflow", "default_strategy")].source == "project_file"


def test_env_overrides_project_and_user_file(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    _write(home / ".config" / "maskflow" / "config.toml", '[maskflow]\ndefault_strategy = "mask"\n')
    _write(project / ".maskflowrc", '[maskflow]\ndefault_strategy = "redact"\n')
    env = {"MASKFLOW_DEFAULT_STRATEGY": "hash", "MASKFLOW_HASH_KEY": "deadbeef"}
    resolved = resolve_config(cwd=project, home=home, env=env)
    assert resolved.config.maskflow.default_strategy.value == "hash"
    assert resolved.provenance[("maskflow", "default_strategy")].source == "env"


def test_cli_set_overrides_everything(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    _write(home / ".config" / "maskflow" / "config.toml", '[maskflow]\ndefault_strategy = "mask"\n')
    _write(project / ".maskflowrc", '[maskflow]\ndefault_strategy = "redact"\n')
    env = {"MASKFLOW_DEFAULT_STRATEGY": "hash", "MASKFLOW_HASH_KEY": "deadbeef"}
    resolved = resolve_config(
        cwd=project, home=home, env=env, cli_sets=["maskflow.default_strategy=surrogate"]
    )
    assert resolved.config.maskflow.default_strategy.value == "surrogate"
    prov = resolved.provenance[("maskflow", "default_strategy")]
    assert prov.source == "cli"


def test_reserved_envs_never_swept_into_config(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    env = {"MASKFLOW_HASH_KEY": "deadbeef", "MASKFLOW_MAPPING_KEY": "beefdead"}
    resolved = resolve_config(cwd=project, home=home, env=env)
    assert resolved.config == resolve_config(cwd=project, home=home, env={}).config


def test_field_level_merge_preserves_sibling_fields(isolated_dirs: tuple[Path, Path]) -> None:
    """A higher layer setting only `threshold` must not erase a lower
    layer's `strategy` for the same entity."""
    home, project = isolated_dirs
    _write(
        home / ".config" / "maskflow" / "config.toml",
        '[entities.AADHAAR]\nstrategy = "mask"\n',
    )
    _write(project / ".maskflowrc", "[entities.AADHAAR]\nthreshold = 0.7\n")
    resolved = resolve_config(cwd=project, home=home, env={})
    assert resolved.config.entities["AADHAAR"].strategy is not None
    assert resolved.config.entities["AADHAAR"].strategy.value == "mask"
    assert resolved.config.entities["AADHAAR"].threshold == 0.7


def test_list_fields_replace_not_append(isolated_dirs: tuple[Path, Path]) -> None:
    home, project = isolated_dirs
    _write(home / ".config" / "maskflow" / "config.toml", '[maskflow]\npacks = ["intl"]\n')
    _write(project / ".maskflowrc", '[maskflow]\npacks = ["india"]\n')
    resolved = resolve_config(cwd=project, home=home, env={})
    assert resolved.config.maskflow.packs == ["india"]


def test_config_path_override_bypasses_discovery(
    isolated_dirs: tuple[Path, Path], tmp_path: Path
) -> None:
    home, project = isolated_dirs
    _write(project / ".maskflowrc", '[maskflow]\ndefault_strategy = "redact"\n')
    elsewhere = tmp_path / "elsewhere.toml"
    _write(elsewhere, '[maskflow]\ndefault_strategy = "hash"\n')
    resolved = resolve_config(
        cwd=project,
        home=home,
        env={"MASKFLOW_HASH_KEY": "deadbeef"},
        config_path_override=elsewhere,
    )
    assert resolved.config.maskflow.default_strategy.value == "hash"
    assert resolved.project_file == elsewhere
