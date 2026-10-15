"""`maskflow-agent` command line. Stdlib only at import time -- `hook` and
`exec` run on every tool call, so heavy modules load only in the
subcommands that need them (`daemon`, `doctor`)."""

from __future__ import annotations

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    # Fast paths first: no argparse tree for the per-tool-call commands.
    if argv[:2] == ["hook", "--agent"] and len(argv) == 4:
        from . import adapters

        if argv[2] == "claude":
            argv = ["hook", argv[3]]
        else:
            return adapters.main(argv[2], argv[3])
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

    from . import adapters

    parser = argparse.ArgumentParser(
        prog="maskflow-agent",
        description="MaskFlow PII guard for AI coding agents (Claude Code, GitHub Copilot, ...).",
    )
    parser.add_argument("--version", action="version", version=f"maskflow-agent {__version__}")
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name, help_text in (
        ("install", "add the guard's hooks to an agent's settings"),
        ("uninstall", "remove the guard's hooks from an agent's settings"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument(
            "--agent",
            choices=("claude", *adapters.AGENTS),
            default="claude",
            help="claude: Claude Code (default) | copilot: GitHub Copilot CLI, cloud "
            "agent and VS Code agent mode | cursor: Cursor desktop and CLI "
            "(all but claude are experimental)",
        )
        p.add_argument(
            "--scope",
            choices=("project", "local", "user"),
            default="project",
            help="claude -- project: .claude/settings.json (default, commit it to share "
            "with your team) | local: .claude/settings.local.json | user: "
            "~/.claude/settings.json. copilot -- project: .github/hooks/ | user: "
            "~/.copilot/hooks/. cursor -- project: .cursor/hooks.json | user: "
            "~/.cursor/hooks.json",
        )
        p.add_argument(
            "--portable",
            action="store_true",
            help="non-Claude agents: run `maskflow-agent` from PATH instead of this interpreter's "
            "absolute path (for a committed file used on other machines or by the "
            "Copilot cloud agent)",
        )
        if name == "install":
            p.add_argument(
                "--no-warm-up",
                action="store_true",
                help="skip loading the engine once now (the first session then starts cold)",
            )
    sub.add_parser("doctor", help="verify the guard end to end with synthetic canaries")
    sub.add_parser("hook", help="(internal) run one Claude Code hook")
    sub.add_parser("exec", help="(internal) run a command with placeholders restored")
    sub.add_parser("daemon", help="(internal) per-session masking daemon")
    args = parser.parse_args(argv)

    cwd = Path.cwd()
    if args.cmd in ("install", "uninstall") and args.agent != "claude":
        return _install_other(
            args.cmd, args.agent, args.scope, args.portable, getattr(args, "no_warm_up", False), cwd
        )
    if args.cmd in ("install", "uninstall"):
        from . import install

        path = install.settings_path(args.scope, cwd)
        if args.cmd == "install":
            install.install(path)
            print(f"maskflow-agent hooks installed in {path}")
            if not args.no_warm_up:
                print("Loading the masking engine once (the first load can take ~30 s) ...")
                ok, seconds = install.warm_up()
                print(
                    f"  ready in {seconds:.0f} s"
                    if ok
                    else "  warm-up failed -- run `maskflow-agent doctor` to see why"
                )
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


def _install_other(
    cmd: str, agent: str, scope: str, portable: bool, no_warm_up: bool, cwd: object
) -> int:
    from pathlib import Path

    from . import adapters, install

    module = adapters.load(agent)
    path = module.config_path(scope, Path(str(cwd)))
    if cmd == "uninstall":
        removed = module.uninstall(path)
        print(f"{'removed' if removed else 'no maskflow-agent hooks in'} {path}")
        return 0
    module.install(path, portable=portable)
    print(f"maskflow-agent hooks for {agent} installed in {path}")
    if adapters.STATUS.get(agent) != "verified":
        print(
            f"  note: {agent} support is EXPERIMENTAL -- built from the agent's hook "
            "documentation, not yet verified against the live agent."
        )
    print("Loading the masking engine once (the first load can take ~30 s) ...")
    ok, seconds = install.warm_up()
    print(
        f"  ready in {seconds:.0f} s" if ok else "  warm-up failed -- run `maskflow-agent doctor`"
    )
    print("Start a new agent session, then run `maskflow-agent doctor`.")
    return 0
