"""Where .maskflowrc lives: a user file under ~/.config/maskflow/, and a
project file discovered by walking up from the current directory. See
docs/configuration.md for the precedence order these feed into.
"""

from __future__ import annotations

from pathlib import Path

_USER_CONFIG_NAMES = ("config.toml", "config.yaml", "config.yml", "config.json")
_PROJECT_CONFIG_NAMES = (
    ".maskflowrc",
    ".maskflowrc.toml",
    ".maskflowrc.yaml",
    ".maskflowrc.yml",
    ".maskflowrc.json",
)


def find_user_file(home: Path | None = None) -> Path | None:
    home = home if home is not None else Path.home()
    config_dir = home / ".config" / "maskflow"
    for name in _USER_CONFIG_NAMES:
        candidate = config_dir / name
        if candidate.is_file():
            return candidate
    return None


def find_project_file(cwd: Path | None = None, home: Path | None = None) -> Path | None:
    """Walk from `cwd` upward looking for a project config file. Stops
    (without matching) at `home` -- the home directory itself is the user
    file's territory, never searched as a "project" location. Stops after
    checking a directory containing `.git` (repo root), whether or not a
    config file was found there. Also stops at the filesystem root.
    """
    cwd = (cwd if cwd is not None else Path.cwd()).resolve()
    home = (home if home is not None else Path.home()).resolve()

    current = cwd
    while True:
        if current == home:
            return None

        for name in _PROJECT_CONFIG_NAMES:
            candidate = current / name
            if candidate.is_file():
                return candidate

        if (current / ".git").exists():
            return None

        parent = current.parent
        if parent == current:
            return None
        current = parent
