"""Claude Code hook handlers. Stdlib only -- each hook is a fresh process.

    maskflow-agent hook session-start | pre-tool-use | post-tool-use
                        | user-prompt-submit | session-end

Each reads the hook's JSON payload on stdin and prints a JSON decision.

Failure policy (the point of the whole package): no code path may let a raw
tool result through because something went wrong.
* post-tool-use: any error -> the result is replaced by a same-shaped
  "withheld" stub. (Claude Code can't hide the original if this process
  *crashes*, so the work here is kept tiny and wrapped in a catch-all.)
* pre-tool-use: installed with `onFailure: "block"`, and denies the call
  itself when the daemon is down and can't be restarted -- so a tool never
  runs while its output can't be masked.
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from typing import Any

from . import paths, protocol

WITHHELD = (
    "[maskflow: output withheld -- the PII guard could not mask it. Run `maskflow-agent doctor`.]"
)
_TOKEN_RE = re.compile(r"<[A-Z][A-Z_]*?_\d+(?:_[0-9a-f]+)?>")
_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
_WRAPPER_RE = re.compile(r"maskflow[_-]agent\b.*\bexec\b|maskflow_agent\.execwrap", re.S)
_START_TIMEOUT = 45.0

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


# -- helpers ----------------------------------------------------------------
def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


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


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    return []


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
    seen for a different value."""
    if protocol.ping(session_id):
        return True
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
    deadline = time.monotonic() + _START_TIMEOUT
    while time.monotonic() < deadline:
        if protocol.ping(session_id, timeout=1.0):
            tokens = _transcript_tokens(transcript_path)
            if tokens:
                try:
                    protocol.request(session_id, "reserve", tokens=tokens)
                except protocol.DaemonUnavailable:
                    return False
            return True
        time.sleep(0.2)
    return False


# -- handlers -----------------------------------------------------------------
def session_start(payload: dict[str, Any]) -> None:
    ok = ensure_daemon(payload["session_id"], payload.get("transcript_path"))
    out: dict[str, Any] = {
        "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": CONTEXT}
    }
    if not ok:
        out["systemMessage"] = (
            "MaskFlow PII guard failed to start; tool calls will be blocked until it "
            "does. Run `maskflow-agent doctor`."
        )
    _emit(out)


def _deny(reason: str) -> None:
    _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def pre_tool_use(payload: dict[str, Any]) -> None:
    session_id = payload["session_id"]
    if not ensure_daemon(session_id, payload.get("transcript_path")):
        _deny(
            "MaskFlow PII guard is not running for this session, so this tool's output "
            "could not be masked. Ask the user to run `maskflow-agent doctor`."
        )
        return

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    text = "\n".join(_strings(tool_input))
    if tool == "Bash" and _WRAPPER_RE.search(text):
        _deny("Commands may not invoke the MaskFlow unmask wrapper directly.")
        return
    if "<" not in text:
        return
    tokens = protocol.request(session_id, "tokens_in", text=text).get("tokens", [])
    if not tokens:
        return

    if tool in _WRITE_TOOLS:
        _deny(
            f"This edit contains MaskFlow placeholders ({', '.join(tokens[:3])}). They "
            "stand for real values that the model never sees, and are never converted "
            "back inside files -- writing them would replace real data with "
            "placeholders. Edit around them, or ask the user to make this change."
        )
        return

    if tool == "Bash" and isinstance(tool_input.get("command"), str):
        import shlex

        from . import config

        command = tool_input["command"]
        cfg = config.load(payload.get("cwd"))
        if config.is_unmask_allowed(command, cfg.unmask_allow):
            user_rule = config.user_bash_decision(command, payload.get("cwd"))
            if user_rule == "deny":
                _deny("This command matches one of your Bash deny rules.")
                return
            ticket = protocol.request(session_id, "issue_ticket", command=command)["ticket"]
            wrapped = shlex.join(
                [sys.executable, "-m", "maskflow_agent", "exec",
                 "--session", session_id, "--ticket", ticket, "--"]
            )  # fmt: skip
            new_input = dict(tool_input)
            new_input["command"] = f"{wrapped} {shlex.quote(command)}"
            decision: dict[str, Any] = {
                "hookEventName": "PreToolUse",
                "updatedInput": new_input,
            }
            # Never grant more than the user already had: auto-approve only
            # when their own allow rules cover the original command. With no
            # decision, Claude Code's normal permission flow (prompt / auto
            # mode) judges the wrapped command.
            if user_rule in ("allow", "ask"):
                decision["permissionDecision"] = user_rule
                decision["permissionDecisionReason"] = (
                    "maskflow: placeholders are restored to real values when this runs"
                )
            _emit({"hookSpecificOutput": decision})
            return
        _emit(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "additionalContext": (
                        "MaskFlow: this command is not on the unmask allowlist, so "
                        f"{', '.join(tokens[:3])} were passed literally, not as real values."
                    ),
                }
            }
        )


def post_tool_use(payload: dict[str, Any]) -> None:
    response = payload.get("tool_response")
    try:
        result = protocol.request(payload["session_id"], "mask_value", value=response)
        if not result.get("changed"):
            return
        masked = result["value"]
    except Exception:  # noqa: BLE001 -- fail closed on anything
        masked = withheld(response)
    _emit({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": masked}})


def user_prompt_submit(payload: dict[str, Any]) -> None:
    from . import config

    cfg = config.load(payload.get("cwd"))
    if cfg.prompt_mode == "off":
        return
    try:
        counts = protocol.request(
            payload["session_id"], "scan", text=str(payload.get("prompt", ""))
        ).get("counts", {})
    except protocol.DaemonUnavailable:
        return
    if not counts:
        return
    found = ", ".join(f"{label} x{n}" for label, n in sorted(counts.items()))
    if cfg.prompt_mode == "block":
        _emit(
            {
                "decision": "block",
                "reason": (
                    f"MaskFlow: your prompt contains personal data ({found}). It was not "
                    "sent. Remove it, or reference the record by a non-personal key."
                ),
                "suppressOriginalPrompt": True,
            }
        )
        return
    _emit(
        {
            "systemMessage": (
                f"MaskFlow: your prompt contains personal data ({found}) and was sent to "
                "the model as typed -- prompts can't be masked. Tool results are masked."
            )
        }
    )


def session_end(payload: dict[str, Any]) -> None:
    try:
        protocol.request(payload["session_id"], "end", timeout=1.0)
    except protocol.DaemonUnavailable:
        pass


HANDLERS = {
    "session-start": session_start,
    "pre-tool-use": pre_tool_use,
    "post-tool-use": post_tool_use,
    "user-prompt-submit": user_prompt_submit,
    "session-end": session_end,
}


def main(event: str) -> int:
    handler = HANDLERS[event]
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict) or not isinstance(payload.get("session_id"), str):
            raise ValueError
    except ValueError:
        if event == "post-tool-use":
            _emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "updatedToolOutput": WITHHELD,
                    }
                }
            )
            return 0
        sys.stderr.write("maskflow-agent: unreadable hook payload\n")
        return 1
    if event == "post-tool-use":
        try:
            handler(payload)
        except Exception:  # noqa: BLE001 -- last-resort fail-closed
            _emit(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PostToolUse",
                        "updatedToolOutput": withheld(payload.get("tool_response")),
                    }
                }
            )
        return 0
    try:
        handler(payload)
    except protocol.DaemonUnavailable as exc:
        if event == "pre-tool-use":
            _deny(f"MaskFlow PII guard error: {exc}. Ask the user to run `maskflow-agent doctor`.")
            return 0
        sys.stderr.write(f"maskflow-agent: {exc}\n")
        return 1
    return 0
