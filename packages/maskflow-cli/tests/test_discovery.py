from __future__ import annotations

from pathlib import Path

from maskflow_cli.config.discovery import find_project_file, find_user_file


def test_find_user_file_none(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    assert find_user_file(home=home) is None


def test_find_user_file_found(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "maskflow"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text("[maskflow]\n")
    assert find_user_file(home=home) == config_dir / "config.toml"


def test_find_user_file_prefers_toml_over_yaml(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_dir = home / ".config" / "maskflow"
    config_dir.mkdir(parents=True)
    (config_dir / "config.toml").write_text("[maskflow]\n")
    (config_dir / "config.yaml").write_text("maskflow: {}\n")
    assert find_user_file(home=home) == config_dir / "config.toml"


def test_find_project_file_in_cwd(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "proj"
    project.mkdir()
    (project / ".maskflowrc").write_text("[maskflow]\n")
    assert find_project_file(cwd=project, home=home) == project / ".maskflowrc"


def test_find_project_file_walks_up_to_git_root(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "proj"
    nested = project / "a" / "b" / "c"
    nested.mkdir(parents=True)
    (project / ".git").mkdir()
    (project / ".maskflowrc").write_text("[maskflow]\n")
    assert find_project_file(cwd=nested, home=home) == project / ".maskflowrc"


def test_find_project_file_stops_at_git_root_even_if_not_found(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = tmp_path / "proj"
    nested = project / "a" / "b"
    nested.mkdir(parents=True)
    (project / ".git").mkdir()
    # No config file anywhere under project -- must not escape above the git root.
    outside = tmp_path / "outside.maskflowrc"
    outside.write_text("[maskflow]\n")
    assert find_project_file(cwd=nested, home=home) is None


def test_find_project_file_never_searches_home_itself(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    (home / ".maskflowrc").write_text("[maskflow]\n")
    # cwd == home, with no git root in between -- must not treat $HOME as a
    # project location.
    assert find_project_file(cwd=home, home=home) is None


def test_find_project_file_stops_walk_before_crossing_home(tmp_path: Path) -> None:
    home = tmp_path / "home"
    nested = home / "scratch" / "sub"
    nested.mkdir(parents=True)
    (home / ".maskflowrc").write_text("[maskflow]\n")
    # No .git anywhere between nested and home -- walk must stop at home's
    # boundary without matching home's own config file.
    assert find_project_file(cwd=nested, home=home) is None
