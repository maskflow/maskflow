"""Is this egress path guarded?

Four of the five answers are evidence-backed; the fifth, `unknown`, is the
one this module reaches for whenever the evidence runs out. That matters
more here than anywhere else in the package, because the two ways to be
wrong are not symmetric: calling a guarded path unmasked wastes an
afternoon, while calling an unguarded path masked is the failure the whole
tool exists to prevent. So every rule below either proves a guard or
declines to.

The honest difficulty is the gateway. MaskFlow's gateway is deliberately
OpenAI/Anthropic *path*-compatible and has no reserved hostname, so
`base_url="http://localhost:8000/v1"` is indistinguishable from any other
local proxy by reading source alone. We therefore do not treat a custom
base_url as proof of anything. It is proof of a guard only alongside a
MaskFlow marker in the same file (a `maskflow` host, a
`X-Maskflow-Session` header, a `MASKFLOW_GATEWAY_*` variable); otherwise
the flow is `unknown` and the report says the destination could not be
identified and should be confirmed by probing it. A client with no
base_url at all is unambiguous: that is direct egress to the provider.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

from ..sinks.loader import SinkDef
from .flows import (
    MASKED_VIA_GATEWAY,
    MASKED_VIA_INTEGRATION,
    MASKED_VIA_MASK_CALL,
    UNKNOWN,
    UNMASKED,
)
from .symbols import SymbolTable, dotted

#: Importing any of these is evidence that this module routes through a
#: MaskFlow integration rather than calling the framework raw.
INTEGRATION_MODULES: tuple[str, ...] = (
    "maskflow_litellm",
    "maskflow_langchain",
    "maskflow_llamaindex",
    "maskflow_mcp",
)

#: Which sink category each integration guards. An integration import only
#: counts for the framework it actually wraps -- importing
#: maskflow_langchain does not guard a bare `openai` call in the same file.
_INTEGRATION_COVERS: dict[str, frozenset[str]] = {
    "maskflow_litellm": frozenset({"litellm"}),
    "maskflow_langchain": frozenset({"langchain"}),
    "maskflow_llamaindex": frozenset({"llamaindex"}),
    "maskflow_mcp": frozenset({"mcp"}),
}

#: Substring that makes a host recognisably MaskFlow's own gateway. This is
#: a convention (the Compose/Helm service name, the Docker image), not a
#: contract -- hence the corroboration requirement described above.
_GATEWAY_HOST_MARKER = "maskflow"

#: File-level strings that corroborate "the proxy in this file is ours".
_GATEWAY_MARKERS: tuple[str, ...] = (
    "X-Maskflow-Session",
    "x-maskflow-session",
    "MASKFLOW_GATEWAY_",
)

#: The SDK entry points that mask at the call site.
_MASK_FUNCS = frozenset({"mask", "mask_with_policy", "mask_and_call"})
_MASK_ROOTS = frozenset({"maskflow", "maskflow_core"})


@dataclass(frozen=True)
class ModuleFacts:
    """Evidence gathered once per file, used by every flow in it."""

    integrations: frozenset[str] = frozenset()
    has_gateway_marker: bool = False
    #: Dotted import roots present in the file, for the integration check.
    import_roots: frozenset[str] = frozenset()
    explanation: tuple[str, ...] = field(default_factory=tuple)


def collect_module_facts(tree: ast.Module, table: SymbolTable) -> ModuleFacts:
    """Scan a parsed module once for file-level masking evidence."""
    integrations = {
        module
        for path in table.imports.values()
        for module in INTEGRATION_MODULES
        if path == module or path.startswith(f"{module}.")
    }
    roots = {path.split(".")[0] for path in table.imports.values()}

    marker = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if any(m in node.value for m in _GATEWAY_MARKERS):
                marker = True
                break

    notes: list[str] = []
    if integrations:
        notes.append(f"module imports MaskFlow integration(s): {sorted(integrations)}")
    if marker:
        notes.append("module contains a MaskFlow gateway marker (session header or env var)")

    return ModuleFacts(
        integrations=frozenset(integrations),
        has_gateway_marker=marker,
        import_roots=frozenset(roots),
        explanation=tuple(notes),
    )


def _is_mask_call(node: ast.expr, table: SymbolTable, scope: str) -> bool:
    """Is this expression a `mask(...)` / `mask_with_policy(...)` call?"""
    if not isinstance(node, ast.Call):
        return False
    literal = dotted(node.func)
    if literal is None:
        return False
    resolved = table.resolve(node.func, scope) or literal
    tail = resolved.rsplit(".", 1)[-1]
    root = resolved.split(".")[0]
    return tail in _MASK_FUNCS and root in _MASK_ROOTS


def _payload_nodes(call: ast.Call, sink: SinkDef) -> list[tuple[str, ast.expr]]:
    """The (argument name, node) pairs the registry says carry the payload."""
    out: list[tuple[str, ast.expr]] = []
    for keyword in call.keywords:
        if keyword.arg is not None and keyword.arg in sink.text_args.keywords:
            out.append((keyword.arg, keyword.value))
    for index in sink.text_args.positional:
        if index < len(call.args):
            out.append((f"arg{index}", call.args[index]))
    return out


def _argument_is_masked(node: ast.expr, table: SymbolTable, scope: str) -> bool:
    """True when this argument's value demonstrably came from mask().

    Walks the shapes a masked payload actually takes in real code: the name
    `mask()` was assigned to, a direct `mask(text)` call, `result.masked_text`,
    and a list/dict built out of those (the `messages=[{"content": masked}]`
    shape, which is the common one and would otherwise read as unmasked).
    """
    if table.is_masked_name(node, scope):
        return True
    if _is_mask_call(node, table, scope):
        return True
    if isinstance(node, ast.Attribute) and node.attr == "masked_text":
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_argument_is_masked(el, table, scope) for el in node.elts)
    if isinstance(node, ast.Dict):
        return any(v is not None and _argument_is_masked(v, table, scope) for v in node.values)
    if isinstance(node, ast.JoinedStr):  # an f-string containing a masked name
        return any(
            isinstance(v, ast.FormattedValue) and _argument_is_masked(v.value, table, scope)
            for v in node.values
        )
    if isinstance(node, ast.BinOp):  # "prefix " + masked
        return _argument_is_masked(node.left, table, scope) or _argument_is_masked(
            node.right, table, scope
        )
    return False


def _gateway_verdict(base_url: str, facts: ModuleFacts) -> tuple[bool, str]:
    """(is_maskflow_gateway, reason) for a literal base_url."""
    lowered = base_url.lower()
    if _GATEWAY_HOST_MARKER in lowered:
        return True, f"client base_url names a MaskFlow gateway host ({base_url!r})"
    if facts.has_gateway_marker:
        return True, (
            f"client has a custom base_url ({base_url!r}) and the module carries a "
            "MaskFlow gateway marker"
        )
    return False, (
        f"client has a custom base_url ({base_url!r}) that could not be identified as a "
        "MaskFlow gateway -- it may be a guard or an unknown third party; probe "
        "GET /v1/entities on it to confirm"
    )


def classify(
    call: ast.Call,
    call_path: str,
    sink: SinkDef,
    table: SymbolTable,
    scope: str,
    facts: ModuleFacts,
) -> tuple[str, str, tuple[str, ...], tuple[str, ...]]:
    """Decide a flow's masking status.

    Returns (status, reason, payload argument names, explanation steps).
    Precedence is mask() at the call site, then a recognised gateway, then
    a framework integration, then unmasked -- a call-site mask() is the
    strongest evidence available statically, because it is visible right
    there rather than inferred from configuration.
    """
    steps: list[str] = list(facts.explanation)
    payloads = _payload_nodes(call, sink)
    payload_names = tuple(name for name, _ in payloads)

    # 1. mask() at the call site.
    masked = [name for name, node in payloads if _argument_is_masked(node, table, scope)]
    if masked:
        steps.append(f"payload argument(s) {masked} came from mask()")
        return (
            MASKED_VIA_MASK_CALL,
            f"payload argument(s) {', '.join(masked)} are mask() output",
            payload_names,
            tuple(steps),
        )

    # The whole call wrapped in mask_and_call() is the SDK's one-liner.
    # Detected here rather than above because the payload is the inner
    # prompt, not an argument of this call.
    # (walk.py marks it on the hit; see `wrapped_in_mask_and_call`.)

    # 2. A recognised MaskFlow gateway.
    kwargs = table.kwargs_for(call.func, scope)
    base_url = kwargs.get("base_url") or kwargs.get("baseURL") or kwargs.get("api_base")
    if base_url:
        is_gateway, reason = _gateway_verdict(base_url, facts)
        steps.append(reason)
        if is_gateway:
            return MASKED_VIA_GATEWAY, reason, payload_names, tuple(steps)
        return UNKNOWN, reason, payload_names, tuple(steps)

    # 3. A MaskFlow framework integration covering this sink's provider.
    for integration in sorted(facts.integrations):
        if sink.provider in _INTEGRATION_COVERS.get(integration, frozenset()):
            reason = f"{integration} wraps this {sink.provider} path"
            steps.append(reason)
            return MASKED_VIA_INTEGRATION, reason, payload_names, tuple(steps)

    # 4. Nothing guards it. If the registry told us where the payload sits
    # and we found it, this is a confident `unmasked`; if the registry
    # declares no payload argument (a decorator, an MCP tool), we can see
    # the sink but not the text, so the honest answer is `unknown`.
    if not sink.text_args.is_empty and not payloads:
        reason = (
            f"no {sink.id} payload argument found at this call site "
            f"(expected one of {list(sink.text_args.keywords)})"
        )
        steps.append(reason)
        return UNKNOWN, reason, payload_names, tuple(steps)

    if sink.text_args.is_empty:
        reason = (
            f"{sink.id} egresses whatever it is given and the registry declares no single "
            "payload argument, so masking cannot be judged from the call site alone"
        )
        steps.append(reason)
        return UNKNOWN, reason, payload_names, tuple(steps)

    reason = f"payload argument(s) {', '.join(payload_names)} reach {sink.provider} unmasked"
    steps.append(reason)
    return UNMASKED, reason, payload_names, tuple(steps)
