"""Guard configuration and the unmask allowlist. Stdlib only.

Config is read from the first of `<cwd>/.claude/maskflow-agent.json`,
`$MASKFLOW_AGENT_HOME/config.json`; missing files mean defaults:

    {
      "unmask_allow": ["psql", "mysql", "kubectl exec"],   // replaces defaults
      "unmask_allow_extra": ["my-db-cli"],                 // added to defaults
      "prompt_mode": "warn"                                // or "block" / "off"
    }

Placeholders are restored only when EVERY simple command in the Bash
command line starts with an allowlisted program. Anything the check can't
read with certainty -- command substitution, backticks, process
substitution, unbalanced quotes -- is treated as not allowlisted, so the
placeholder text is passed through literally.
"""

from __future__ import annotations

import json
import os
import shlex
from pathlib import Path
from typing import NamedTuple

from . import paths

DEFAULT_UNMASK_ALLOW: tuple[str, ...] = (
    "psql",
    "mysql",
    "mariadb",
    "sqlite3",
    "duckdb",
    "mongosh",
    "mongo",
    "redis-cli",
    "clickhouse-client",
    "cqlsh",
    "kubectl exec",
)

PROMPT_MODES = ("warn", "block", "off")

_CONTROL = {";", "&&", "||", "|", "&", "\n"}
_UNREADABLE = ("$(", "`", "<(", ">(")


class AgentConfig(NamedTuple):
    # NamedTuple, not a dataclass: dataclasses imports inspect (~10 ms), and
    # this module loads on every tool call.
    unmask_allow: tuple[str, ...] = DEFAULT_UNMASK_ALLOW
    prompt_mode: str = "warn"
    sources: tuple[str, ...] = ()


def _candidates(cwd: str | None) -> list[Path]:
    found = []
    if cwd:
        found.append(Path(cwd) / ".claude" / "maskflow-agent.json")
    found.append(paths.home() / "config.json")
    return found


def load(cwd: str | None = None) -> AgentConfig:
    for candidate in _candidates(cwd):
        if not candidate.is_file():
            continue
        try:
            raw = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(raw, dict):
            continue
        allow = raw.get("unmask_allow", DEFAULT_UNMASK_ALLOW)
        extra = raw.get("unmask_allow_extra", ())
        mode = raw.get("prompt_mode", "warn")
        allow_t = tuple(str(a) for a in allow if isinstance(a, str) and a.strip())
        extra_t = tuple(str(a) for a in extra if isinstance(a, str) and a.strip())
        return AgentConfig(
            unmask_allow=tuple(dict.fromkeys((*allow_t, *extra_t))),
            prompt_mode=mode if mode in PROMPT_MODES else "warn",
            sources=(str(candidate),),
        )
    return AgentConfig()


def _simple_commands(command: str) -> list[list[str]] | None:
    """Split a command line into simple commands (argv lists), or None when
    it can't be read with certainty."""
    if any(marker in command for marker in _UNREADABLE):
        return None
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return None
    commands: list[list[str]] = [[]]
    for token in tokens:
        if token in _CONTROL or set(token) <= set(";&|"):
            commands.append([])
        else:
            commands[-1].append(token)
    return [c for c in commands if c]


def _program(argv: list[str]) -> list[str]:
    """Drop leading VAR=value assignments and a leading `env`/`sudo`-free
    path prefix from argv[0]."""
    i = 0
    while i < len(argv) and "=" in argv[i] and not argv[i].startswith("="):
        name = argv[i].split("=", 1)[0]
        if not name.replace("_", "").isalnum():
            break
        i += 1
    rest = argv[i:]
    if rest:
        rest = [os.path.basename(rest[0]), *rest[1:]]
    return rest


def is_unmask_allowed(command: str, allow: tuple[str, ...]) -> bool:
    commands = _simple_commands(command)
    if not commands:
        return False
    rules = [rule.split() for rule in allow]
    for argv in commands:
        program = _program(argv)
        if not program:
            return False
        if not any(program[: len(rule)] == rule for rule in rules if rule):
            return False
    return True


# -- the user's own Bash permission rules ---------------------------------------
# Claude Code evaluates permission rules against the command a PreToolUse hook
# returns. Once a command is wrapped in `maskflow-agent exec`, a user rule such
# as `Bash(psql:*)` in "deny" would no longer match it -- so before wrapping,
# the hook checks the ORIGINAL command against the user's deny/ask rules
# itself and keeps their decision.
def _settings_files(cwd: str | None) -> list[Path]:
    files = [Path.home() / ".claude" / "settings.json"]
    if cwd:
        files += [
            Path(cwd) / ".claude" / "settings.json",
            Path(cwd) / ".claude" / "settings.local.json",
        ]
    return files


def _bash_rules(cwd: str | None, kind: str) -> list[str]:
    rules: list[str] = []
    for file in _settings_files(cwd):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        perms = data.get("permissions") if isinstance(data, dict) else None
        entries = perms.get(kind, []) if isinstance(perms, dict) else []
        rules += [e for e in entries if isinstance(e, str) and e.startswith("Bash")]
    return rules


def _rule_matches(rule: str, command_text: str) -> bool:
    if rule == "Bash" or rule == "Bash(*)":
        return True
    if not (rule.startswith("Bash(") and rule.endswith(")")):
        return False
    inner = rule[5:-1].strip()
    if inner.endswith(":*"):
        prefix = inner[:-2]
        return command_text == prefix or command_text.startswith(prefix + " ")
    if inner.endswith("*"):
        return command_text.startswith(inner[:-1])
    return command_text == inner


def user_bash_decision(command: str, cwd: str | None) -> str | None:
    """What the user's own rules say about the ORIGINAL command: "deny" or
    "ask" if any deny/ask rule matches any of its simple commands, "allow"
    only if allow rules cover EVERY simple command, else None (no rule --
    Claude Code's normal flow decides). Unreadable commands never get
    "allow"."""
    commands = _simple_commands(command)
    texts = [" ".join(_program(argv)) for argv in commands] if commands else None
    for kind in ("deny", "ask"):
        rules = _bash_rules(cwd, kind)
        if not rules:
            continue
        if texts is None:
            return kind
        if any(_rule_matches(rule, text) for rule in rules for text in texts):
            return kind
    allow = _bash_rules(cwd, "allow")
    if texts and allow and all(any(_rule_matches(r, t) for r in allow) for t in texts):
        return "allow"
    return None
