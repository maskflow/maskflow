"""`maskflow-agent` command line. Stdlib only at import time -- `hook` and
`exec` run on every tool call, so heavy modules load only in the
subcommands that need them (`daemon`, `doctor`)."""

from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Fast paths first: no argparse tree for the per-tool-call commands.
    if argv[:1] == ["hook"] and len(argv) == 2:
        from . import hooks

        if argv[1] not in hooks.HANDLERS:
            sys.stderr.write(f"maskflow-agent: unknown hook {argv[1]!r}\n")
            return 2
        return hooks.main(argv[1])
    if argv[:1] == ["exec"]:
        from . import execwrap

        return execwrap.main(argv[1:])
    if argv[:1] == ["daemon"]:
        from . import daemon

        return daemon.main(argv[1:])

    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser(
        prog="maskflow-agent",
        description="MaskFlow PII guard for AI coding agents (Claude Code hooks).",
    )
    parser.add_argument("--version", action="version", version=f"maskflow-agent {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (
        ("install", "add the guard's hooks to Claude Code settings"),
        ("uninstall", "remove the guard's hooks from Claude Code settings"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument(
            "--scope",
            choices=("project", "local", "user"),
            default="project",
            help="project: .claude/settings.json (default, commit it to share with "
            "your team) | local: .claude/settings.local.json | user: ~/.claude/settings.json",
        )
    sub.add_parser("doctor", help="verify the guard end to end with synthetic canaries")
    sub.add_parser("hook", help="(internal) run one Claude Code hook")
    sub.add_parser("exec", help="(internal) run a command with placeholders restored")
    sub.add_parser("daemon", help="(internal) per-session masking daemon")
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    if args.cmd in ("install", "uninstall"):
        from . import install

        path = install.settings_path(args.scope, cwd)
        if args.cmd == "install":
            install.install(path)
            print(f"maskflow-agent hooks installed in {path}")
            print("Start a new Claude Code session, then run `maskflow-agent doctor`.")
        else:
            removed = install.uninstall(path)
            print(f"{'removed from' if removed else 'no maskflow-agent hooks in'} {path}")
        return 0
    if args.cmd == "doctor":
        from . import doctor

        return doctor.run(cwd)
    parser.error(f"use `maskflow-agent {args.cmd}` only through Claude Code hooks")
    return 2
