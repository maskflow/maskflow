"""derive.py must never read a detected value. Enforced by AST inspection
of the module source: no attribute access to ``.text`` (Span) or
``.original`` (MappingEntry) is allowed anywhere in it."""

from __future__ import annotations

import ast
import pathlib

import maskflow_evidence.derive as derive_mod

FORBIDDEN_ATTRS = {"text", "original"}


def test_derive_never_accesses_a_value_attribute() -> None:
    source = pathlib.Path(derive_mod.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    offenders = [
        node.attr
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTRS
    ]
    assert not offenders, f"derive.py reads a value attribute: {offenders}"
