"""The ast pass: a source tree -> Flow objects.

Two indexes are built from the registry once per run -- one for
module-level callables, one for client-plus-method pairs -- so matching a
call is a dict lookup on its resolved dotted path rather than a scan over
26 sinks per call.

This module parses source with `ast` and never executes it. A file that
does not parse is skipped and recorded as a skipped file, not a fatal
error: an audit of somebody else's repository will meet Python 2 leftovers,
templates, and generated code, and refusing to report anything because of
one of them would be useless.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from ..sinks.loader import SinkDef, factory_map
from ..trace.backward import build_assignments, trace_payload
from .flows import (
    CONFIDENCE_HIGH,
    CONFIDENCE_LOW,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_UNKNOWN,
    SOURCE_DB_COLUMN,
    SOURCE_FILE_READ,
    SOURCE_PARAMETER,
    SOURCE_REQUEST_FIELD,
    SOURCE_TOOL_RESULT,
    SOURCE_UNKNOWN,
    Flow,
    Source,
    flow_id,
)
from .masking import ModuleFacts, classify, collect_module_facts
from .symbols import SymbolTable, build_symbol_table, dotted

#: Directories never worth auditing. A vendored dependency's own LLM calls
#: are not the user's egress paths, and walking .venv would dwarf the real
#: result. Kept as a default rather than gitignore parsing, which would be
#: a dependency and a surprise; `exclude=` overrides it.
DEFAULT_EXCLUDES: frozenset[str] = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        ".env",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".nox",
        "build",
        "dist",
        "site-packages",
        ".eggs",
        ".idea",
        ".claude",
    }
)

_MASK_AND_CALL = "mask_and_call"


@dataclass(frozen=True)
class SinkIndex:
    """Registry lookups, prepared once."""

    functions: dict[str, SinkDef]
    client_methods: dict[str, SinkDef]
    by_id: dict[str, SinkDef]
    #: Passed to the symbol table so factory chains resolve; see
    #: SymbolTable.factories.
    factories: dict[str, str]

    @classmethod
    def build(cls, sinks: tuple[SinkDef, ...]) -> SinkIndex:
        functions: dict[str, SinkDef] = {}
        client_methods: dict[str, SinkDef] = {}
        for sink in sinks:
            for fn in sink.functions:
                functions[fn] = sink
            for client in sink.clients:
                for method in sink.methods:
                    client_methods[f"{client}.{method}"] = sink
        return cls(
            functions=functions,
            client_methods=client_methods,
            by_id={s.id: s for s in sinks},
            factories=factory_map(sinks),
        )

    def match(self, call_path: str) -> SinkDef | None:
        return self.functions.get(call_path) or self.client_methods.get(call_path)


@dataclass(frozen=True)
class SkippedFile:
    """A file the walk could not read. Carries no file content."""

    file: str
    reason: str


def iter_python_files(root: Path, *, exclude: frozenset[str] = DEFAULT_EXCLUDES) -> Iterator[Path]:
    """Every .py file under root, in sorted order so a run is reproducible."""
    if root.is_file():
        if root.suffix == ".py":
            yield root
        return
    for path in sorted(root.rglob("*.py"), key=lambda p: p.as_posix()):
        if any(part in exclude for part in path.relative_to(root).parts[:-1]):
            continue
        yield path


def _literal_strings(node: ast.expr) -> list[str]:
    """Every plain string literal reachable in this expression.

    Used only to match a URL against a known host list. An f-string's
    literal fragments count -- `f"{base}/v1/chat"` still tells us the path
    even when the host is dynamic -- which is why this returns a list
    rather than a single value.
    """
    out: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Constant) and isinstance(child.value, str):
            out.append(child.value)
    return out


def _payload_arg_nodes(call: ast.Call, sink: SinkDef) -> list[tuple[str, ast.expr]]:
    """The (name, node) pairs the registry says carry this sink's payload.

    Same selection masking.classify() uses -- kept here rather than
    imported from it so the trace does not depend on the classifier.
    """
    out: list[tuple[str, ast.expr]] = []
    for keyword in call.keywords:
        if keyword.arg is not None and keyword.arg in sink.text_args.keywords:
            out.append((keyword.arg, keyword.value))
    for index in sink.text_args.positional:
        if index < len(call.args):
            out.append((f"arg{index}", call.args[index]))
    return out


def _parameters_of(func: ast.AST) -> frozenset[str]:
    """Parameter names of a function, minus self/cls."""
    if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return frozenset()
    args = func.args
    names = [a.arg for a in (*args.posonlyargs, *args.args, *args.kwonlyargs)]
    if args.vararg is not None:
        names.append(args.vararg.arg)
    if args.kwarg is not None:
        names.append(args.kwarg.arg)
    return frozenset(n for n in names if n not in {"self", "cls"})


def _resolve_host(call: ast.Call, sink: SinkDef, table: SymbolTable, scope: str) -> str | None:
    """The destination host for a sink that requires one.

    Returns the matched host, or None when the URL could not be resolved to
    one of the sink's hosts -- in which case the call is not reported as
    this sink at all. A dynamically built URL is exactly the case where
    guessing would manufacture a false finding.
    """
    if sink.url_args is None:
        return sink.hosts[0] if len(sink.hosts) == 1 else ""

    candidates: list[str] = []
    for keyword in call.keywords:
        if keyword.arg is not None and keyword.arg in sink.url_args.keywords:
            candidates.extend(_literal_strings(keyword.value))
    for index in sink.url_args.positional:
        if index < len(call.args):
            candidates.extend(_literal_strings(call.args[index]))
    # A base_url on the client plus a relative path on the call is the
    # other common shape.
    kwargs = table.kwargs_for(call.func, scope)
    candidates.extend(v for k, v in kwargs.items() if k in {"base_url", "baseURL", "api_base"})

    for value in candidates:
        lowered = value.lower()
        for host in sink.hosts:
            if host.lower() in lowered:
                return host
    return None


#: Source kinds that name a concrete origin, so a flow traced to one of
#: them is worth asserting in the report.
_NAMED_SOURCES = frozenset(
    {SOURCE_DB_COLUMN, SOURCE_REQUEST_FIELD, SOURCE_FILE_READ, SOURCE_TOOL_RESULT}
)


def confidence_for(sources: tuple[Source, ...]) -> str:
    """How much the report may claim about where a payload came from.

    `high` only when a source is both a named origin and actually carries
    that name -- a `db_column` with no column name is an origin we cannot
    put in front of a reviewer, so it stays `medium`.
    """
    if not sources:
        return CONFIDENCE_UNKNOWN
    if any(s.kind in _NAMED_SOURCES and s.detail for s in sources):
        return CONFIDENCE_HIGH
    if any(s.kind in _NAMED_SOURCES for s in sources):
        return CONFIDENCE_MEDIUM
    if any(s.kind == SOURCE_PARAMETER for s in sources):
        return CONFIDENCE_MEDIUM
    if all(s.kind == SOURCE_UNKNOWN for s in sources):
        return CONFIDENCE_LOW
    return CONFIDENCE_LOW


class _Walker(ast.NodeVisitor):
    """Collects flows from one parsed module."""

    def __init__(
        self,
        *,
        relative_path: str,
        index: SinkIndex,
        table: SymbolTable,
        facts: ModuleFacts,
    ) -> None:
        self.relative_path = relative_path
        self.index = index
        self.table = table
        self.facts = facts
        self.flows: list[Flow] = []
        self._scope: list[str] = []
        self._occurrences: dict[tuple[str, str], int] = {}
        #: The enclosing function node, and its assignment table built once
        #: on first use -- a function with ten sinks parses its body once.
        self._func_stack: list[ast.AST] = []
        self._assign_cache: dict[int, tuple[dict[str, list[ast.expr]], frozenset[str]]] = {}
        #: Depth of enclosing mask_and_call() arguments -- a sink inside one
        #: is masked by construction.
        self._in_mask_and_call = 0

    @property
    def scope(self) -> str:
        return ".".join(self._scope)

    def _enter(self, name: str) -> None:
        self._scope.append(name)

    def _leave(self) -> None:
        self._scope.pop()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._enter(node.name)
        self.generic_visit(node)
        self._leave()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._enter(node.name)
        self._func_stack.append(node)
        self.generic_visit(node)
        self._func_stack.pop()
        self._leave()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._enter(node.name)
        self._func_stack.append(node)
        self.generic_visit(node)
        self._func_stack.pop()
        self._leave()

    def _context(self) -> tuple[dict[str, list[ast.expr]], frozenset[str]]:
        """The assignment table and parameter names of the enclosing function."""
        if not self._func_stack:
            return {}, frozenset()
        func = self._func_stack[-1]
        key = id(func)
        cached = self._assign_cache.get(key)
        if cached is None:
            cached = (build_assignments(func), _parameters_of(func))
            self._assign_cache[key] = cached
        return cached

    def _trace(self, node: ast.Call, sink: SinkDef) -> tuple[Source, ...]:
        assignments, parameters = self._context()
        sources: list[Source] = []
        seen: set[tuple[str, str]] = set()
        for _name, payload in _payload_arg_nodes(node, sink):
            for source in trace_payload(payload, assignments=assignments, parameters=parameters):
                key = (source.kind, source.detail)
                if key in seen:
                    continue
                seen.add(key)
                sources.append(source)
        return tuple(sources)

    def visit_Call(self, node: ast.Call) -> None:
        literal = dotted(node.func)
        resolved = self.table.resolve(node.func, self.scope)
        call_path = resolved or literal

        is_mask_and_call = call_path is not None and call_path.rsplit(".", 1)[-1] == _MASK_AND_CALL
        if is_mask_and_call:
            self._in_mask_and_call += 1

        if call_path is not None:
            sink = self.index.match(call_path)
            if sink is not None:
                flow = self._flow(node, call_path, sink)
                if flow is not None:
                    self.flows.append(flow)

        self.generic_visit(node)
        if is_mask_and_call:
            self._in_mask_and_call -= 1

    def _flow(self, node: ast.Call, call_path: str, sink: SinkDef) -> Flow | None:
        host = _resolve_host(node, sink, self.table, self.scope)
        if host is None:
            # A raw-HTTP call whose URL we could not tie to a provider host
            # is not evidence of egress. Dropping it is the point: the
            # alternative is a report full of every requests.post in the repo.
            return None

        status, reason, payload_names, steps = classify(
            node, call_path, sink, self.table, self.scope, self.facts
        )

        if self._in_mask_and_call:
            from .flows import MASKED_VIA_MASK_CALL

            status = MASKED_VIA_MASK_CALL
            reason = "call site is inside a mask_and_call() wrapper"
            steps = (*steps, reason)

        sources = self._trace(node, sink)

        key = (self.scope, call_path)
        occurrence = self._occurrences.get(key, 0)
        self._occurrences[key] = occurrence + 1

        return Flow(
            flow_id=flow_id(self.relative_path, self.scope, call_path, occurrence),
            file=self.relative_path,
            line=node.lineno,
            function=self.scope,
            sink_id=sink.id,
            category=sink.category,
            provider=sink.provider,
            call_path=call_path,
            host=host,
            masking_status=status,
            masking_reason=reason,
            payload_args=payload_names,
            sources=sources,
            confidence=confidence_for(sources),
            explanation=steps,
        )


def discover_file(
    path: Path, root: Path, index: SinkIndex
) -> tuple[tuple[Flow, ...], SkippedFile | None]:
    """Flows in one file. A file that cannot be parsed is skipped, not fatal."""
    relative = path.relative_to(root).as_posix() if path != root else path.name
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return (), SkippedFile(relative, f"could not read ({exc.__class__.__name__})")
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        # Only the class name and line -- a SyntaxError's str() quotes the
        # offending source line, which could be the very data we must not
        # print (rule 1).
        return (), SkippedFile(relative, f"could not parse (SyntaxError at line {exc.lineno})")

    table = build_symbol_table(tree, factories=index.factories)
    facts = collect_module_facts(tree, table)
    walker = _Walker(relative_path=relative, index=index, table=table, facts=facts)
    walker.visit(tree)
    return tuple(walker.flows), None


def discover(
    root: Path, sinks: tuple[SinkDef, ...], *, exclude: frozenset[str] = DEFAULT_EXCLUDES
) -> tuple[tuple[Flow, ...], tuple[SkippedFile, ...], int]:
    """Walk a tree. Returns (flows, skipped files, files examined)."""
    index = SinkIndex.build(sinks)
    flows: list[Flow] = []
    skipped: list[SkippedFile] = []
    examined = 0
    for path in iter_python_files(root, exclude=exclude):
        examined += 1
        found, skip = discover_file(path, root, index)
        flows.extend(found)
        if skip is not None:
            skipped.append(skip)
    # Sorted so the report and its baseline diff are order-independent.
    flows.sort(key=lambda f: (f.file, f.line, f.flow_id))
    return tuple(flows), tuple(skipped), examined
