"""Turn a masking decision into evidence events -- without ever reading a
detected value.

``derive.py`` may touch ``Span.start``/``end``/``entity_type``/``score``/
``recognizer`` and ``MappingEntry.entity_type``/``strategy``/``score``/
``recognizer``. It must never read ``Span.text`` or ``MappingEntry.original``
-- ``tests/test_derive_no_value_access.py`` enforces this with an AST check.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from maskflow_core import Mapping, Span
from maskflow_core.strategies import Strategy

from .schema import EvidenceEvent
from .versions import engine_version, pack_version

# maskflow_core.Strategy -> evidence `action`. HASH collapses to "masked":
# from an evidence standpoint the value was replaced by something
# non-recoverable, same category as MASK/REDACT is "redacted".
_STRATEGY_ACTION: dict[Strategy, str] = {
    Strategy.REPLACE: "masked",
    Strategy.MASK: "masked",
    Strategy.HASH: "masked",
    Strategy.REDACT: "redacted",
    Strategy.SURROGATE: "surrogate",
}


@dataclass(frozen=True)
class EventContext:
    """The invariant part of every event from one masking call. All fields
    are validated as slugs by ``EvidenceEvent`` -- a caller that passes an
    email as ``session_id`` gets an ``EvidenceSchemaError``."""

    session_id: str
    service: str
    environment: str
    provider: str | None = None
    model: str | None = None


def _emit_group(
    ctx: EventContext,
    entity_type: str,
    recognizer: str,
    action: str,
    scores: list[float],
) -> EvidenceEvent:
    return EvidenceEvent(
        entity_type=entity_type,
        count=len(scores),
        # The most conservative claim: the weakest detection in the group.
        score=min(scores),
        recognizer=recognizer,
        action=action,
        service=ctx.service,
        environment=ctx.environment,
        session_id=ctx.session_id,
        provider=ctx.provider,
        model=ctx.model,
        pack_version=pack_version(),
        engine_version=engine_version(),
    )


def events_from_spans(
    spans: Sequence[Span],
    ctx: EventContext,
    *,
    strategy_for: Callable[[str], str] | None = None,
    dropped: Iterable[Span] = (),
) -> list[EvidenceEvent]:
    """One event per ``(entity_type, recognizer, action)`` across the
    resolved ``spans`` (plus any ``dropped`` spans, which become
    ``action="passed"``).

    ``strategy_for`` maps an entity-type name to an evidence action
    (``"masked"``/``"redacted"``/``"surrogate"``); when omitted every
    resolved span is treated as ``"masked"``.
    """
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    for span in spans:
        etype = span.entity_type.value
        action = strategy_for(etype) if strategy_for is not None else "masked"
        groups[(etype, span.recognizer, action)].append(span.score)

    for span in dropped:
        groups[(span.entity_type.value, span.recognizer, "passed")].append(span.score)

    return [
        _emit_group(ctx, etype, recognizer, action, scores)
        for (etype, recognizer, action), scores in sorted(groups.items())
    ]


def action_for_strategy(strategy: Strategy) -> str:
    return _STRATEGY_ACTION.get(strategy, "masked")


def events_from_mapping(
    mapping: Mapping,
    ctx: EventContext,
    *,
    only_tokens: Iterable[str] | None = None,
) -> list[EvidenceEvent]:
    """Events from a ``mask_with_policy`` result -- the gateway path, which
    holds the session ``Mapping`` rather than the span list.

    ``only_tokens`` restricts to tokens added by the current request (the
    gateway diffs the mapping before/after each mask call). ``score`` and
    ``recognizer`` come from the ``MappingEntry`` when present (core >=
    0.6.x populates them); otherwise ``recognizer`` is ``"unknown"`` and the
    group score defaults to ``1.0``.
    """
    wanted = set(only_tokens) if only_tokens is not None else None
    groups: dict[tuple[str, str, str], list[float]] = defaultdict(list)

    for token, entry in mapping.items():
        if wanted is not None and token not in wanted:
            continue
        etype = entry.entity_type.value
        action = action_for_strategy(entry.strategy)
        recognizer = getattr(entry, "recognizer", None) or "unknown"
        score = getattr(entry, "score", None)
        groups[(etype, recognizer, action)].append(1.0 if score is None else float(score))

    return [
        _emit_group(ctx, etype, recognizer, action, scores)
        for (etype, recognizer, action), scores in sorted(groups.items())
    ]
