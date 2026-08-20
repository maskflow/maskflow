"""Leak-gate primitives shared by every package's test suite: install a
log/exception-capturing handler for the whole pytest session, run
`@pytest.mark.leak` tests last (so they see everything the session
produced), and let a package assert none of its known PII fixture literals
ever showed up in a log record or an exception's text. See CLAUDE.md rule 1
(raw PII must never reach logs, exceptions, or repr).

Not imported by `maskflow_core/__init__.py` -- this is test-only tooling, not
part of the <200ms-import engine surface. A package's tests/conftest.py wires
it in with:

    from maskflow_core.testing import (
        LEAK_POOL,
        assert_no_leaks,
        pytest_collection_modifyitems,
        pytest_configure,
        pytest_exception_interact,
    )

and a single test (marked `@pytest.mark.leak`, so it's ordered last) that
calls `assert_no_leaks(LEAK_POOL, known_pii_values)` once everything else in
the session has run. `test_leak_guards.py` covers the "repr" leg of rule 1
directly (per-class assertions); this module covers "log record"/"exception".

`pytest_configure` also neutralizes any `-m`/markexpr that mentions "leak"
(see its body) -- the gate needs the whole session to run to mean anything,
so `pytest -m leak` runs everything rather than deselecting down to just the
leak-gate test and trivially passing against an empty pool.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pytest

# Matches "leak" as a whole marker name inside a `-m`/markexpr string (e.g.
# "leak", "leak or benchmark", "not leak") -- not as a substring of some
# other marker that happens to contain the letters "leak".
_LEAK_MARKER_RE = re.compile(r"\bleak\b")


class _CapturingHandler(logging.Handler):
    def __init__(self, pool: list[str]) -> None:
        super().__init__(level=logging.DEBUG)
        self._pool = pool

    def emit(self, record: logging.LogRecord) -> None:
        self._pool.append(record.getMessage())


# Populated for the lifetime of one pytest session: log records and
# exception text captured across every test, regardless of that test's own
# marks. A leak-marked test (ordered last, see pytest_collection_modifyitems
# below) scans this pool once everything else has run.
LEAK_POOL: list[str] = []

_handler = _CapturingHandler(LEAK_POOL)


def pytest_configure(config: pytest.Config) -> None:
    root_logger = logging.getLogger()
    if _handler not in root_logger.handlers:
        root_logger.addHandler(_handler)
    root_logger.setLevel(min(root_logger.level or logging.WARNING, logging.DEBUG))

    # `pytest -m leak` alone would otherwise deselect every OTHER test before
    # any of them run -- and LEAK_POOL only ever fills from whatever ran
    # earlier in this same process, so the correctly-ordered-last leak test
    # would then check an empty pool and trivially pass, even with an active
    # PII leak elsewhere in the code it never got a chance to see. The "leak"
    # marker exists for ordering (pytest_collection_modifyitems below) and
    # identification, not selection, so a markexpr that mentions it gets
    # neutralized here -- the whole session still runs, same as if no -m
    # flag had been passed at all.
    markexpr = getattr(config.option, "markexpr", "") or ""
    if _LEAK_MARKER_RE.search(markexpr):
        config.option.markexpr = ""


def pytest_exception_interact(node: Any, call: Any, report: Any) -> None:
    excinfo = getattr(call, "excinfo", None)
    if excinfo is None:
        return
    LEAK_POOL.append(str(excinfo.value))
    LEAK_POOL.append(str(excinfo.getrepr(style="long")))


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    # Stable sort: leak-marked items move to the end, everything else keeps
    # its collected order -- so the leak-gate assertion runs after (and can
    # see log/exception output from) every other test in the session.
    items.sort(key=lambda item: 1 if item.get_closest_marker("leak") else 0)


def assert_no_leaks(pool: Iterable[str], secrets: Iterable[str]) -> None:
    haystack = "\n".join(pool)
    leaked = [s for s in secrets if s and s in haystack]
    assert not leaked, f"PII fixture value(s) leaked into logs/exceptions: {leaked!r}"
