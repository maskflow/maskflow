"""A production `logging.Filter` a downstream app can install so that *its
own* logger calls -- not just MaskFlow's -- never emit raw PII. See CLAUDE.md
rule #1 and issue #23: repr-exclusion and the `pytest -m leak` gate (see
`maskflow_core.testing`) only protect this library's own test session; they
say nothing about a consuming app doing e.g. `logger.info(f"...{raw_text}")`
before ever calling mask(), or a third-party recognizer plugin doing
`logger.debug(span.text)`. This module is that missing safety net.

Opt-in, not automatic: importing `maskflow_core` never touches global logging
state on its own (a library mutating a host app's root logger as an import
side effect would be its own kind of surprise). Call `install_pii_filter()`
once, typically at app startup.

Regex/checksum-validated patterns only (`detect_patterns_only()`) -- no NER,
no spaCy load. A log filter runs on every single log call in the host app,
which is a very different cost profile from a per-request mask() call, and
core's own architecture already treats the NER pass as the expensive,
optional part (see detection.py's tier-0 excision, the `[nlp]` extra). This
means a bare name or street address typed into a log line is NOT caught --
only entity types with a registered pattern/checksum recognizer are (Aadhaar,
PAN, email, credit card, ...). `exc_info`/traceback text is also out of
scope: a Formatter computes that after filters run, so a Filter can't
reliably rewrite it.
"""

from __future__ import annotations

import logging

from .detection import DEFAULT_MIN_CONFIDENCE, detect_patterns_only
from .entities import PIIType

# Sentinel attribute marking a logger as already carrying a PIIRedactionFilter,
# so install_pii_filter() is safe to call more than once (e.g. once per
# module doing its own logging setup) without attaching duplicates that would
# each redact the record independently.
_INSTALLED_ATTR = "_maskflow_pii_redaction_filter"


class PIIRedactionFilter(logging.Filter):
    """Scrubs a LogRecord's formatted message through
    `detect_patterns_only()` before emission, replacing each detected span
    with `<ENTITY_TYPE>`. Never drops a record -- always returns True from
    `filter()`; this redacts, it does not silence.

    Only `record.msg`/`record.args` are touched (i.e. what
    `record.getMessage()` produces). A clean message -- the overwhelming
    common case -- takes a fast path: no spans found, record left untouched,
    no string rebuilt.
    """

    def __init__(
        self,
        min_confidence: float = DEFAULT_MIN_CONFIDENCE,
        *,
        disabled_types: frozenset[PIIType] = frozenset(),
    ) -> None:
        super().__init__()
        self._min_confidence = min_confidence
        self._disabled_types = disabled_types

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        spans = detect_patterns_only(
            message,
            self._min_confidence,
            disabled_types=self._disabled_types,
        )
        if not spans:
            return True

        pieces: list[str] = []
        cursor = 0
        for span in spans:  # non-overlapping, sorted by start
            pieces.append(message[cursor : span.start])
            pieces.append(f"<{span.entity_type.value}>")
            cursor = span.end
        pieces.append(message[cursor:])

        record.msg = "".join(pieces)
        record.args = ()
        return True


def install_pii_filter(
    logger: logging.Logger | None = None,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
    *,
    disabled_types: frozenset[PIIType] = frozenset(),
) -> PIIRedactionFilter:
    """Attach a PIIRedactionFilter to `logger` (default: the root logger, so
    every logger in the process that propagates to it is covered). Idempotent
    per logger -- calling this again on the same logger returns the
    already-installed filter rather than attaching a second one."""
    target = logger if logger is not None else logging.getLogger()

    existing = getattr(target, _INSTALLED_ATTR, None)
    if isinstance(existing, PIIRedactionFilter):
        return existing

    pii_filter = PIIRedactionFilter(min_confidence, disabled_types=disabled_types)
    target.addFilter(pii_filter)
    setattr(target, _INSTALLED_ATTR, pii_filter)
    return pii_filter


__all__ = ["PIIRedactionFilter", "install_pii_filter"]
