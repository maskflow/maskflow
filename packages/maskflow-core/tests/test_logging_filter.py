"""Covers the still-open leg of issue #23: a production logging filter a
downstream app can install so that *its own* logger calls -- not just
MaskFlow's -- never emit raw PII. See maskflow_core.logging_filter and
CLAUDE.md rule #1.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator

import pytest
from maskflow_core.logging_filter import PIIRedactionFilter, install_pii_filter
from maskflow_core.registry import register_pattern

MARKER_RE = re.compile(r"\bMARK-LOG-\d{4}\b")
register_pattern("TEST_LOG_MARKER", MARKER_RE, 0.95)


@pytest.fixture
def captured() -> Iterator[list[str]]:
    """A fresh logger + a plain handler capturing formatted output, isolated
    from the root logger and from the leak-gate's own capturing handler."""
    records: list[str] = []

    class _Handler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record.getMessage())

    logger = logging.getLogger("test_logging_filter")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = _Handler()
    logger.addHandler(handler)

    yield records

    logger.removeHandler(handler)
    logger.filters.clear()
    if hasattr(logger, "_maskflow_pii_redaction_filter"):
        del logger._maskflow_pii_redaction_filter  # type: ignore[attr-defined]


@pytest.mark.leak
def test_install_pii_filter_redacts_downstream_logger_call(captured: list[str]) -> None:
    logger = logging.getLogger("test_logging_filter")
    install_pii_filter(logger)

    # The exact scenario the issue calls out: an app (or a third-party
    # recognizer plugin) logging a raw value it never ran through mask() --
    # not a MaskFlow-internal log call.
    logger.info("processing record for %s", "MARK-LOG-1234")

    assert "MARK-LOG-1234" not in captured[0]
    assert "<TEST_LOG_MARKER>" in captured[0]


def test_clean_message_passes_through_untouched(captured: list[str]) -> None:
    logger = logging.getLogger("test_logging_filter")
    install_pii_filter(logger)

    logger.info("nothing sensitive here")

    assert captured == ["nothing sensitive here"]


def test_install_is_idempotent(captured: list[str]) -> None:
    logger = logging.getLogger("test_logging_filter")
    first = install_pii_filter(logger)
    second = install_pii_filter(logger)

    assert first is second
    assert len(logger.filters) == 1

    logger.info("value %s", "MARK-LOG-5678")
    # A single filter redacts once; a duplicate-attached filter would leave
    # this looking the same by luck (idempotent redaction) but double the
    # detect_patterns_only() cost per record -- len(logger.filters) above is
    # the real assertion.
    assert "MARK-LOG-5678" not in captured[0]


def test_filter_never_drops_the_record() -> None:
    pii_filter = PIIRedactionFilter()
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="MARK-LOG-9999", args=(), exc_info=None,
    )
    assert pii_filter.filter(record) is True


def test_positional_args_are_cleared_after_redaction() -> None:
    pii_filter = PIIRedactionFilter()
    record = logging.LogRecord(
        name="x", level=logging.INFO, pathname="", lineno=0,
        msg="id=%s", args=("MARK-LOG-4242",), exc_info=None,
    )
    pii_filter.filter(record)

    assert record.args == ()
    assert "MARK-LOG-4242" not in record.msg
    assert "MARK-LOG-4242" not in record.getMessage()
