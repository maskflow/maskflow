"""Where did this payload come from? -- intra-procedural, best effort.

The report's value depends on naming the *source* of the text, not just the
call that sent it: "the `aadhaar` column of `tickets` reaches
api.openai.com" is actionable in a way that "line 42 is unmasked" is not.

This pass is deliberately modest. It walks backwards from the payload
argument through assignments inside the same function, and classifies what
it lands on by the shape of the expression and the name of the callee. It
does not follow calls into other functions, does not know the DB schema,
and does not infer types. When it cannot tell, it says
`unknown` -- which `flows.CONFIDENCE_UNKNOWN` then carries into the report
rather than dressing a guess up as a finding.

Identifiers only: a column name, a field name, a callee name. The content
of a string literal is never recorded -- a literal is reported as kind
`literal` with an empty detail, so a hard-coded value in the audited
codebase cannot ride into the report (rule 1).
"""

from __future__ import annotations

import ast

from ..discovery.flows import (
    SOURCE_DB_COLUMN,
    SOURCE_FILE_READ,
    SOURCE_LITERAL,
    SOURCE_PARAMETER,
    SOURCE_REQUEST_FIELD,
    SOURCE_TOOL_RESULT,
    SOURCE_UNKNOWN,
    Source,
)

#: Callee names that mean "this came out of a database". Matched on the
#: final attribute of the call target, so it covers psycopg cursors,
#: SQLAlchemy Session/Query, and the Django ORM without naming any of them.
_DB_CALLS: frozenset[str] = frozenset(
    {
        "execute",
        "executemany",
        "fetchone",
        "fetchall",
        "fetchmany",
        "scalar",
        "scalars",
        "scalar_one",
        "query",
        "select",
        "filter",
        "filter_by",
        "all",
        "first",
        "one",
        "one_or_none",
        "get_or_create",
        "raw",
        "values",
        "values_list",
        "annotate",
        "aggregate",
    }
)

#: Callee names that mean "this came off an inbound HTTP request".
_REQUEST_CALLS: frozenset[str] = frozenset(
    {"get_json", "model_dump", "model_dump_json", "dict", "form", "parse_obj", "parse_raw"}
)

#: Attribute names on a request object, for the `request.json` /
#: `request.form` / `await request.body()` shapes.
_REQUEST_ATTRS: frozenset[str] = frozenset(
    {"json", "form", "body", "data", "args", "query_params", "files", "payload"}
)

#: Callee names that mean "this was read off disk".
_FILE_CALLS: frozenset[str] = frozenset(
    {
        "open",
        "read",
        "readlines",
        "read_text",
        "read_bytes",
        "read_csv",
        "read_json",
        "read_excel",
        "load",
        "loads",
        "extract_text",
        "get_text",
        "load_data",
        "DictReader",
        "reader",
    }
)

#: Callee names that mean "this is an MCP / agent tool result".
_TOOL_CALLS: frozenset[str] = frozenset({"call_tool", "run_tool", "invoke_tool", "tool_result"})

#: Calls that pass provenance through unchanged, so the trace follows into
#: their arguments rather than stopping at the callee's name. mask() and
#: unmask() belong here: they transform the value, not its origin.
_TRANSPARENT_CALLS: frozenset[str] = frozenset(
    {
        "str",
        "format",
        "join",
        "strip",
        "lstrip",
        "rstrip",
        "lower",
        "upper",
        "replace",
        "mask",
        "unmask",
        "mask_with_policy",
        "mask_and_call",
    }
)

#: How far back through assignments to follow before giving up. This is an
#: effort bound, not a correctness one -- mutually recursive assignments
#: (`a = b` / `b = a`) are stopped by the `visiting` set in trace_payload,
#: not by this. It is generous because realistic chains are deeper than
#: they look: a payload that goes list -> dict -> name -> mask() -> name ->
#: f-string -> subscript -> name -> fetchone() has already spent eight
#: levels, and a limit that cuts it short silently downgrades a perfectly
#: traceable column to `unknown` (which is how fixture 04 caught a limit
#: of 6 reporting less than fixture 01 for the same query).
_MAX_DEPTH = 24


def _callee_name(node: ast.Call) -> str:
    """The final attribute (or name) of a call target: `s.execute` -> execute."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _kind_for_call(name: str) -> str | None:
    if name in _DB_CALLS:
        return SOURCE_DB_COLUMN
    if name in _REQUEST_CALLS:
        return SOURCE_REQUEST_FIELD
    if name in _FILE_CALLS:
        return SOURCE_FILE_READ
    if name in _TOOL_CALLS:
        return SOURCE_TOOL_RESULT
    return None


class _Assignments(ast.NodeVisitor):
    """name -> the expressions assigned to it, within one function body.

    Nested function definitions are not descended into: their locals are a
    different scope, and treating them as the same one is how a tracer
    starts reporting sources that do not exist.
    """

    def __init__(self) -> None:
        self.table: dict[str, list[ast.expr]] = {}
        self._depth = 0

    def _add(self, target: ast.expr, value: ast.expr) -> None:
        if isinstance(target, ast.Name):
            self.table.setdefault(target.id, []).append(value)
        elif isinstance(target, (ast.Tuple, ast.List)):
            for element in target.elts:
                self._add(element, value)

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            self._add(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._add(node.target, node.value)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        # `for row in cursor.fetchall():` -- the loop variable carries the
        # iterable's provenance, which is usually the whole point.
        self._add(node.target, node.iter)
        self.generic_visit(node)

    def visit_AsyncFor(self, node: ast.AsyncFor) -> None:
        self._add(node.target, node.iter)
        self.generic_visit(node)

    def visit_withitem(self, node: ast.withitem) -> None:
        if node.optional_vars is not None:
            self._add(node.optional_vars, node.context_expr)
        self.generic_visit(node)

    def _skip_nested(self, node: ast.AST) -> None:
        if self._depth == 0:
            self._depth += 1
            self.generic_visit(node)
            self._depth -= 1

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._skip_nested(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._skip_nested(node)

    def visit_Lambda(self, node: ast.Lambda) -> None:
        return


def _parameters(func: ast.AST) -> frozenset[str]:
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return frozenset()
    args = func.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return frozenset(n for n in names if n not in {"self", "cls"})


def _subscript_key(node: ast.Subscript) -> str:
    """`row["aadhaar"]` -> "aadhaar"; a dynamic index -> ""."""
    slice_node = node.slice
    if isinstance(slice_node, ast.Constant) and isinstance(slice_node.value, str):
        return slice_node.value
    return ""


def build_assignments(func: ast.AST) -> dict[str, list[ast.expr]]:
    """The assignment table for one function body."""
    visitor = _Assignments()
    for child in ast.iter_child_nodes(func):
        visitor.visit(child)
    return visitor.table


def trace_payload(
    node: ast.expr,
    *,
    assignments: dict[str, list[ast.expr]],
    parameters: frozenset[str],
) -> tuple[Source, ...]:
    """Every source the payload expression can be traced back to.

    Returns a de-duplicated tuple, ordered so the report is deterministic.
    An empty tuple means "traced nothing", which the caller turns into
    confidence `unknown`.
    """
    found: list[Source] = []
    seen: set[tuple[str, str]] = set()
    #: Names currently being expanded. This, not the depth bound, is what
    #: makes a cyclic assignment terminate.
    visiting: set[str] = set()

    def record(kind: str, detail: str = "") -> None:
        key = (kind, detail)
        if key in seen:
            return
        seen.add(key)
        found.append(Source(kind=kind, detail=detail))

    def walk(expr: ast.expr, depth: int, hint: str) -> None:
        if depth > _MAX_DEPTH:
            return

        if isinstance(expr, ast.Constant):
            if isinstance(expr.value, str):
                record(SOURCE_LITERAL)
            return

        if isinstance(expr, ast.Name):
            if expr.id in assignments:
                if expr.id in visiting:
                    # A cycle: `a = b` and `b = a`. Record what we know --
                    # the name -- rather than recursing forever.
                    record(SOURCE_UNKNOWN, expr.id)
                    return
                visiting.add(expr.id)
                for value in assignments[expr.id]:
                    walk(value, depth + 1, hint)
                visiting.discard(expr.id)
                return
            if expr.id in parameters:
                record(SOURCE_PARAMETER, expr.id)
            else:
                record(SOURCE_UNKNOWN, expr.id)
            return

        if isinstance(expr, ast.Subscript):
            key = _subscript_key(expr)
            # Classify by what is being indexed, label by the key: the
            # kind comes from the container's provenance, so
            # `row["aadhaar"]` where row came from fetchall() is a db
            # column, while `body["aadhaar"]` off request.json() is a
            # request field.
            kinds_before = len(found)
            walk(expr.value, depth + 1, key or hint)
            if key:
                # Re-label whatever the container resolved to with the key.
                relabelled = [
                    Source(kind=s.kind, detail=key)
                    for s in found[kinds_before:]
                    if s.kind in {SOURCE_DB_COLUMN, SOURCE_REQUEST_FIELD, SOURCE_FILE_READ}
                ]
                for source in relabelled:
                    record(source.kind, source.detail)
                if not relabelled and len(found) == kinds_before:
                    record(SOURCE_UNKNOWN, key)
            return

        if isinstance(expr, ast.Attribute):
            if expr.attr in _REQUEST_ATTRS and isinstance(expr.value, ast.Name):
                record(SOURCE_REQUEST_FIELD, expr.attr)
                return
            kinds_before = len(found)
            walk(expr.value, depth + 1, expr.attr)
            if len(found) == kinds_before:
                record(SOURCE_UNKNOWN, expr.attr)
            return

        if isinstance(expr, ast.Call):
            name = _callee_name(expr)
            kind = _kind_for_call(name)
            if kind is not None:
                record(kind, hint or name)
                return
            if name in _TRANSPARENT_CALLS:
                # Transparent to provenance: trace through it. mask() is in
                # this set deliberately -- masking changes the value but not
                # where it came from, and "the aadhaar column is masked
                # before it is sent" is a far more useful report line than
                # "something called mask()".
                for arg in (*expr.args, *(k.value for k in expr.keywords)):
                    walk(arg, depth + 1, hint)
                if isinstance(expr.func, ast.Attribute):
                    walk(expr.func.value, depth + 1, hint)
                return
            record(SOURCE_UNKNOWN, name)
            return

        if isinstance(expr, (ast.List, ast.Tuple, ast.Set)):
            for element in expr.elts:
                walk(element, depth + 1, hint)
            return

        if isinstance(expr, ast.Dict):
            for key_node, value in zip(expr.keys, expr.values, strict=False):
                label = hint
                if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                    label = key_node.value if key_node.value not in {"role", "type"} else hint
                if value is not None:
                    walk(value, depth + 1, label)
            return

        if isinstance(expr, ast.JoinedStr):
            for value in expr.values:
                if isinstance(value, ast.FormattedValue):
                    walk(value.value, depth + 1, hint)
                elif isinstance(value, ast.Constant):
                    record(SOURCE_LITERAL)
            return

        if isinstance(expr, ast.BinOp):
            walk(expr.left, depth + 1, hint)
            walk(expr.right, depth + 1, hint)
            return

        if isinstance(expr, ast.Await):
            walk(expr.value, depth + 1, hint)
            return

        if isinstance(expr, (ast.ListComp, ast.GeneratorExp, ast.SetComp)):
            walk(expr.elt, depth + 1, hint)
            for comp in expr.generators:
                walk(comp.iter, depth + 1, hint)
            return

    walk(node, 0, "")
    return tuple(sorted(found, key=lambda s: (s.kind, s.detail)))
