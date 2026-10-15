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
import sys
from typing import Any

from . import guard, protocol

# Re-exported: the plugin, doctor and tests use these names.
WITHHELD = guard.WITHHELD
CONTEXT = guard.CONTEXT
withheld = guard.withheld
ensure_daemon = guard.ensure_daemon
_select_columns = guard.select_columns
_with_header_hint = guard.with_header_hint

_WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}


# -- helpers ----------------------------------------------------------------
def _emit(obj: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(obj, ensure_ascii=False))
    sys.stdout.flush()


def _kind(tool: str) -> str:
    if tool == "Bash":
        return "shell"
    if tool in _WRITE_TOOLS:
        return "write"
    return "other"


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
    from . import config

    tool = payload.get("tool_name", "")
    tool_input = payload.get("tool_input") or {}
    command = tool_input.get("command") if tool == "Bash" else None
    cwd = payload.get("cwd")
    pre = guard.pre_tool(
        payload["session_id"],
        kind=_kind(tool),
        tool_input=tool_input,
        command=command if isinstance(command, str) else None,
        cwd=cwd,
        transcript_path=payload.get("transcript_path"),
        user_rule=lambda c: config.user_bash_decision(c, cwd),
    )
    if pre.deny is not None:
        _deny(pre.deny)
        return
    if pre.command is not None:
        decision: dict[str, Any] = {
            "hookEventName": "PreToolUse",
            "updatedInput": {**tool_input, "command": pre.command},
        }
        if pre.permission is not None:
            decision["permissionDecision"] = pre.permission
            decision["permissionDecisionReason"] = (
                "maskflow: placeholders are restored to real values when this runs"
            )
        _emit({"hookSpecificOutput": decision})
        return
    if pre.note is not None:
        _emit(
            {"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": pre.note}}
        )


def post_tool_use(payload: dict[str, Any]) -> None:
    response = payload.get("tool_response")
    command = (payload.get("tool_input") or {}).get("command")
    masked = guard.mask_output(
        payload["session_id"],
        response,
        command if payload.get("tool_name") == "Bash" and isinstance(command, str) else None,
    )
    if masked is None:
        return
    _emit({"hookSpecificOutput": {"hookEventName": "PostToolUse", "updatedToolOutput": masked}})


def user_prompt_submit(payload: dict[str, Any]) -> None:
    from . import config

    cfg = config.load(payload.get("cwd"))
    if cfg.prompt_mode == "off":
        return
    found = guard.prompt_findings(payload["session_id"], str(payload.get("prompt", "")))
    if found is None:
        return
    if cfg.prompt_mode == "block":
        _emit(
            {
                "decision": "block",
                "reason": guard.prompt_blocked(found),
                "suppressOriginalPrompt": True,
            }
        )
        return
    _emit({"systemMessage": guard.prompt_warning(found)})


def session_end(payload: dict[str, Any]) -> None:
    guard.end_session(payload["session_id"])


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
