"""Central span-overlap resolution -- the single point where PII candidate
spans from every recognizer (regex + NER) are deduplicated into the final
non-overlapping list used for masking. See CLAUDE.md 'Design decisions' #1.

Algorithm, in short:
  1. Drop spans below their entity type's confidence threshold.
  2. Sort by priority: validated desc, score desc, length desc, start asc.
  3. Greedily accept spans in that order. Two spans that partially overlap
     without either containing the other (CROSSING) can never both survive --
     the text can't be tokenized for a partial overlap. A span fully nested
     inside another (CONTAINS) is a conflict too, UNLESS the containing
     type's overlap policy is CONTAINED, in which case the more specific
     (validated over unvalidated, else smaller) span wins. Two disjoint spans
     of the same type separated only by whitespace/a single punctuation
     character (ADJACENT) never conflict at accept time.
  4. If the winning type's policy is MERGE, a second pass joins adjacent
     same-type survivors into one span.

INVARIANT: a validated span never loses to an overlapping unvalidated span,
regardless of score, length, or overlap policy.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import Enum, auto

from .entities import ExplanationStep, PIIType, Span

# A single optional whitespace char, then a single optional punctuation char,
# then a single optional whitespace char -- i.e. at most one separator
# character (plus surrounding space) between two same-type spans for them to
# be considered ADJACENT rather than DISJOINT.
_ADJACENT_GAP_RE = re.compile(r"^\s?[^\w\s]?\s?$")


class OverlapPolicy(Enum):
    STRICT = auto()
    CONTAINED = auto()
    MERGE = auto()


class Relationship(Enum):
    DISJOINT = auto()
    ADJACENT = auto()
    CROSSING = auto()
    CONTAINS = auto()  # one fully contains the other, either direction


@dataclass(frozen=True)
class ResolveConfig:
    default_threshold: float = 0.5
    per_entity_threshold: dict[PIIType, float] = field(default_factory=dict)
    default_overlap_policy: OverlapPolicy = OverlapPolicy.STRICT
    per_entity_overlap_policy: dict[PIIType, OverlapPolicy] = field(default_factory=dict)

    def threshold_for(self, entity_type: PIIType) -> float:
        return self.per_entity_threshold.get(entity_type, self.default_threshold)

    def policy_for(self, entity_type: PIIType) -> OverlapPolicy:
        return self.per_entity_overlap_policy.get(entity_type, self.default_overlap_policy)


def _relationship(a: Span, b: Span, text: str) -> Relationship:
    if a.end <= b.start:
        gap = text[a.end : b.start]
    elif b.end <= a.start:
        gap = text[b.end : a.start]
    else:
        if a.start <= b.start and b.end <= a.end:
            return Relationship.CONTAINS  # a contains b
        if b.start <= a.start and a.end <= b.end:
            return Relationship.CONTAINS  # b contains a
        return Relationship.CROSSING

    if a.entity_type == b.entity_type and _ADJACENT_GAP_RE.match(gap):
        return Relationship.ADJACENT
    return Relationship.DISJOINT


def _merge_adjacent(spans: list[Span], text: str, config: ResolveConfig) -> list[Span]:
    if not spans:
        return spans

    merged = [spans[0]]
    for nxt in spans[1:]:
        prev = merged[-1]
        if (
            config.policy_for(nxt.entity_type) == OverlapPolicy.MERGE
            and _relationship(prev, nxt, text) == Relationship.ADJACENT
        ):
            merged[-1] = Span(
                start=prev.start,
                end=nxt.end,
                entity_type=nxt.entity_type,
                score=max(prev.score, nxt.score),
                recognizer=f"merged({prev.recognizer}+{nxt.recognizer})",
                text=text[prev.start : nxt.end],
                validated=prev.validated or nxt.validated,
                explanation=[
                    *prev.explanation,
                    *nxt.explanation,
                    ExplanationStep(
                        rule="merge", outcome="merged", detail="adjacent same-type spans"
                    ),
                ],
            )
        else:
            merged.append(nxt)
    return merged


def resolve(candidates: Sequence[Span], text: str, config: ResolveConfig) -> list[Span]:
    """Resolve a pool of candidate spans (usually overlapping) into the final
    non-overlapping list, per `config`."""
    live = [s for s in candidates if s.score >= config.threshold_for(s.entity_type)]

    # validated desc, score desc, length desc, start asc -- a checksum-validated
    # span always beats an overlapping unvalidated one, regardless of raw score.
    ordered = sorted(
        live,
        key=lambda s: (not s.validated, -s.score, -(s.end - s.start), s.start),
    )

    accepted: list[Span] = []
    for cand in ordered:
        conflict = False
        replaces: list[Span] = []

        for kept in accepted:
            rel = _relationship(cand, kept, text)
            if rel in (Relationship.DISJOINT, Relationship.ADJACENT):
                continue
            if rel == Relationship.CROSSING:
                conflict = True
                break

            # rel == CONTAINS
            prefers_cand = config.policy_for(kept.entity_type) == OverlapPolicy.CONTAINED and (
                (cand.validated and not kept.validated)
                or (
                    cand.validated == kept.validated
                    and (cand.end - cand.start) < (kept.end - kept.start)
                )
            )
            if prefers_cand:
                cand.explanation.append(
                    ExplanationStep(
                        rule="overlap:contained",
                        outcome="preferred",
                        detail=f"over {kept.recognizer} span [{kept.start}:{kept.end}]",
                    )
                )
                replaces.append(kept)
                continue
            conflict = True
            break

        if not conflict:
            for kept in replaces:
                accepted.remove(kept)
            accepted.append(cand)

    accepted.sort(key=lambda s: s.start)
    return _merge_adjacent(accepted, text, config)


def resolve_verbose(
    candidates: Sequence[Span], text: str, config: ResolveConfig
) -> tuple[list[Span], list[Span]]:
    """Like resolve(), but also returns the candidates dropped purely for
    scoring below their entity type's threshold -- not spans that lost to
    an overlapping competitor, only the threshold cut `resolve()` applies
    before ordering/accepting anything. `accepted` is identical to what
    `resolve(candidates, text, config)` alone returns.

    This is the extra bookkeeping `maskflow explain`'s NEAREST MISSES needs
    and nothing else calls for -- kept out of `resolve()` itself so the
    normal detect()/mask() hot path (which never inspects rejected
    candidates) doesn't pay for it.
    """
    accepted = resolve(candidates, text, config)
    rejected = [c for c in candidates if c.score < config.threshold_for(c.entity_type)]
    for span in rejected:
        span.explanation.append(
            ExplanationStep(
                rule="threshold",
                outcome="dropped",
                detail=f"score {span.score} < threshold {config.threshold_for(span.entity_type)}",
            )
        )
    return accepted, rejected


@dataclass(frozen=True)
class SpanSet:
    """A pool of candidate spans over one piece of text, ready for resolution."""

    text: str
    spans: tuple[Span, ...]

    def resolve(self, config: ResolveConfig) -> list[Span]:
        return resolve(self.spans, self.text, config)

    def resolve_verbose(self, config: ResolveConfig) -> tuple[list[Span], list[Span]]:
        return resolve_verbose(self.spans, self.text, config)
