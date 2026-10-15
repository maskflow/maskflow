"""`maskflow-agent doctor`: prove the guard works on this machine.

Runs SYNTHETIC canary identifiers (generated here, checksum-valid, never
real people's data) through the real hook processes and a real daemon, and
fails loudly if any canary would reach the model.
"""

from __future__ import annotations

import json
import random
import re
import shutil
import socket
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

from . import install, paths, protocol

MIN_CLAUDE = (2, 1, 295)  # PreToolUse `onFailure: "block"`


def _canaries() -> dict[str, str]:
    """SYNTHETIC: random, checksum-valid shapes; regenerated every run."""
    from maskflow_pack_india.checksums import (  # type: ignore[import-untyped]
        verhoeff_generate,
    )

    rng = random.Random()
    base = rng.choice("23456789") + "".join(rng.choice("0123456789") for _ in range(10))
    letters = "ABCDEFGHJKLMNPRSTUVWXYZ"
    pan = (
        "".join(rng.choice(letters) for _ in range(3))
        + "P"
        + rng.choice(letters)
        + "".join(rng.choice("0123456789") for _ in range(4))
        + rng.choice(letters)
    )
    return {
        "AADHAAR": base + str(verhoeff_generate(base)),
        "PAN": pan,
        "INDIAN_MOBILE": rng.choice("6789") + "".join(rng.choice("0123456789") for _ in range(9)),
    }


def _run_hook(event: str, payload: dict[str, Any]) -> tuple[int, str]:
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "hook", event],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    return proc.returncode, proc.stdout


def _claude_version() -> tuple[int, ...] | None:
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "--version"], capture_output=True, text=True, timeout=20, check=False
        ).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", out)
    return tuple(int(g) for g in match.groups()) if match else None


def _plugin_active(cwd: Path) -> str | None:
    """The id of an enabled maskflow-agent Claude Code plugin that applies to
    `cwd` (user scope, or a project/local install for this directory)."""
    exe = shutil.which("claude")
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "plugin", "list", "--json"],
            capture_output=True, text=True, timeout=30, check=False, cwd=cwd,
        ).stdout  # fmt: skip
        entries = json.loads(out or "[]")
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return None
    here = cwd.resolve()
    for entry in entries if isinstance(entries, list) else []:
        if not isinstance(entry, dict) or not str(entry.get("id", "")).startswith(
            "maskflow-agent@"
        ):
            continue
        if not entry.get("enabled"):
            continue
        project = entry.get("projectPath")
        if entry.get("scope") == "user" or (project and Path(project).resolve() == here):
            return str(entry["id"])
    return None


class _Report:
    def __init__(self) -> None:
        self.failed = 0

    def check(self, ok: bool, label: str, hint: str = "") -> bool:
        print(f"  {'ok  ' if ok else 'FAIL'}  {label}")
        if not ok:
            self.failed += 1
            if hint:
                print(f"        {hint}")
        return ok

    def note(self, label: str) -> None:
        print(f"  --    {label}")


def run(cwd: Path) -> int:
    report = _Report()
    print("maskflow-agent doctor")

    report.check(hasattr(socket, "AF_UNIX"), "unix sockets available (macOS/Linux)")
    version = _claude_version()
    if version is None:
        report.note("claude CLI not found on PATH -- skipping version check")
    else:
        report.check(
            version >= MIN_CLAUDE,
            f"Claude Code {'.'.join(map(str, version))} >= {'.'.join(map(str, MIN_CLAUDE))}",
            "Upgrade Claude Code: older versions can't block a tool when the guard fails.",
        )

    from . import adapters

    others: list[str] = []
    for agent in adapters.AGENTS:
        module = adapters.load(agent)
        for scope in ("project", "user"):
            path = module.config_path(scope, cwd)
            if module.is_installed(path):
                others.append(agent)
                report.note(f"{agent} hooks in {path} ({adapters.STATUS[agent]})")

    scopes = {
        s: install.installed(install.settings_path(s, cwd)) for s in ("project", "local", "user")
    }
    active = [s for s, events in scopes.items() if events]
    plugin = _plugin_active(cwd)
    if not active and not plugin and others:
        report.note("Claude Code hooks not installed (other agents are)")
    elif plugin:
        report.note(f"Claude Code plugin {plugin} is enabled for this project")
        report.check(
            not active,
            "hooks installed once (plugin only)",
            f"Also found in {', '.join(active)} settings -- every hook would run twice. "
            "Run `maskflow-agent uninstall --scope <scope>` or remove the plugin.",
        )
    elif report.check(
        bool(active),
        "hooks installed",
        "Run `maskflow-agent install`, or install the Claude Code plugin "
        "(/plugin install maskflow-agent@maskflow).",
    ):
        for scope in active:
            missing = sorted(set(install.EXPECTED_EVENTS) - set(scopes[scope]))
            report.check(
                not missing,
                f"{scope} settings has all hooks" + (f" (missing {missing})" if missing else ""),
                "Re-run `maskflow-agent install`.",
            )

    canaries = _canaries()
    session = f"doctor-{uuid.uuid4().hex[:12]}"
    row = f"1,{canaries['AADHAAR']},{canaries['PAN']},{canaries['INDIAN_MOBILE']}"
    csv = "id,aadhaar,pan,mobile\n" + row + "\n"
    try:
        code, out = _run_hook(
            "session-start", {"session_id": session, "hook_event_name": "SessionStart"}
        )
        started = code == 0 and protocol.ping(session)
        report.check(
            started, "daemon starts for a session", f"See the log: {paths.log_path(session)}"
        )
        if started and not protocol.request(session, "ping").get("ner"):
            report.note(
                "spaCy model missing: IDs/numbers are masked, names/addresses are NOT. "
                "Fix: python -m spacy download en_core_web_sm"
            )

        shapes = {
            "Bash": {"stdout": csv, "stderr": "", "interrupted": False, "isImage": False},
            "Read": {"type": "text", "file": {"filePath": "/tmp/x.csv", "content": csv}},
            "Grep": {"mode": "content", "content": row, "numLines": 1},
        }
        for tool, response in shapes.items():
            code, out = _run_hook(
                "post-tool-use",
                {"session_id": session, "tool_name": tool, "tool_response": response},
            )
            leaked = [k for k, v in canaries.items() if v in out]
            report.check(
                code == 0 and not leaked and "<AADHAAR_" in out,
                f"{tool} output masked" + (f" -- LEAKED {leaked}" if leaked else ""),
            )

        for agent in sorted(set(others)):
            module = adapters.load(agent)
            event, payload = module.probe(session, csv)
            proc = subprocess.run(
                [sys.executable, "-m", "maskflow_agent", "hook", "--agent", agent, event],
                input=json.dumps(payload), capture_output=True, text=True, timeout=180,
                check=False,
            )  # fmt: skip
            if hasattr(module, "rewritten"):  # wrap mode: run the rewritten command
                try:
                    command = module.rewritten(json.loads(proc.stdout or "{}"), proc.stderr)
                except ValueError:
                    command = None
                if command is None:
                    report.check(False, f"{agent} hook wraps shell commands")
                    continue
                proc = subprocess.run(
                    ["bash", "-c", command], capture_output=True, text=True, timeout=180,
                    check=False,
                )  # fmt: skip
            leaked = [k for k, v in canaries.items() if v in proc.stdout]
            report.check(
                proc.returncode == 0 and not leaked and "<AADHAAR_" in proc.stdout,
                f"{agent} hook masks tool output" + (f" -- LEAKED {leaked}" if leaked else ""),
            )

        code, out = _run_hook(
            "pre-tool-use",
            {
                "session_id": session,
                "tool_name": "Edit",
                "tool_input": {"file_path": "x", "old_string": "<AADHAAR_1>", "new_string": "y"},
            },
        )
        report.check(
            '"deny"' in out and "placeholders" in out,
            "edits containing placeholders are refused",
        )

        command = "echo 'aadhaar <AADHAAR_1>'"
        ticket = protocol.request(session, "issue_ticket", command=command)["ticket"]
        wrapper = [sys.executable, "-m", "maskflow_agent", "exec", "--session", session]
        proc = subprocess.run(
            [*wrapper, "--ticket", ticket, "--", command],
            capture_output=True, text=True, timeout=60, check=False,
        )  # fmt: skip
        report.check(
            proc.returncode == 0 and canaries["AADHAAR"] not in proc.stdout + proc.stderr,
            "run-time unmask wrapper re-masks its output",
        )
        replay = subprocess.run(
            [*wrapper, "--ticket", ticket, "--", command],
            capture_output=True, text=True, timeout=60, check=False,
        )  # fmt: skip
        report.check(
            replay.returncode == 97, "a spent ticket can't unmask again (no direct wrapper use)"
        )
    finally:
        try:
            protocol.request(session, "end", timeout=5)
        except protocol.DaemonUnavailable:
            pass
        paths.summary_path(session).unlink(missing_ok=True)
        if not report.failed:
            paths.log_path(session).unlink(missing_ok=True)

    dead = f"doctor-dead-{uuid.uuid4().hex[:8]}"
    code, out = _run_hook(
        "post-tool-use",
        {"session_id": dead, "tool_name": "Bash", "tool_response": {"stdout": csv}},
    )
    report.check(
        code == 0 and not any(v in out for v in canaries.values()) and "withheld" in out,
        "guard down -> output withheld, not passed through",
    )

    print("all checks passed" if not report.failed else f"{report.failed} check(s) failed")
    return 0 if not report.failed else 1
