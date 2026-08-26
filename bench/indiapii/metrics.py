"""Generic precision/recall/F1 computation against a pack's fixture samples.

Not tied to PERSON_NAME/INDIAN_ADDRESS specifically -- any PII pack's
POSITIVE_SAMPLES (a Sample-shaped list: text + expected (PIIType, value)
pairs), plain NEGATIVE_SAMPLES (str, expect zero findings), and an optional
HARD_NEGATIVE_SAMPLES bucket (str, structurally/lexically similar to a real
positive but must still produce zero findings for `target_types`) can be
scored with evaluate(). Built for the work order's four-layer PERSON_NAME
(Indian) / INDIAN_ADDRESS build (report.py in this directory), reused
as-is for each of L1-L4's report rather than rewritten per layer.

Never prints or logs the matched span text itself -- report.py's table is
counts and ratios only (CLAUDE.md rule 1).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


class SampleLike(Protocol):
    text: str
    expected: list[tuple[PIIType, str]]


@dataclass
class PRFResult:
    entity_type: PIIType
    tp: int = 0
    fp: int = 0
    fn: int = 0

    @property
    def precision(self) -> float | None:
        denom = self.tp + self.fp
        return self.tp / denom if denom else None

    @property
    def recall(self) -> float | None:
        denom = self.tp + self.fn
        return self.tp / denom if denom else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if not p or not r or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)


def evaluate(
    positive_samples: Sequence[SampleLike],
    negative_samples: Sequence[str],
    hard_negative_samples: Sequence[str],
    target_types: Sequence[PIIType],
) -> dict[PIIType, PRFResult]:
    """Score `detect()` against fixtures, restricted to `target_types` so a
    fixture built for one recognizer under active development isn't
    penalized/credited for unrelated recognizers' findings on the same text.
    """
    results: dict[PIIType, PRFResult] = {t: PRFResult(entity_type=t) for t in target_types}
    target_set = set(target_types)

    for sample in positive_samples:
        found = {
            (s.entity_type, s.text) for s in detect(sample.text) if s.entity_type in target_set
        }
        expected = {pair for pair in sample.expected if pair[0] in target_set}
        for pair in expected:
            results[pair[0]].tp += 1 if pair in found else 0
            if pair not in found:
                results[pair[0]].fn += 1
        for pair in found - expected:
            results[pair[0]].fp += 1

    for text in (*negative_samples, *hard_negative_samples):
        for s in detect(text):
            if s.entity_type in target_set:
                results[s.entity_type].fp += 1

    return results


@dataclass
class LayerReport:
    layer: str
    results: dict[PIIType, PRFResult] = field(default_factory=dict)

    def render(self) -> str:
        header = (
            f"{'entity_type':<16}{'precision':>10}{'recall':>10}{'f1':>10}"
            f"{'tp':>6}{'fp':>6}{'fn':>6}"
        )
        lines = [f"-- {self.layer} --", header, "-" * len(header)]
        for entity_type, r in self.results.items():
            p = f"{r.precision:.2%}" if r.precision is not None else "n/a"
            rec = f"{r.recall:.2%}" if r.recall is not None else "n/a"
            f1 = f"{r.f1:.2%}" if r.f1 is not None else "n/a"
            lines.append(f"{entity_type:<16}{p:>10}{rec:>10}{f1:>10}{r.tp:>6}{r.fp:>6}{r.fn:>6}")
        return "\n".join(lines)
