"""`maskflow-audit` must stay an optional dependency.

A bare `pip install maskflow-cli`, and the standalone PyInstaller binary,
must keep working with every other command intact -- the binary's spec
collects every `maskflow_cli` submodule, so a module-level
`import maskflow_audit` anywhere in the CLI would either bundle the audit
package into the binary or break its build.

Checked by AST inspection rather than by uninstalling the package, so the
guarantee holds in a dev environment where the extra IS installed (which
is every environment this suite runs in).
"""

from __future__ import annotations

import ast
import pathlib

import maskflow_cli.audit_render as audit_render_mod
import maskflow_cli.commands.audit_cmd as audit_cmd_mod
from maskflow_cli.app import app
from typer.testing import CliRunner

runner = CliRunner()

_MODULES = (audit_cmd_mod, audit_render_mod)


def _toplevel_imports(module: object) -> set[str]:
    """Root package names imported at module level (not inside a function).

    A TYPE_CHECKING block counts as module level textually but never runs,
    so it is skipped -- that is exactly how audit_render types itself
    against maskflow-audit without importing it.
    """
    source = pathlib.Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


def test_no_cli_module_imports_maskflow_audit_at_module_level() -> None:
    for module in _MODULES:
        assert "maskflow_audit" not in _toplevel_imports(module), (
            f"{module.__name__} imports maskflow_audit eagerly; it must be "
            "lazy-imported inside the command body"
        )


def test_the_guard_can_actually_see_imports() -> None:
    """Non-vacuity: the helper must find the imports that ARE there."""
    assert "typer" in _toplevel_imports(audit_cmd_mod)
    assert "rich" in _toplevel_imports(audit_render_mod)


def test_the_missing_extra_message_names_the_install_command() -> None:
    # A user who hits this needs the exact command, not a concept.
    assert "pip install 'maskflow-cli[audit]'" in audit_cmd_mod._MISSING


def test_every_other_command_still_works() -> None:
    # The binary ships without the extra; `doctor` must not care.
    result = runner.invoke(app, ["doctor"], env={"HOME": "/nonexistent-home"})
    assert result.exit_code == 0, result.output
