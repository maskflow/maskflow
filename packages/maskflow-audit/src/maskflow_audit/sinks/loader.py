"""registry.yaml -> frozen SinkDef objects.

Every validator collects every problem it finds rather than raising on the
first, so a contributor who mistypes three fields is told about three
fields -- the same policy as maskflow_core.config.schema. The registry is
shipped data, not user input, so a problem here is a packaging bug and
RegistryError is fatal rather than a soft issue list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

#: The category vocabulary. A sink outside these is rejected, because the
#: report groups by category and an unknown one would render as a blank
#: section rather than fail loudly.
CATEGORIES: tuple[str, ...] = (
    "llm_sdk",
    "framework",
    "raw_http",
    "vector_write",
    "observability",
    "mcp",
)

_SUPPORTED_VERSION = 1

_SINK_KEYS = frozenset(
    {
        "id",
        "category",
        "provider",
        "hosts",
        "clients",
        "methods",
        "functions",
        "text_args",
        "url_args",
        "factories",
        "notes",
    }
)
_ARG_KEYS = frozenset({"keywords", "positional"})


class RegistryError(Exception):
    """The shipped registry is malformed. Carries every problem found.

    The message lists sink ids and field names only -- there is no user
    data anywhere near this file, but the habit is the one rule 1 asks for.
    """

    def __init__(self, problems: list[str]) -> None:
        self.problems = problems
        joined = "\n".join(f"  - {p}" for p in problems)
        super().__init__(f"sink registry is invalid ({len(problems)} problem(s)):\n{joined}")


@dataclass(frozen=True)
class ArgSpec:
    """Where a payload sits in a call's arguments.

    `keywords` are keyword-argument names; `positional` are 0-based indices.
    Both may be empty -- a sink can be worth reporting even when we cannot
    say which argument carried the text (an @observe decorator, say).
    """

    keywords: tuple[str, ...] = ()
    positional: tuple[int, ...] = ()

    @property
    def is_empty(self) -> bool:
        return not self.keywords and not self.positional


@dataclass(frozen=True)
class Factory:
    """A method that hands back a different object you then call.

    `chroma.get_or_create_collection()` returns a Collection, and it is
    `collection.add(...)` that egresses. Without this the resolution chain
    stops at the factory and the real sink is never found -- which is
    exactly the bug fixture 02 caught.
    """

    method: str
    yields: str


@dataclass(frozen=True)
class SinkDef:
    """One registry entry.

    A sink matches either `functions` (a module-level callable that
    egresses) or `clients` x `methods` (a constructed client you then call),
    and may declare both -- raw_http does, because `requests.post` and
    `session.post` are the same sink.
    """

    id: str
    category: str
    provider: str
    hosts: tuple[str, ...] = ()
    clients: tuple[str, ...] = ()
    methods: tuple[str, ...] = ()
    functions: tuple[str, ...] = ()
    text_args: ArgSpec = field(default_factory=ArgSpec)
    url_args: ArgSpec | None = None
    factories: tuple[Factory, ...] = ()
    notes: str = ""

    @property
    def requires_host_match(self) -> bool:
        """True when a call only counts once its URL resolves to `hosts`."""
        return self.url_args is not None


def registry_path() -> Path:
    """The shipped registry.yaml next to this module."""
    return Path(__file__).resolve().parent / "registry.yaml"


def _strs(value: Any, where: str, problems: list[str]) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        problems.append(f"{where}: expected a list of strings")
        return ()
    out: list[str] = []
    for i, item in enumerate(value):
        if not isinstance(item, str) or not item:
            problems.append(f"{where}[{i}]: expected a non-empty string")
            continue
        out.append(item)
    return tuple(out)


def _arg_spec(value: Any, where: str, problems: list[str]) -> ArgSpec:
    if value is None:
        return ArgSpec()
    if not isinstance(value, dict):
        problems.append(f"{where}: expected a mapping with keywords/positional")
        return ArgSpec()
    unknown = sorted(set(value) - _ARG_KEYS)
    if unknown:
        problems.append(f"{where}: unknown key(s) {unknown}; allowed: {sorted(_ARG_KEYS)}")
    keywords = _strs(value.get("keywords"), f"{where}.keywords", problems)
    positional_raw = value.get("positional")
    positional: list[int] = []
    if positional_raw is not None:
        if not isinstance(positional_raw, list):
            problems.append(f"{where}.positional: expected a list of integers")
        else:
            for i, item in enumerate(positional_raw):
                # bool is an int subclass; a stray `true` here would silently
                # mean index 1, so reject it explicitly.
                if not isinstance(item, int) or isinstance(item, bool) or item < 0:
                    problems.append(f"{where}.positional[{i}]: expected a non-negative integer")
                    continue
                positional.append(item)
    return ArgSpec(keywords=keywords, positional=tuple(positional))


def _factories(value: Any, where: str, problems: list[str]) -> tuple[Factory, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        problems.append(f"{where}: expected a list of {{method, yields}} mappings")
        return ()
    out: list[Factory] = []
    for i, item in enumerate(value):
        if not isinstance(item, dict):
            problems.append(f"{where}[{i}]: expected a mapping")
            continue
        unknown = sorted(set(item) - {"method", "yields"})
        if unknown:
            problems.append(f"{where}[{i}]: unknown key(s) {unknown}")
        method, yields = item.get("method"), item.get("yields")
        if not isinstance(method, str) or not method:
            problems.append(f"{where}[{i}].method: expected a non-empty string")
            continue
        if not isinstance(yields, str) or not yields:
            problems.append(f"{where}[{i}].yields: expected a non-empty string")
            continue
        out.append(Factory(method=method, yields=yields))
    return tuple(out)


def _sink(raw: Any, index: int, problems: list[str]) -> SinkDef | None:
    where = f"sinks[{index}]"
    if not isinstance(raw, dict):
        problems.append(f"{where}: expected a mapping")
        return None

    sink_id = raw.get("id")
    if not isinstance(sink_id, str) or not sink_id:
        problems.append(f"{where}.id: expected a non-empty string")
        return None
    where = f"sink {sink_id!r}"

    unknown = sorted(set(raw) - _SINK_KEYS)
    if unknown:
        problems.append(f"{where}: unknown key(s) {unknown}; allowed: {sorted(_SINK_KEYS)}")

    category = raw.get("category")
    if category not in CATEGORIES:
        problems.append(f"{where}.category: {category!r} is not one of {list(CATEGORIES)}")
        category = ""

    provider = raw.get("provider")
    if not isinstance(provider, str) or not provider:
        problems.append(f"{where}.provider: expected a non-empty string")
        provider = "unknown"

    notes = raw.get("notes", "")
    if not isinstance(notes, str):
        problems.append(f"{where}.notes: expected a string")
        notes = ""

    clients = _strs(raw.get("clients"), f"{where}.clients", problems)
    methods = _strs(raw.get("methods"), f"{where}.methods", problems)
    functions = _strs(raw.get("functions"), f"{where}.functions", problems)
    hosts = _strs(raw.get("hosts"), f"{where}.hosts", problems)

    # A client with no methods can never match, and a method with no client
    # would match every object in the tree. Either mistake makes the entry
    # silently useless, which is worse than a loud failure -- except for an
    # entry that is pure documentation (helicone-proxy), which declares
    # neither and is matched by masking.py's base_url inspection instead.
    if clients and not methods:
        problems.append(f"{where}: declares clients but no methods, so it can never match")
    if methods and not clients:
        problems.append(f"{where}: declares methods but no clients, so it would match anything")

    factories = _factories(raw.get("factories"), f"{where}.factories", problems)
    for factory in factories:
        if factory.yields not in clients:
            problems.append(
                f"{where}: factory {factory.method!r} yields {factory.yields!r}, which is not "
                "in this sink's clients, so the yielded object's methods could never match"
            )

    text_args = _arg_spec(raw.get("text_args"), f"{where}.text_args", problems)
    url_args = (
        _arg_spec(raw.get("url_args"), f"{where}.url_args", problems) if "url_args" in raw else None
    )

    if url_args is not None and not hosts:
        problems.append(f"{where}: declares url_args but no hosts to match the URL against")

    if category == "":
        return None
    return SinkDef(
        id=sink_id,
        category=category,
        provider=provider,
        hosts=hosts,
        clients=clients,
        methods=methods,
        functions=functions,
        text_args=text_args,
        url_args=url_args,
        factories=factories,
        notes=notes,
    )


def load_registry(path: Path | None = None) -> tuple[SinkDef, ...]:
    """Parse and validate the registry. Raises RegistryError on any problem."""
    target = path if path is not None else registry_path()
    problems: list[str] = []

    try:
        raw = yaml.safe_load(target.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RegistryError([f"{target}: not found"]) from exc
    except yaml.YAMLError as exc:
        # Deliberately not re-raising the yaml error: its message quotes the
        # offending source line, and keeping our own shape means callers only
        # ever handle RegistryError.
        raise RegistryError(
            [f"{target}: could not parse as YAML: {exc.__class__.__name__}"]
        ) from exc

    if not isinstance(raw, dict):
        raise RegistryError([f"{target}: top level must be a mapping"])

    version = raw.get("version")
    if version != _SUPPORTED_VERSION:
        raise RegistryError(
            [
                f"{target}: version {version!r} is not supported "
                f"(this build reads {_SUPPORTED_VERSION})"
            ]
        )

    sinks_raw = raw.get("sinks")
    if not isinstance(sinks_raw, list) or not sinks_raw:
        raise RegistryError([f"{target}: `sinks` must be a non-empty list"])

    sinks: list[SinkDef] = []
    seen: set[str] = set()
    for index, entry in enumerate(sinks_raw):
        sink = _sink(entry, index, problems)
        if sink is None:
            continue
        if sink.id in seen:
            problems.append(f"sink {sink.id!r}: duplicate id")
            continue
        seen.add(sink.id)
        sinks.append(sink)

    if problems:
        raise RegistryError(problems)
    return tuple(sinks)


@lru_cache(maxsize=1)
def default_registry() -> tuple[SinkDef, ...]:
    """The shipped registry, parsed once per process."""
    return load_registry()


def factory_map(sinks: tuple[SinkDef, ...]) -> dict[str, str]:
    """ "<client>.<method>" -> yielded client path, for the symbol table."""
    out: dict[str, str] = {}
    for sink in sinks:
        for client in sink.clients:
            for factory in sink.factories:
                out[f"{client}.{factory.method}"] = factory.yields
    return out
