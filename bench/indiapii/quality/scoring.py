"""Deterministic scoring: field-accuracy precision/recall/F1 for
extract_fields tasks against the corpus's own gold values, placeholder-leak
detection, and paired bootstrap confidence intervals for masked-vs-unmasked
deltas. No LLM calls in this module -- pure arithmetic, covered by ordinary
unit tests with no network/API key involved.
"""

from __future__ import annotations

import json
import random
import re
import statistics
from dataclasses import dataclass

_LEAK_RE = re.compile(r"<[A-Z_]+_\d+(?:_[0-9a-f]+)?>")

_WHITESPACE_RE = re.compile(r"\s+")

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


def has_leak(text: str) -> bool:
    return bool(_LEAK_RE.search(text))


def _normalize(value: str) -> str:
    return _WHITESPACE_RE.sub(" ", value.strip().lower())


@dataclass(frozen=True)
class FieldAccuracy:
    precision: float | None
    recall: float | None
    f1: float | None


def _parse_json_object(text: str) -> dict:
    match = _JSON_OBJECT_RE.search(text)
    if not match:
        return {}
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def score_fields(response_text: str, gold_fields: dict[str, str | None]) -> FieldAccuracy:
    """`gold_fields` is a field_name -> gold_value map (None where the source
    document never contained that field). A predicted value counts as a true
    positive only on an exact match (after whitespace/case normalization) --
    partial-credit matching isn't attempted here, mirroring the harness's
    own STRICT match mode for the analogous "did detection get the value
    right" question.

    recall is out of the fields the document actually had (gold_present);
    precision is out of the fields the model actually returned a value for
    (predicted_present) -- a wrong-but-present value costs both (it's
    neither a correct recall hit nor a precise prediction), while a
    hallucinated field the document never had only costs precision.
    predicted_present == 0 while gold_present is non-empty is scored as a
    precision of 0.0 (a real extraction failure), not None -- None is
    reserved for "there was nothing to score" (empty gold_fields, handled
    above)."""
    predicted = _parse_json_object(response_text)
    if not gold_fields:
        return FieldAccuracy(None, None, None)

    gold_present = [f for f, v in gold_fields.items() if v is not None]
    predicted_present = [f for f in gold_fields if predicted.get(f) not in (None, "", "null")]
    tp = sum(
        1
        for f in gold_present
        if f in predicted_present and _normalize(str(predicted[f])) == _normalize(gold_fields[f])
    )

    recall = tp / len(gold_present) if gold_present else None
    if predicted_present:
        precision = tp / len(predicted_present)
    else:
        precision = 0.0 if gold_present else None

    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / (precision + recall)
    return FieldAccuracy(precision, recall, f1)


def bootstrap_ci(
    values: list[float], n_resamples: int = 2000, seed: int = 0, alpha: float = 0.05
) -> tuple[float, float, float]:
    """Returns (mean, ci_low, ci_high) via a plain nonparametric bootstrap
    over `values` (e.g. per-task masked-minus-unmasked deltas). Deterministic
    per `seed`, so a report rebuilt from the same records reproduces the
    same interval."""
    if not values:
        return (0.0, 0.0, 0.0)
    mean = statistics.fmean(values)
    n = len(values)
    if n == 1:
        return (mean, mean, mean)

    rng = random.Random(seed)
    resample_means = []
    for _ in range(n_resamples):
        sample = [values[rng.randrange(n)] for _ in range(n)]
        resample_means.append(statistics.fmean(sample))
    resample_means.sort()
    lo_idx = int((alpha / 2) * n_resamples)
    hi_idx = int((1 - alpha / 2) * n_resamples) - 1
    return (
        mean,
        resample_means[max(0, lo_idx)],
        resample_means[min(n_resamples - 1, hi_idx)],
    )
