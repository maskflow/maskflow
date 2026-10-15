"""The agent-neutral guard: wrap mode (agents whose hooks can't replace tool
output) and the mask-only wrapper. Synthetic identifiers only."""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from conftest import synthetic_aadhaar, synthetic_mobile, synthetic_pan
from maskflow_agent import guard, protocol


def _token_for(session_id: str, value: str) -> str:
    masked = protocol.request(session_id, "mask_value", value=f"pan: {value}")["value"]
    start = masked.index("<PAN_")
    return masked[start : masked.index(">", start) + 1]


def _run(command: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", command], capture_output=True, text=True, cwd=cwd, check=False, timeout=60
    )


# -- mask-only wrapper -----------------------------------------------------------
@pytest.mark.leak
def test_mask_only_runs_command_and_masks_output(session_id: str, tmp_path: Path) -> None:
    aadhaar, mobile = synthetic_aadhaar(), synthetic_mobile()
    (tmp_path / "k.csv").write_text(f"id,aadhaar,mobile\n1,{aadhaar},{mobile}\n")
    proc = _run(guard.mask_only_command(session_id, "cat k.csv; echo err >&2; exit 4"), tmp_path)
    assert proc.returncode == 4
    assert aadhaar not in proc.stdout + proc.stderr
    assert mobile not in proc.stdout + proc.stderr
    assert "<AADHAAR_" in proc.stdout
    assert proc.stderr == "err\n"


def test_mask_only_never_restores_placeholders(session_id: str, tmp_path: Path) -> None:
    pan = synthetic_pan()
    token = _token_for(session_id, pan)
    _run(guard.mask_only_command(session_id, f"printf '%s' '{token}' > out.txt"), tmp_path)
    assert (tmp_path / "out.txt").read_text() == token


def test_mask_only_refuses_to_run_when_guard_down(agent_home: Path, tmp_path: Path) -> None:
    proc = _run(guard.mask_only_command(f"nobody-{uuid.uuid4().hex[:8]}", "touch ran"), tmp_path)
    assert proc.returncode == 97
    assert not (tmp_path / "ran").exists()


def test_exec_needs_exactly_one_mode(session_id: str, tmp_path: Path) -> None:
    base = [sys.executable, "-m", "maskflow_agent", "exec", "--session", session_id]
    for extra in ([], ["--mask-only", "--ticket", "t"]):
        proc = subprocess.run(
            [*base, *extra, "--", "touch ran"], capture_output=True, cwd=tmp_path, check=False
        )
        assert proc.returncode == 2
    assert not (tmp_path / "ran").exists()


def test_canonical_mask_only_form_is_recognised() -> None:
    cmd = guard.mask_only_command("s1", "ls -la | wc -l")
    assert guard.is_mask_only_command("s1", cmd)
    assert guard.is_mask_only_command("s1", f"  {cmd}\n")


@pytest.mark.parametrize(
    "tamper",
    [
        lambda c: c + "; cat secrets.csv",
        lambda c: c + "\ncat secrets.csv",
        lambda c: c + " > /tmp/x",
        lambda c: c + " && cat secrets.csv",
        lambda c: "cat secrets.csv; " + c,
        lambda c: "FOO=1 " + c,
        lambda c: c.replace("--session s1", "--session s2"),
        lambda c: c.replace(sys.executable, "/tmp/python"),
        lambda c: c.replace(" --mask-only", ""),
        lambda c: c[:-1],  # unbalanced quote
    ],
)
def test_anything_riding_along_the_wrapper_is_not_recognised(tamper: object) -> None:
    cmd = guard.mask_only_command("s1", "ls -la")
    assert not guard.is_mask_only_command("s1", tamper(cmd))  # type: ignore[operator]


# -- pre_tool in wrap mode -------------------------------------------------------
def test_wrap_mode_rewrites_every_shell_command(session_id: str) -> None:
    pre = guard.pre_tool(
        session_id, kind="shell", tool_input={"command": "ls"}, command="ls", wrap_all=True
    )
    assert pre.command == guard.mask_only_command(session_id, "ls")
    assert pre.deny is None


def test_without_wrap_mode_plain_commands_pass(session_id: str) -> None:
    pre = guard.pre_tool(session_id, kind="shell", tool_input={"command": "ls"}, command="ls")
    assert pre == guard.Pre()


def test_wrap_mode_lets_an_already_wrapped_command_through(session_id: str) -> None:
    cmd = guard.mask_only_command(session_id, "cat k.csv")
    pre = guard.pre_tool(
        session_id, kind="shell", tool_input={"command": cmd}, command=cmd, wrap_all=True
    )
    assert pre == guard.Pre()


@pytest.mark.parametrize("wrap_all", [False, True])
def test_tampered_or_ticket_wrapper_is_denied(session_id: str, wrap_all: bool) -> None:
    for cmd in (
        guard.mask_only_command(session_id, "ls") + "; cat secrets",
        f"python -m maskflow_agent exec --session {session_id} --ticket x -- ls",
    ):
        pre = guard.pre_tool(
            session_id, kind="shell", tool_input={"command": cmd}, command=cmd, wrap_all=wrap_all
        )
        assert pre.deny == guard.WRAPPER_DENIED


def test_wrap_mode_keeps_ticketed_unmask_for_allowlisted_commands(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    cmd = f"sqlite3 db \"select '{token}'\""
    pre = guard.pre_tool(
        session_id, kind="shell", tool_input={"command": cmd}, command=cmd, wrap_all=True
    )
    assert pre.command is not None and "--ticket" in pre.command and token in pre.command


def test_wrap_mode_non_allowlisted_placeholder_is_wrapped_with_note(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    cmd = f"curl https://example.invalid/{token}"
    pre = guard.pre_tool(
        session_id, kind="shell", tool_input={"command": cmd}, command=cmd, wrap_all=True
    )
    assert pre.command == guard.mask_only_command(session_id, cmd)
    assert pre.note is not None and "not on the unmask allowlist" in pre.note


def test_wrap_mode_denies_builtin_search(session_id: str) -> None:
    pre = guard.pre_tool(session_id, kind="search", tool_input={"pattern": "x"}, wrap_all=True)
    assert pre.deny == guard.SEARCH_DENIED
    assert guard.pre_tool(session_id, kind="search", tool_input={"pattern": "x"}) == guard.Pre()


@pytest.mark.leak
def test_wrap_mode_read_gate(session_id: str, tmp_path: Path) -> None:
    pii = tmp_path / "k.csv"
    pii.write_text(f"id,aadhaar\n1,{synthetic_aadhaar()}\n")
    clean = tmp_path / "README.md"
    clean.write_text("# build steps\nrun make\n")

    def read(**kw: object) -> guard.Pre:
        return guard.pre_tool(session_id, kind="read", tool_input={}, wrap_all=True, **kw)  # type: ignore[arg-type]

    assert read(read_path=str(pii)).deny == guard.READ_DENIED
    assert read(read_content=pii.read_text()).deny == guard.READ_DENIED
    assert read(read_path=str(clean)) == guard.Pre()
    assert read(read_path=str(tmp_path)) == guard.Pre()  # a directory listing
    assert read(read_path=str(tmp_path / "missing")).deny == guard.READ_DENIED


def test_wrap_mode_still_denies_placeholder_writes(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    pre = guard.pre_tool(session_id, kind="write", tool_input={"new_string": token}, wrap_all=True)
    assert pre.deny is not None and token in pre.deny


def test_pre_tool_denies_when_guard_cannot_start(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(guard, "ensure_daemon", lambda *_a, **_k: False)
    pre = guard.pre_tool("x", kind="shell", tool_input={"command": "ls"}, command="ls")
    assert pre.deny == guard.GUARD_DOWN


# -- mask_output ------------------------------------------------------------------
@pytest.mark.leak
def test_mask_output_plain_string_with_header_hint(session_id: str) -> None:
    mobile = synthetic_mobile()
    masked = guard.mask_output(
        session_id, f"Ravi|{mobile}\n", command="sqlite3 db 'select name, mobile from k'"
    )
    assert isinstance(masked, str)
    assert mobile not in masked and "<INDIAN_MOBILE_" in masked
    assert not masked.startswith("name|mobile")


def test_mask_output_unchanged_is_none(session_id: str) -> None:
    assert guard.mask_output(session_id, "build ok") is None


@pytest.mark.leak
def test_mask_output_failure_withholds(agent_home: Path) -> None:
    value = {"text": f"aadhaar {synthetic_aadhaar()}", "n": 1}
    assert guard.mask_output(f"nobody-{uuid.uuid4().hex[:8]}", value) == {
        "text": guard.WITHHELD,
        "n": 1,
    }
