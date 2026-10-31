"""The shipped registry parses, and a malformed one fails loudly."""

from __future__ import annotations

from pathlib import Path

import pytest
from maskflow_audit.sinks.loader import (
    CATEGORIES,
    RegistryError,
    factory_map,
    load_registry,
    registry_path,
)


def test_shipped_registry_loads() -> None:
    sinks = load_registry()
    assert sinks, "the shipped registry must not be empty"
    assert all(s.category in CATEGORIES for s in sinks)
    assert len({s.id for s in sinks}) == len(sinks), "sink ids must be unique"


def test_shipped_registry_is_packaged() -> None:
    # A wheel that forgets the YAML would fail only at first use, which is
    # exactly the kind of packaging bug a smoke test should catch.
    assert registry_path().is_file()


def test_every_category_is_represented() -> None:
    covered = {s.category for s in load_registry()}
    assert covered == set(CATEGORIES), f"uncovered categories: {set(CATEGORIES) - covered}"


def test_every_factory_yields_a_declared_client() -> None:
    for sink in load_registry():
        for factory in sink.factories:
            assert factory.yields in sink.clients, (
                f"{sink.id}: factory {factory.method} yields {factory.yields}, "
                "which is not in clients, so it could never match"
            )


def test_factory_map_is_keyed_by_client_and_method() -> None:
    mapping = factory_map(load_registry())
    assert mapping["chromadb.PersistentClient.get_or_create_collection"] == "chromadb.Collection"


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "registry.yaml"
    path.write_text(body, encoding="utf-8")
    return path


def test_unsupported_version_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="version"):
        load_registry(_write(tmp_path, "version: 99\nsinks: []\n"))


def test_missing_file_is_refused(tmp_path: Path) -> None:
    with pytest.raises(RegistryError, match="not found"):
        load_registry(tmp_path / "absent.yaml")


def test_every_problem_is_collected_not_just_the_first(tmp_path: Path) -> None:
    # Three separate mistakes in one file; the contributor should be told
    # about all three, the same policy as core's config schema.
    path = _write(
        tmp_path,
        """
version: 1
sinks:
  - id: a
    category: not_a_category
    provider: x
  - id: b
    category: llm_sdk
    provider: y
    clients: ["x.Y"]
  - id: b
    category: llm_sdk
    provider: z
    methods: ["create"]
""",
    )
    with pytest.raises(RegistryError) as excinfo:
        load_registry(path)
    problems = "\n".join(excinfo.value.problems)
    assert "not_a_category" in problems
    assert "clients but no methods" in problems
    assert "methods but no clients" in problems
    assert len(excinfo.value.problems) >= 3


def test_url_args_without_hosts_is_refused(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        """
version: 1
sinks:
  - id: a
    category: raw_http
    provider: x
    functions: ["requests.post"]
    url_args:
      keywords: ["url"]
""",
    )
    with pytest.raises(RegistryError, match="no hosts"):
        load_registry(path)


def test_boolean_is_not_accepted_as_a_positional_index(tmp_path: Path) -> None:
    # bool is an int subclass, so `true` would otherwise mean index 1.
    path = _write(
        tmp_path,
        """
version: 1
sinks:
  - id: a
    category: llm_sdk
    provider: x
    functions: ["m.f"]
    text_args:
      positional: [true]
""",
    )
    with pytest.raises(RegistryError, match="non-negative integer"):
        load_registry(path)
