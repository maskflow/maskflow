"""`maskflow-agent exec --session S -- '<command with placeholders>'`

The PreToolUse hook rewrites an allowlisted Bash command into this wrapper,
so the command Claude Code records, shows and logs only ever contains
placeholders. Here, inside the child process, the daemon swaps placeholders
for real values, the command runs, and its stdout/stderr are masked before
they are printed. Stdlib only.

Fails closed: if the daemon can't be reached, or the single-use ticket the
PreToolUse hook obtained for this exact command is missing, spent or
expired, the command does NOT run.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

from . import protocol

EXIT_GUARD_DOWN = 97
MAX_CAPTURE = 64 * 1024 * 1024


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="maskflow-agent exec")
    parser.add_argument("--session", required=True)
    parser.add_argument("--ticket", required=True)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    parts = args.command[1:] if args.command[:1] == ["--"] else args.command
    if len(parts) != 1:
        sys.stderr.write("maskflow-agent exec: expected exactly one command string\n")
        return 2
    command = parts[0]

    try:
        real = protocol.request(args.session, "unmask_text", text=command, ticket=args.ticket)[
            "text"
        ]
    except (protocol.DaemonUnavailable, KeyError):
        sys.stderr.write(
            "maskflow: placeholders can't be restored (guard not running, or this run "
            "wasn't approved by the guard's hook). The command was not run.\n"
        )
        return EXIT_GUARD_DOWN

    proc = subprocess.run(
        ["bash", "-c", real],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
    )
    stdout = proc.stdout[:MAX_CAPTURE].decode("utf-8", errors="replace")
    stderr = proc.stderr[:MAX_CAPTURE].decode("utf-8", errors="replace")
    del real
    try:
        masked = protocol.request(
            args.session, "mask_value", value={"stdout": stdout, "stderr": stderr}
        )["value"]
        out, err = masked["stdout"], masked["stderr"]
    except (protocol.DaemonUnavailable, KeyError, TypeError):
        out = "[maskflow: output withheld -- the PII guard stopped while the command ran]\n"
        err = ""
    sys.stdout.write(out)
    sys.stderr.write(err)
    if len(proc.stdout) > MAX_CAPTURE or len(proc.stderr) > MAX_CAPTURE:
        sys.stderr.write("[maskflow: output truncated]\n")
    return proc.returncode
