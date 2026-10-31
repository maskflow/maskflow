"""Per-module symbol table: a call target -> the dotted path it came from.

Sink matching is on dotted paths (`openai.OpenAI` + `chat.completions.create`),
but source code almost never spells one out. It writes:

    from openai import OpenAI as Client
    client = Client(api_key=...)
    client.chat.completions.create(...)

so recognising that call means tracking two things: what each imported name
really refers to, and which local names hold a constructed client. This
module does exactly that and nothing else -- no type inference, no call
graph. When it cannot resolve a name it returns None, and the caller reports
`unknown` rather than guessing; over-claiming a leak is worse than admitting
we could not trace one.

Scoping is deliberately shallow: a module scope plus one scope per function,
with the function's bindings shadowing the module's. Python's real scoping
rules are richer, but a client rebound in a nested comprehension is not a
pattern worth the complexity, and getting it wrong would only ever downgrade
a flow to `unknown`.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field

#: Scope key for module level.
MODULE_SCOPE = ""


def scope_chain(scope: str) -> tuple[str, ...]:
    """A scope and every scope enclosing it, innermost first.

    "Svc.go" -> ("Svc.go", "Svc", ""). This is what lets a method see a
    `self.client` that a sibling method assigned: the binding is mirrored
    at class scope, and the method's lookup walks out to it.
    """
    parts = scope.split(".") if scope else []
    out: list[str] = []
    while parts:
        out.append(".".join(parts))
        parts = parts[:-1]
    out.append(MODULE_SCOPE)
    return tuple(out)


def attribute_chain(node: ast.expr) -> tuple[str, tuple[str, ...]] | None:
    """Flatten `a.b.c` into ("a", ("b", "c")).

    Returns None when the base of the chain is not a plain name -- e.g.
    `get_client().chat.create`, where there is no name to resolve.
    `self.x.y` comes back as ("self", ("x", "y")); the caller is what
    decides that "self.x" is a binding key.
    """
    attrs: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        attrs.append(current.attr)
        current = current.value
    if not isinstance(current, ast.Name):
        return None
    attrs.reverse()
    return current.id, tuple(attrs)


def dotted(node: ast.expr) -> str | None:
    """`a.b.c` as the literal string "a.b.c", before any resolution."""
    chain = attribute_chain(node)
    if chain is None:
        return None
    base, attrs = chain
    return ".".join((base, *attrs))


@dataclass
class SymbolTable:
    """What the names in one module refer to.

    `imports` maps a local name to the dotted path it was imported as.
    `bindings` maps (scope, name) to the dotted path of the thing
    constructed into it, where scope is the enclosing function's qualified
    name or MODULE_SCOPE. `self.attr` is stored under the name "self.attr"
    in the scope of the method that assigned it, and also at class scope so
    a sibling method can see it.
    """

    imports: dict[str, str] = field(default_factory=dict)
    bindings: dict[tuple[str, str], str] = field(default_factory=dict)
    #: Local names bound to a `mask()`/`MaskResult` result, so masking.py can
    #: tell `client.create(messages=masked)` from `...=raw`.
    masked_names: set[tuple[str, str]] = field(default_factory=set)
    #: Keyword arguments seen on each constructor call, keyed by the dotted
    #: path of the name it was bound to -- this is how a gateway `base_url`
    #: is recovered at the call site that uses the client, not where it was
    #: built.
    client_kwargs: dict[tuple[str, str], dict[str, str]] = field(default_factory=dict)
    #: Factory resolution, from the registry: a method that hands back a
    #: different object you then call. `chroma.get_or_create_collection()`
    #: yields a Collection, and it is `collection.add(...)` that egresses --
    #: without this the chain breaks at the factory and the real sink is
    #: never found. Maps "<client>.<method>" -> the yielded client path.
    factories: dict[str, str] = field(default_factory=dict)

    def resolve_name(self, name: str, scope: str) -> str | None:
        """A bare name -> its dotted path, innermost scope winning."""
        for candidate in scope_chain(scope):
            key = (candidate, name)
            if key in self.bindings:
                return self.bindings[key]
        return self.imports.get(name)

    def resolve(self, node: ast.expr, scope: str) -> str | None:
        """A call target -> its fully resolved dotted path, or None.

        `client.chat.completions.create` becomes
        `openai.OpenAI.chat.completions.create` when `client` is known to
        hold an `openai.OpenAI`.
        """
        chain = attribute_chain(node)
        if chain is None:
            return None
        base, attrs = chain

        # `self.client.chat.create` -- the binding key is "self.client", so
        # try the two-part head before falling back to the bare base.
        if base == "self" and attrs:
            head = f"self.{attrs[0]}"
            resolved = self.resolve_name(head, scope)
            if resolved is not None:
                return ".".join((resolved, *attrs[1:])) if attrs[1:] else resolved

        resolved = self.resolve_name(base, scope)
        if resolved is None:
            return None
        return ".".join((resolved, *attrs)) if attrs else resolved

    def binding_key_for(self, node: ast.expr, scope: str) -> tuple[str, str] | None:
        """The (scope, name) key a call target's receiver is bound under.

        `client.chat.completions.create(...)` -> the key holding `client`,
        so the caller can look up that client's constructor kwargs.
        """
        chain = attribute_chain(node)
        if chain is None:
            return None
        base, attrs = chain
        candidates: list[str] = []
        if base == "self" and attrs:
            candidates.append(f"self.{attrs[0]}")
        candidates.append(base)
        for name in candidates:
            for candidate in scope_chain(scope):
                key = (candidate, name)
                if key in self.bindings:
                    return key
        return None

    def kwargs_for(self, node: ast.expr, scope: str) -> dict[str, str]:
        """Constructor keyword arguments of the client this call targets."""
        key = self.binding_key_for(node, scope)
        if key is None:
            return {}
        return self.client_kwargs.get(key, {})

    def is_masked_name(self, node: ast.expr, scope: str) -> bool:
        """True when this expression is a name holding a mask() result."""
        if not isinstance(node, ast.Name):
            return False
        return any((candidate, node.id) in self.masked_names for candidate in scope_chain(scope))


class _Builder(ast.NodeVisitor):
    """One pass over a module, filling a SymbolTable.

    Runs before the sink walk so a client constructed after its first use
    in source order is still resolved -- module-level order is not call
    order, and a method that uses `self.client` is almost always defined
    before `__init__` is read.
    """

    def __init__(self, table: SymbolTable) -> None:
        self.table = table
        self._scope: list[str] = []
        self._class: list[str] = []

    @property
    def scope(self) -> str:
        return ".".join(self._scope) if self._scope else MODULE_SCOPE

    # -- imports ---------------------------------------------------------
    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.table.imports[alias.asname or alias.name.split(".")[0]] = alias.name
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        # A relative import has no absolute dotted path we can match a
        # third-party sink against, so it is recorded under its own name
        # only; `from . import client` can never be `openai.OpenAI`.
        if node.level:
            self.generic_visit(node)
            return
        module = node.module or ""
        for alias in node.names:
            local = alias.asname or alias.name
            self.table.imports[local] = f"{module}.{alias.name}" if module else alias.name
        self.generic_visit(node)

    # -- scopes ----------------------------------------------------------
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._class.append(node.name)
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()
        self._class.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        self._scope.append(node.name)
        self.generic_visit(node)
        self._scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._function(node)

    # -- bindings --------------------------------------------------------
    def _record(self, target: ast.expr, value: ast.expr) -> None:
        name = self._target_name(target)
        if name is None:
            return

        if self._expr_is_masked(value):
            self.table.masked_names.add(self._key(name))

        if isinstance(value, ast.Call):
            path = self._called_path(value)
            if path is not None:
                self.table.client_kwargs[self._key(name)] = self._literal_kwargs(value)
                self._bind(name, path)
                return

        if isinstance(value, ast.Name):
            # A plain alias of a client keeps pointing at the same client.
            resolved = self.table.resolve_name(value.id, self.scope)
            if resolved is not None:
                self._bind(name, resolved)

    #: Callables that return their input's text unchanged apart from
    #: formatting, so a masked argument makes the result masked too. A
    #: prompt template's .format() is the common case and the one that
    #: would otherwise make a correctly-masked chain read as unmasked.
    _TRANSPARENT = frozenset(
        {"format", "join", "strip", "lstrip", "rstrip", "lower", "upper", "replace", "str"}
    )

    def _expr_is_masked(self, node: ast.expr) -> bool:
        """Does this expression carry mask() output?

        Mirrors masking._argument_is_masked, but at assignment time, so a
        name bound to a formatted masked string is itself recorded masked.
        """
        if isinstance(node, ast.Name):
            return self.table.is_masked_name(node, self.scope)
        if isinstance(node, ast.Attribute) and node.attr == "masked_text":
            return True
        if isinstance(node, ast.Call):
            path = self._called_path(node)
            if path is not None and self._is_mask_call(path):
                return True
            # The transparency check is on the method NAME, which needs no
            # resolution: `template.format(...)` is transparent whatever
            # `template` turns out to be, and templates are usually
            # parameters we cannot resolve.
            literal = dotted(node.func)
            tail = (literal or "").rsplit(".", 1)[-1]
            if tail in self._TRANSPARENT:
                args: list[ast.expr] = [*node.args, *(k.value for k in node.keywords)]
                if isinstance(node.func, ast.Attribute):
                    args.append(node.func.value)
                return any(self._expr_is_masked(a) for a in args)
            return False
        if isinstance(node, ast.JoinedStr):
            return any(
                isinstance(v, ast.FormattedValue) and self._expr_is_masked(v.value)
                for v in node.values
            )
        if isinstance(node, ast.BinOp):
            return self._expr_is_masked(node.left) or self._expr_is_masked(node.right)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return any(self._expr_is_masked(e) for e in node.elts)
        if isinstance(node, ast.Dict):
            return any(v is not None and self._expr_is_masked(v) for v in node.values)
        return False

    def _is_mask_call(self, path: str) -> bool:
        # `maskflow.mask`, `maskflow.sdk.mask`, `maskflow_core.mask`, and a
        # bare `mask` imported from any of them all resolve to a path whose
        # last segment is one of these.
        tail = path.rsplit(".", 1)[-1]
        return tail in {"mask", "mask_with_policy"} and path.split(".")[0] in {
            "maskflow",
            "maskflow_core",
        }

    def _key(self, name: str) -> tuple[str, str]:
        return (self.scope, name)

    def _bind(self, name: str, path: str) -> None:
        self.table.bindings[self._key(name)] = path
        # A `self.x` assigned in one method must be visible in every other
        # method of the class, so mirror it at class scope.
        if name.startswith("self.") and self._class:
            class_scope = ".".join(self._scope[:-1]) if len(self._scope) > 1 else MODULE_SCOPE
            self.table.bindings[(class_scope, name)] = path
            kwargs = self.table.client_kwargs.get(self._key(name))
            if kwargs is not None:
                self.table.client_kwargs[(class_scope, name)] = kwargs

    @staticmethod
    def _target_name(target: ast.expr) -> str | None:
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            chain = attribute_chain(target)
            if chain is not None and chain[0] == "self" and len(chain[1]) == 1:
                return f"self.{chain[1][0]}"
        return None

    def _called_path(self, call: ast.Call) -> str | None:
        """The dotted path of what a Call hands back.

        Resolves through bindings as well as imports, so a factory called
        on an already-bound client is followed, and then applies the
        registry's factory map: the useful answer for
        `chroma.get_or_create_collection()` is the Collection it yields,
        not the factory method itself.
        """
        resolved = self.table.resolve(call.func, self.scope)
        if resolved is None:
            # The base is neither imported nor a known binding, so there is
            # no dotted path here -- only a local name. Returning it anyway
            # would record a resolution we do not have, and a local helper
            # that happened to share a provider's name would then read as
            # that provider. None is the honest answer.
            return None
        return self.table.factories.get(resolved, resolved)

    @staticmethod
    def _literal_kwargs(call: ast.Call) -> dict[str, str]:
        """Keyword arguments whose value is a plain string literal.

        Only literals: a `base_url` built at runtime cannot be judged
        statically, and recording a guess would be worse than recording
        nothing -- masking.py treats an absent base_url as "no evidence"
        rather than "direct".
        """
        out: dict[str, str] = {}
        for keyword in call.keywords:
            if keyword.arg is None:
                continue
            if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
                out[keyword.arg] = keyword.value.value
        return out

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Tuple):
                # `masked, mapping = mask(text)` -- bind the first element
                # only, which is the masked text by MaskResult's contract.
                path = self._called_path(node.value) if isinstance(node.value, ast.Call) else None
                if path is not None and self._is_mask_call(path) and target.elts:
                    first = self._target_name(target.elts[0])
                    if first is not None:
                        self.table.masked_names.add(self._key(first))
                continue
            self._record(target, node.value)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._record(node.target, node.value)
        self.generic_visit(node)

    def visit_With(self, node: ast.With) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._record(item.optional_vars, item.context_expr)
        self.generic_visit(node)

    def visit_AsyncWith(self, node: ast.AsyncWith) -> None:
        for item in node.items:
            if item.optional_vars is not None:
                self._record(item.optional_vars, item.context_expr)
        self.generic_visit(node)


def build_symbol_table(tree: ast.Module, *, factories: dict[str, str] | None = None) -> SymbolTable:
    """One pass over a parsed module, before the sink walk.

    `factories` comes from the registry (see SymbolTable.factories).
    """
    table = SymbolTable(factories=dict(factories or {}))
    _Builder(table).visit(tree)
    return table
