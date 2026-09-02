"""The per-record detection unit. Pure and I/O-free so it can run in a
worker process; crucially it returns only `FindingSeed`s -- a typed
placeholder, a non-reversible fingerprint, and an already-masked excerpt --
so a record's raw text never crosses back to the parent process or reaches
the aggregator (CLAUDE.md rule 1).
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from maskflow_core.config.engine import compile_config
from maskflow_core.config.schema import RootConfig
from maskflow_core.detection import DEFAULT_MIN_CONFIDENCE, detect, detect_patterns_only
from maskflow_core.entities import Span

_EXCERPT_CONTEXT = 64  # chars of surrounding text kept on each side


@dataclass(frozen=True)
class FindingSeed:
    entity_type: str
    placeholder: str  # canonical "<TYPE_1>" for display
    value_fingerprint: str  # HMAC(run_key, value) -- distinct count only
    masked_excerpt: str  # "...<TYPE_1> in context...", never a raw value
    from_ner: bool  # True => counts toward the extrapolated estimate


@dataclass
class _WorkerState:
    detect_kwargs: dict
    deep: bool
    run_key: bytes


_STATE: _WorkerState | None = None


def init_worker(root_config: RootConfig, deep: bool, run_key: bytes) -> None:
    """ProcessPoolExecutor initializer: register the recognizer packs in
    this child process and compile the config once."""
    import maskflow_pack_india  # noqa: F401  -- side-effect: register India recognizers
    import maskflow_pack_intl  # noqa: F401  -- side-effect: register intl recognizers

    global _STATE
    compiled = compile_config(root_config)
    _STATE = _WorkerState(dict(compiled.detect_kwargs()), deep, run_key)


def make_state(root_config: RootConfig, deep: bool, run_key: bytes) -> _WorkerState:
    """In-process (`--workers 1`) equivalent of init_worker."""
    compiled = compile_config(root_config)
    return _WorkerState(dict(compiled.detect_kwargs()), deep, run_key)


def scan_batch(items: list[tuple[str, str, bool]]) -> list[list[FindingSeed]]:
    """Pool entry point: one call per chunk of records (not per record) so
    the per-task pickle/IPC cost is amortised over the whole chunk. Results
    line up positionally with `items`. Uses the module-global state set by
    init_worker."""
    assert _STATE is not None, "init_worker was not called"
    return [scan_with(_STATE, rid, text, in_ner) for rid, text, in_ner in items]


def scan_with(
    state: _WorkerState, record_id: str, text: str, in_ner_sample: bool
) -> list[FindingSeed]:
    use_ner = state.deep or in_ner_sample
    if use_ner:
        spans = detect(text, min_confidence=DEFAULT_MIN_CONFIDENCE, **state.detect_kwargs)
    else:
        # detect_patterns_only() accepts only the three detect kwargs that
        # make sense without an NER pass -- exclusion_values /
        # exclusion_patterns are applied by detect() after resolution and
        # are dropped here (they still apply on every --deep / sampled
        # record, and to the excerpt, which is built from these spans).
        spans = detect_patterns_only(
            text,
            min_confidence=DEFAULT_MIN_CONFIDENCE,
            per_entity_threshold=state.detect_kwargs["per_entity_threshold"],
            disabled_types=state.detect_kwargs["disabled_types"],
            extra_patterns=state.detect_kwargs["extra_patterns"],
        )
        spans = _apply_exclusions(spans, state)
    spans = sorted(spans, key=lambda s: s.start)

    seeds: list[FindingSeed] = []
    for span in spans:
        from_ner = span.recognizer.startswith("ner:")
        seeds.append(
            FindingSeed(
                entity_type=str(span.entity_type),
                placeholder=f"<{span.entity_type}_1>",
                value_fingerprint=_fingerprint(state.run_key, span.text),
                masked_excerpt=_excerpt(text, span, spans),
                from_ner=from_ner and not state.deep,
            )
        )
    return seeds


def ner_available() -> tuple[bool, str]:
    """Whether the NER pass can run in this environment (spaCy + model
    present). Cheap: reuses core's lru_cached loader. Returns (ok, reason)."""
    import maskflow_pack_india  # noqa: F401
    import maskflow_pack_intl  # noqa: F401

    try:
        from maskflow_core.ner import _get_nlp
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    try:
        nlp = _get_nlp()
    except OSError as exc:
        return False, str(exc)
    if nlp is None:
        return False, "spaCy is not installed (pip install maskflow-core[nlp])"
    return True, ""


def _apply_exclusions(spans: list[Span], state: _WorkerState) -> list[Span]:
    values = state.detect_kwargs.get("exclusion_values") or frozenset()
    patterns = state.detect_kwargs.get("exclusion_patterns") or ()
    if not values and not patterns:
        return spans
    return [
        s for s in spans if s.text not in values and not any(p.search(s.text) for p in patterns)
    ]


def _fingerprint(run_key: bytes, value: str) -> str:
    digest = hmac.new(run_key, value.encode("utf-8", "surrogatepass"), hashlib.sha256)
    return digest.hexdigest()[:16]


def _excerpt(text: str, target: Span, all_spans: list[Span]) -> str:
    """A window of context around `target` in which EVERY detected span --
    the target and any neighbour caught in the same pass -- is replaced by
    its typed placeholder. Reuses the spans already detected for this
    record, so it adds no detection cost and is exactly as thorough as the
    detection that produced the finding (the fuzz gate relies on this)."""
    left = max(0, target.start - _EXCERPT_CONTEXT)
    right = min(len(text), target.end + _EXCERPT_CONTEXT)

    covering = sorted(
        (s for s in all_spans if s.start < right and s.end > left),
        key=lambda s: s.start,
    )
    pieces: list[str] = []
    cursor = left
    for i, s in enumerate(covering, start=1):
        seg_start = max(s.start, left)
        if seg_start > cursor:
            pieces.append(text[cursor:seg_start])
        pieces.append(f"<{s.entity_type}_{i}>")
        cursor = min(s.end, right)
    if cursor < right:
        pieces.append(text[cursor:right])

    body = "".join(pieces).replace("\n", " ").strip()
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return (prefix + body + suffix)[:400]
