"""Shared fixtures.

Every identifier used anywhere in this suite is SYNTHETIC: generated per
run from a seeded RNG in the shape of the real type (checksum-valid where
the type has a published checksum), never a real person's data. Same
convention, and the same seeded-RNG approach, as maskflow-agent's tests.

The seed is fixed so a failure is reproducible; the values are still
generated rather than committed, so this file never becomes a place where
a PII-shaped constant lives (CLAUDE.md rule 2).
"""

from __future__ import annotations

import random
from pathlib import Path

# Import the audit package FIRST, for its pack ordering side effect, before
# touching maskflow_pack_india below. pytest loads a conftest before any
# test module, so a bare `from maskflow_pack_india...` here would register
# pack-india first; whatever imported pack-intl afterwards would then
# re-register PERSON last and win, silently replacing pack-india's
# span_filter and Devanagari context keywords for the whole session. That
# is the import-order hazard maskflow_cli/app.py documents, reached from an
# unexpected direction -- it broke test_cli_pack_registration.py when these
# suites ran together.
import maskflow_audit  # noqa: F401 -- establishes pack-intl before pack-india
import pytest
from maskflow_pack_india.checksums import verhoeff_generate

_RNG = random.Random(20261031)

_PAN_LETTERS = "ABCDEFGHJKLMNPRSTUVWXYZ"


@pytest.fixture(scope="session")
def fixtures_root() -> Path:
    """The audit-fixtures/ tree at the repository root."""
    return Path(__file__).resolve().parents[3] / "audit-fixtures"


def synthetic_aadhaar() -> str:
    """SYNTHETIC: random 11 digits plus a valid Verhoeff check digit."""
    base = _RNG.choice("23456789") + "".join(_RNG.choice("0123456789") for _ in range(10))
    return base + verhoeff_generate(base)


def synthetic_pan() -> str:
    """SYNTHETIC: a structurally valid PAN (no checksum exists for PAN)."""
    return (
        "".join(_RNG.choice(_PAN_LETTERS) for _ in range(3))
        + "P"
        + _RNG.choice(_PAN_LETTERS)
        + "".join(_RNG.choice("0123456789") for _ in range(4))
        + _RNG.choice(_PAN_LETTERS)
    )


def synthetic_mobile() -> str:
    """SYNTHETIC: an Indian mobile shape."""
    return _RNG.choice("6789") + "".join(_RNG.choice("0123456789") for _ in range(9))


@pytest.fixture
def canaries() -> dict[str, str]:
    """Three synthetic values, regenerated every call.

    Exposed as a fixture rather than imported directly: several packages
    in this workspace ship a `conftest.py`, and `from conftest import ...`
    would bind to whichever one reached sys.path first.
    """
    return {
        "AADHAAR": synthetic_aadhaar(),
        "PAN": synthetic_pan(),
        "INDIAN_MOBILE": synthetic_mobile(),
    }


@pytest.fixture
def tree(tmp_path: Path):
    """Writes a module into a throwaway tree and returns the tree root."""

    def _write(source: str, name: str = "app.py") -> Path:
        (tmp_path / name).write_text(source, encoding="utf-8")
        return tmp_path

    return _write
