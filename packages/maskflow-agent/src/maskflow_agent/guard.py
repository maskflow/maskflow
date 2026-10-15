"""Agent-neutral guard logic shared by every agent's hook adapter. Stdlib
only -- it runs in a fresh process on every tool call.

An adapter (`hooks.py` for Claude Code, `adapters/*` for the others) reads
its agent's payload, calls `pre_tool` / `mask_output` / `scan_prompt` here,
and translates the result into that agent's JSON. Decisions are made only
here, so every agent gets the same policy:

* tool output is masked; on any failure it is withheld, never passed raw;
* placeholders are restored only inside allowlisted commands, at run time,
  through a single-use ticket -- never inside file writes;
* agents whose hooks can't rewrite tool output (`wrap_all`) get every shell
  command rewritten into the mask-only wrapper, and their built-in search
  and PII-holding file reads are denied with a hint to use the shell.
"""

from __future__ import annotations

import os
import re
import shlex
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from . import paths, protocol

WITHHELD = (
    "[maskflow: output withheld -- the PII guard could not mask it. Run `maskflow-agent doctor`.]"
)
GUARD_DOWN = (
    "MaskFlow PII guard is not running for this session, so this tool's output "
    "could not be masked. Ask the user to run `maskflow-agent doctor`."
)
WRAPPER_DENIED = "Commands may not invoke the MaskFlow unmask wrapper directly."
SEARCH_DENIED = (
    "MaskFlow PII guard: this agent's built-in search returns file contents the "
    "guard can't mask. Search with the shell instead (e.g. `rg -n PATTERN`); "
    "shell output is masked."
)
READ_DENIED = (
    "MaskFlow PII guard: this file contains personal data and this agent's file "
    "reader can't mask it. Read it with the shell instead (e.g. `cat FILE` or "
    "`sed -n 1,200p FILE`); shell output is masked."
)
_TOKEN_RE = re.compile(r"<[A-Z][A-Z_]*?_\d+(?:_[0-9a-f]+)?>")
_WRAPPER_RE = re.compile(r"maskflow[_-]agent\b.*\bexec\b|maskflow_agent\.execwrap", re.S)
# A cold first start after `pip install` (bytecode compile + spaCy) took 26 s
# on an M-series-class laptop; leave generous room on slower machines.
_START_TIMEOUT = 150.0
# Files larger than this are not scanned by the read gate; they are denied
# (the shell route still works and is masked).
_READ_SCAN_LIMIT = 8 * 1024 * 1024

CONTEXT = (
    "MaskFlow PII guard is active. Personal data in tool results (Aadhaar, PAN, "
    "UPI IDs, phone numbers, bank accounts, names, ...) is replaced with "
    "placeholders like <AADHAAR_1> or <INDIAN_MOBILE_3>; the same value always "
    "gets the same placeholder in this session. Use placeholders verbatim. In "
    "allowlisted database/kubectl commands (psql, mysql, sqlite3, ...) they are "
    "replaced with the real values when the command runs, so e.g. "
    "`psql -c \"UPDATE kyc SET status='ok' WHERE pan='<PAN_3>'\"` updates the right "
    "row. They are never converted back inside file edits. Do not try to decode, "
    "hex-dump or otherwise recover the hidden values."
)


# -- output shapes ----------------------------------------------------------
def withheld(value: Any) -> Any:
    """Same shape as `value`, every string leaf replaced (Claude Code ignores
    a replacement whose shape doesn't match a built-in tool's schema, so the
    stub must keep keys and types)."""
    if isinstance(value, str):
        return WITHHELD if value else value
    if isinstance(value, list):
        return [withheld(v) for v in value]
    if isinstance(value, dict):
        return {k: withheld(v) for k, v in value.items()}
    return value


def strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in strings(v)]
    return []


# -- daemon lifecycle -------------------------------------------------------
def _daemon_cmd(session_id: str) -> list[str]:
    return [sys.executable, "-m", "maskflow_agent", "daemon", "--session", session_id]


def _transcript_tokens(transcript_path: str | None) -> list[str]:
    if not transcript_path or not os.path.isfile(transcript_path):
        return []
    try:
        with open(transcript_path, encoding="utf-8", errors="replace") as f:
            return sorted({m.group(0) for m in _TOKEN_RE.finditer(f.read())})
    except OSError:
        return []


def ensure_daemon(session_id: str, transcript_path: str | None = None) -> bool:
    """Start the session's daemon if it isn't answering. A (re)started
    daemon first reserves every placeholder already in the transcript, so a
    value seen from now on can never be given a name the model has already
    seen for a different value.

    Hooks fire in parallel, and a cold first start (fresh install: bytecode
    compile + spaCy load) can take tens of seconds. So: one spawner at a time
    (a start lock), and a daemon that is alive but still loading (its pid
    file) is waited for, never duplicated."""
    if protocol.ping(session_id):
        return True
    import fcntl

    deadline = time.monotonic() + _START_TIMEOUT
    with open(paths.start_lock_path(session_id), "a") as lock:
        while True:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() > deadline:
                    return False
                time.sleep(0.2)
        try:
            if protocol.ping(session_id):
                return True  # another hook started it while we waited
            if paths.live_pid(session_id) is None:
                _spawn(session_id)
            while time.monotonic() < deadline:
                if protocol.ping(session_id, timeout=1.0):
                    return _reserve(session_id, transcript_path)
                time.sleep(0.2)
            return False
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _spawn(session_id: str) -> None:
    import subprocess

    log = open(paths.log_path(session_id), "ab")  # noqa: SIM115 -- handed to the child
    try:
        subprocess.Popen(
            _daemon_cmd(session_id),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=log,
            start_new_session=True,
            close_fds=True,
        )
    finally:
        log.close()


def _reserve(session_id: str, transcript_path: str | None) -> bool:
    tokens = _transcript_tokens(transcript_path)
    if not tokens:
        return True
    try:
        protocol.request(session_id, "reserve", tokens=tokens)
    except protocol.DaemonUnavailable:
        return False
    return True


# -- the mask-only wrapper --------------------------------------------------
def mask_only_command(session_id: str, command: str) -> str:
    """`command` rewritten to run inside the mask-only wrapper: it runs
    unchanged and its stdout/stderr are masked before the agent sees them.
    Restores nothing, so it needs no ticket."""
    return shlex.join(
        [sys.executable, "-m", "maskflow_agent", "exec",
         "--session", session_id, "--mask-only", "--", command]
    )  # fmt: skip


def is_mask_only_command(session_id: str, command: str) -> bool:
    """True only for the exact canonical form `mask_only_command` produces
    for this session -- so nothing can ride along outside the wrapper
    (`...; cat secrets`, a newline, a redirect, another interpreter)."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return False
    return (
        len(argv) == 9
        and argv[0] == sys.executable
        and argv[1:7] == ["-m", "maskflow_agent", "exec", "--session", session_id, "--mask-only"]
        and argv[7] == "--"
        and mask_only_command(session_id, argv[8]) == command.strip()
    )


# -- pre-tool decision ------------------------------------------------------
@dataclass(frozen=True)
class Pre:
    """What to do before a tool runs. All None: let it run unchanged."""

    deny: str | None = None  # reason shown to the agent
    command: str | None = None  # replacement shell command
    permission: str | None = None  # "allow"/"ask" to pass with `command`
    note: str | None = None  # extra context for the model


def pre_tool(
    session_id: str,
    *,
    kind: str,
    tool_input: Any,
    command: str | None = None,
    cwd: str | None = None,
    transcript_path: str | None = None,
    wrap_all: bool = False,
    user_rule: Callable[[str], str | None] | None = None,
    read_path: str | None = None,
    read_content: str | None = None,
) -> Pre:
    """`kind` is one of shell | write | read | search | other.

    `wrap_all` is for agents whose hooks can't replace tool output after the
    fact: every shell command is rewritten into the mask-only wrapper, built-in
    search is denied, and a built-in read is denied when the file holds PII.
    `user_rule(command)` returns the user's own allow/ask/deny rule for a
    shell command, if the agent has such rules."""
    if not ensure_daemon(session_id, transcript_path):
        return Pre(deny=GUARD_DOWN)

    text = "\n".join(strings(tool_input))
    if kind == "shell" and _WRAPPER_RE.search(text):
        if wrap_all and command is not None and is_mask_only_command(session_id, command):
            return Pre()
        return Pre(deny=WRAPPER_DENIED)
    if wrap_all and kind == "search":
        return Pre(deny=SEARCH_DENIED)
    if wrap_all and kind == "read":
        if _read_has_pii(session_id, read_path, read_content):
            return Pre(deny=READ_DENIED)
        return Pre()

    tokens: list[str] = []
    if "<" in text:
        tokens = protocol.request(session_id, "tokens_in", text=text).get("tokens", [])
    if not tokens:
        if wrap_all and kind == "shell" and command is not None:
            return Pre(command=mask_only_command(session_id, command))
        return Pre()

    if kind == "write":
        return Pre(
            deny=(
                f"This edit contains MaskFlow placeholders ({', '.join(tokens[:3])}). They "
                "stand for real values that the model never sees, and are never converted "
                "back inside files -- writing them would replace real data with "
                "placeholders. Edit around them, or ask the user to make this change."
            )
        )

    if kind == "shell" and command is not None:
        from . import config

        cfg = config.load(cwd)
        if config.is_unmask_allowed(command, cfg.unmask_allow):
            rule = user_rule(command) if user_rule is not None else None
            if rule == "deny":
                return Pre(deny="This command matches one of your Bash deny rules.")
            ticket = protocol.request(session_id, "issue_ticket", command=command)["ticket"]
            wrapped = shlex.join(
                [sys.executable, "-m", "maskflow_agent", "exec",
                 "--session", session_id, "--ticket", ticket, "--"]
            )  # fmt: skip
            # Never grant more than the user already had: auto-approve only
            # when their own allow rules cover the original command. With no
            # decision, the agent's normal permission flow judges the
            # wrapped command.
            return Pre(
                command=f"{wrapped} {shlex.quote(command)}",
                permission=rule if rule in ("allow", "ask") else None,
            )
        note = (
            "MaskFlow: this command is not on the unmask allowlist, so "
            f"{', '.join(tokens[:3])} were passed literally, not as real values."
        )
        if wrap_all:
            return Pre(command=mask_only_command(session_id, command), note=note)
        return Pre(note=note)
    return Pre()


def _read_has_pii(session_id: str, path: str | None, content: str | None) -> bool:
    """Whether a built-in read would show personal data. Unreadable, binary
    or oversized files count as PII (deny; the shell route stays open)."""
    if content is None:
        if not path:
            return False
        try:
            if os.path.isdir(path):
                return False
            if os.path.getsize(path) > _READ_SCAN_LIMIT:
                return True
            with open(path, "rb") as f:
                content = f.read().decode("utf-8", errors="replace")
        except OSError:
            return True
    if not content:
        return False
    counts = protocol.request(session_id, "scan", text=content).get("counts", {})
    return bool(counts)


# -- post-tool masking ------------------------------------------------------
_SELECT_RE = re.compile(r"\bselect\s+(.{1,2000}?)\s+from\b", re.I | re.S)
_IDENT_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
_DELIMS = ("|", "\t", ",")


def select_columns(command: str) -> list[str] | None:
    """Column names of the command's single SELECT with an explicit column
    list (alias if given, else the last identifier: `k.mobile` -> mobile).
    None for SELECT *, expressions without an alias, or several SELECTs."""
    found = _SELECT_RE.findall(command)
    if len(found) != 1:
        return None
    parts, depth, current = [], 0, ""
    for ch in found[0]:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    columns = []
    for part in parts:
        part = part.strip().strip("\"'`")
        if not part or "*" in part:
            return None
        alias = re.split(r"\s+as\s+", part, flags=re.I)
        name = _IDENT_RE.findall(alias[-1])
        if not name:
            return None
        columns.append(name[-1].lower())
    return columns or None


def with_header_hint(command: str, stdout: str) -> tuple[str, str] | None:
    """(header line, stdout with it prepended) when `stdout` looks like the
    headerless rows of a SELECT whose column names are in `command` --
    `sqlite3` / `psql -t` / `mysql -N` output. The masking engine then reads
    each value under its column name, as it does for any table."""
    columns = select_columns(command)
    first = next((line for line in stdout.splitlines() if line.strip()), "")
    if not columns or len(columns) < 2 or not first:
        return None
    if any(c in first.lower() for c in columns if len(c) > 2):
        return None  # already has a header row
    for delim in _DELIMS:
        if first.count(delim) == len(columns) - 1:
            header = delim.join(columns)
            return header, f"{header}\n{stdout}"
    return None


def _mask(session_id: str, value: Any, command: str | None) -> tuple[bool, Any]:
    header = None
    hinted = value
    if isinstance(command, str):
        if isinstance(value, dict) and isinstance(value.get("stdout"), str):
            hint = with_header_hint(command, value["stdout"])
            if hint is not None:
                header, text = hint
                hinted = {**value, "stdout": text}
        elif isinstance(value, str):
            hint = with_header_hint(command, value)
            if hint is not None:
                header, hinted = hint
    result = protocol.request(session_id, "mask_value", value=hinted)
    if header is not None:
        masked = result["value"]
        out = masked["stdout"] if isinstance(masked, dict) else masked
        if isinstance(out, str) and out.startswith(header + "\n"):
            out = out[len(header) + 1 :]
            masked = {**masked, "stdout": out} if isinstance(masked, dict) else out
            return masked != value, masked
        # never expected; mask it the ordinary way instead
        result = protocol.request(session_id, "mask_value", value=value)
    return bool(result.get("changed")), result["value"]


def mask_output(session_id: str, value: Any, command: str | None = None) -> Any | None:
    """Masked copy of a tool result, or None when it holds nothing to mask.
    Any failure returns the same-shaped withheld stub -- never the original.
    `command` (a shell tool's command line) lets headerless SELECT rows be
    read under their column names."""
    try:
        changed, masked = _mask(session_id, value, command)
    except Exception:  # noqa: BLE001 -- fail closed on anything
        return withheld(value)
    return masked if changed else None


# -- prompts ----------------------------------------------------------------
def prompt_findings(session_id: str, prompt: str) -> str | None:
    """'PAN x1, AADHAAR x2' for a prompt holding personal data, else None
    (also None when the daemon can't be reached: prompts are advisory)."""
    try:
        counts = protocol.request(session_id, "scan", text=prompt).get("counts", {})
    except protocol.DaemonUnavailable:
        return None
    if not counts:
        return None
    return ", ".join(f"{label} x{n}" for label, n in sorted(counts.items()))


def prompt_warning(found: str) -> str:
    return (
        f"MaskFlow: your prompt contains personal data ({found}) and was sent to "
        "the model as typed -- prompts can't be masked. Tool results are masked."
    )


def prompt_blocked(found: str) -> str:
    return (
        f"MaskFlow: your prompt contains personal data ({found}). It was not "
        "sent. Remove it, or reference the record by a non-personal key."
    )


def end_session(session_id: str) -> None:
    try:
        protocol.request(session_id, "end", timeout=1.0)
    except protocol.DaemonUnavailable:
        pass
