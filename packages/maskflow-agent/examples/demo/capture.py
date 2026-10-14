"""Extract what the MODEL saw in a Claude Code session into demo JSON.

    python capture.py <session.jsonl> <out.json>

Reads the transcript Claude Code wrote (~/.claude/projects/<dir>/<id>.jsonl):
the prompt, each Bash command the model issued, the tool result it was
given back, and its final answer. All values in the demo database are
SYNTHETIC (see make_db.py), so the captured JSON is safe to commit.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def _text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(_text(c.get("text", "")) for c in content if isinstance(c, dict))
    return ""


def capture(path: str) -> dict[str, Any]:
    prompt, final = "", ""
    steps: list[dict[str, str]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            message = entry.get("message") or {}
            content = message.get("content")
            if entry.get("type") == "user" and isinstance(content, str) and not prompt:
                prompt = content
            if not isinstance(content, list):
                continue
            for block in content:
                if block.get("type") == "tool_use" and block.get("name") == "Bash":
                    steps.append({"command": block["input"].get("command", ""), "result": ""})
                elif block.get("type") == "tool_result" and steps:
                    steps[-1]["result"] = _text(block.get("content")).strip()
                elif block.get("type") == "text" and entry.get("type") == "assistant":
                    final = block.get("text", "")
    return {"prompt": prompt, "steps": steps, "final": final}


if __name__ == "__main__":
    data = capture(sys.argv[1])
    with open(sys.argv[2], "w", encoding="utf-8") as out:
        json.dump(data, out, indent=2, ensure_ascii=False)
    print(f"{len(data['steps'])} commands captured -> {sys.argv[2]}")
