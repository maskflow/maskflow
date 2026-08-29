"""Strict-span and partial-overlap precision/recall/F1 scoring.

Gold spans for a Document are `Document.gold` only (`value_class ==
"positive"`) -- `Document.decoys` (hard-negative spans) are never gold, but
a prediction landing on one is still scored: after label-mapping (see
labels.py), any predicted span left unmatched to a gold span -- whether it
overlaps background text or a decoy -- counts as a false positive for its
mapped canonical type. That's what makes the corpus's hard negatives (e.g.
a naive-regex hit on PAN_SHAPED_INVOICE_NO) actually cost precision.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .corpus import Document

RawSpan = tuple[int, int, str]  # (start, end, raw_label) as an adapter emits it
GoldSpan = tuple[int, int, str]  # (start, end, canonical_label)


class MatchMode(str, Enum):
    STRICT = "strict"
    PARTIAL = "partial"


@dataclass
class PRFResult:
    entity_type: str
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


def _mapped_predictions(
    predictions: list[RawSpan], label_map: dict[str, str]
) -> list[tuple[int, int, str]]:
    """Drops any prediction whose raw label has no canonical mapping --
    never scored as a false positive against an unrelated type."""
    out = []
    for start, end, raw_label in predictions:
        canonical = label_map.get(raw_label)
        if canonical is not None:
            out.append((start, end, canonical))
    return out


def _score_document(
    gold: tuple[GoldSpan, ...],
    predictions: list[tuple[int, int, str]],
    mode: MatchMode,
    results: dict[str, PRFResult],
) -> None:
    unclaimed_pred = list(range(len(predictions)))

    def overlaps(a: tuple[int, int, str], b: tuple[int, int, str]) -> bool:
        return max(a[0], b[0]) < min(a[1], b[1])

    for g_start, g_end, g_label in gold:
        gold_span = (g_start, g_end, g_label)
        match_idx = None
        for idx in unclaimed_pred:
            p_start, p_end, p_label = predictions[idx]
            if p_label != g_label:
                continue
            if mode is MatchMode.STRICT:
                hit = (p_start, p_end) == (g_start, g_end)
            else:
                hit = overlaps((p_start, p_end, p_label), gold_span)
            if hit:
                match_idx = idx
                break
        if match_idx is not None:
            results[g_label].tp += 1
            unclaimed_pred.remove(match_idx)
        else:
            results[g_label].fn += 1

    for idx in unclaimed_pred:
        _p_start, _p_end, p_label = predictions[idx]
        if p_label in results:
            results[p_label].fp += 1


def evaluate(
    docs: list[Document],
    predictions_by_doc: list[list[RawSpan]],
    label_map: dict[str, str],
    canonical_labels: tuple[str, ...],
    mode: MatchMode,
) -> dict[str, PRFResult]:
    """Scores each doc's already-computed raw predictions (see runner.py,
    which owns calling detect() so it can time/guard each call once and
    reuse the same predictions for both matching modes) against
    `doc.gold`, after mapping raw labels through `label_map`. Restricted to
    `canonical_labels` so an adapter's detections of types outside this
    corpus's taxonomy never enter the tally at all.
    """
    results: dict[str, PRFResult] = {t: PRFResult(entity_type=t) for t in canonical_labels}
    for doc, raw_predictions in zip(docs, predictions_by_doc, strict=True):
        predictions = _mapped_predictions(raw_predictions, label_map)
        predictions = [p for p in predictions if p[2] in results]
        gold = tuple(g for g in doc.gold if g[2] in results)
        _score_document(gold, predictions, mode, results)
    return results
