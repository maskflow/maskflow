from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from maskflow_core.entities import PIIType


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture(autouse=True)
def _reset_piitype_registry() -> Iterator[None]:
    """compile_config() (engine.py) calls PIIType.register() for
    [custom.*] entries -- reset the registry after each test so a custom
    type registered by one test doesn't leak into another.
    PIIType._registered is a class-level dict, not covered by the root
    conftest's registry reset (that one only covers
    PATTERNS/NER_RECOGNIZERS/CONTEXT_KEYWORDS/SURROGATE_GENERATORS)."""
    snapshot = dict(PIIType._registered)
    yield
    PIIType._registered.clear()
    PIIType._registered.update(snapshot)
