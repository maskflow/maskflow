"""Best-effort dotted-path -> source line number, per format. Used by
errors.py to annotate a validation error with `file:line` instead of just a
field path. Not a guarantee: an unresolvable path falls back to its nearest
known ancestor, then to line 1 (see lookup_line()).
"""

from __future__ import annotations

import re

import yaml

from .formats import Format

_TOML_TABLE_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:#.*)?$")
_TOML_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_\-]*)\s*=")


def _linemap_toml(raw_text: str) -> dict[tuple[str, ...], int]:
    linemap: dict[tuple[str, ...], int] = {}
    current_table: tuple[str, ...] = ()
    for lineno, line in enumerate(raw_text.splitlines(), start=1):
        table_match = _TOML_TABLE_RE.match(line)
        if table_match:
            current_table = tuple(
                part.strip().strip("\"'") for part in table_match.group(1).split(".")
            )
            linemap[current_table] = lineno
            continue
        key_match = _TOML_KEY_RE.match(line)
        if key_match:
            linemap[current_table + (key_match.group(1),)] = lineno
    return linemap


def _linemap_yaml(raw_text: str) -> dict[tuple[str, ...], int]:
    linemap: dict[tuple[str, ...], int] = {}
    root = yaml.compose(raw_text)
    if root is None:
        return linemap

    def walk(node: yaml.Node, path: tuple[str, ...]) -> None:
        if isinstance(node, yaml.MappingNode):
            for key_node, value_node in node.value:
                key_path = path + (str(key_node.value),)
                linemap[key_path] = key_node.start_mark.line + 1
                walk(value_node, key_path)

    walk(root, ())
    return linemap


def _skip_json_string(text: str, start: int) -> tuple[str, int, int]:
    """Return (string value, index just past the closing quote, number of
    newlines crossed) for the JSON string starting at `start` (index of the
    opening quote)."""
    i = start + 1
    buf: list[str] = []
    newlines = 0
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\" and i + 1 < n:
            buf.append(c)
            buf.append(text[i + 1])
            i += 2
            continue
        if c == "\n":
            newlines += 1
        if c == '"':
            i += 1
            break
        buf.append(c)
        i += 1
    return "".join(buf), i, newlines


def _linemap_json(raw_text: str) -> dict[tuple[str, ...], int]:
    linemap: dict[tuple[str, ...], int] = {}
    path_stack: list[str] = []
    container_stack: list[str] = []  # "object" | "array"
    expect_key_stack: list[bool] = []  # per object container
    pending_key: str | None = None
    pending_key_line = 1
    line = 1
    i = 0
    n = len(raw_text)

    while i < n:
        c = raw_text[i]
        if c == "\n":
            line += 1
            i += 1
            continue
        if c in " \t\r":
            i += 1
            continue
        if c == '"':
            str_line = line
            value, i, newlines = _skip_json_string(raw_text, i)
            line += newlines
            if container_stack and container_stack[-1] == "object" and expect_key_stack[-1]:
                pending_key = value
                pending_key_line = str_line
                expect_key_stack[-1] = False
            continue
        if c == ":":
            i += 1
            continue
        if c == ",":
            if container_stack and container_stack[-1] == "object":
                expect_key_stack[-1] = True
            i += 1
            continue
        if c == "{":
            if pending_key is not None:
                path_stack.append(pending_key)
                linemap[tuple(path_stack)] = pending_key_line
                pending_key = None
            container_stack.append("object")
            expect_key_stack.append(True)
            i += 1
            continue
        if c == "}":
            if container_stack and container_stack[-1] == "object":
                container_stack.pop()
                expect_key_stack.pop()
                if path_stack:
                    path_stack.pop()
            i += 1
            continue
        if c == "[":
            if pending_key is not None:
                path_stack.append(pending_key)
                linemap[tuple(path_stack)] = pending_key_line
                pending_key = None
            container_stack.append("array")
            i += 1
            continue
        if c == "]":
            if container_stack and container_stack[-1] == "array":
                container_stack.pop()
                if path_stack:
                    path_stack.pop()
            i += 1
            continue
        if pending_key is not None:
            path_stack.append(pending_key)
            linemap[tuple(path_stack)] = pending_key_line
            path_stack.pop()
            pending_key = None
            while i < n and raw_text[i] not in ",}]\n":
                i += 1
            continue
        i += 1

    return linemap


def build_linemap(raw_text: str, fmt: Format) -> dict[tuple[str, ...], int]:
    if fmt == "toml":
        return _linemap_toml(raw_text)
    if fmt == "yaml":
        return _linemap_yaml(raw_text)
    return _linemap_json(raw_text)


def lookup_line(linemap: dict[tuple[str, ...], int], path: tuple[str, ...]) -> int | None:
    """Exact path if known, else the longest known ancestor prefix, else
    None (caller falls back to line 1)."""
    for end in range(len(path), 0, -1):
        prefix = path[:end]
        if prefix in linemap:
            return linemap[prefix]
    return None
