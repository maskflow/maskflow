"""Streaming orchestration: pull ScanRecords from a Source, detect in a
worker pool (or in-process for --workers 1), fold results into a bounded
Aggregator, and checkpoint the source cursor + aggregator state so a killed
run resumes.

Ordering: results are consumed oldest-first from a bounded in-flight
window, so the checkpoint cursor only ever advances past records that are
fully aggregated -- a resume never drops or double-counts a record.
"""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import deque
from collections.abc import Callable
from concurrent.futures import Future, ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

from maskflow_core.config.schema import RootConfig

from .aggregate import Aggregator
from .checkpoint import Checkpoint, CheckpointMismatch, load_checkpoint, write_checkpoint
from .sources import ScanRecord, Source
from .worker import FindingSeed, init_worker, make_state, scan_batch, scan_with

_NER_SAMPLE_TARGET = 5_000
_CHECKPOINT_SECONDS = 10.0
_CHUNK = 512  # records per worker task -- amortises IPC without unbalancing the pool


@dataclass(frozen=True)
class PipelineConfig:
    root_config: RootConfig
    deep: bool = False
    ner_available: bool = True
    workers: int = 1
    max_records: int | None = None  # --sample
    ner_sample_target: int = _NER_SAMPLE_TARGET
    distinct_cap: int = 50_000
    excerpt_cap: int = 20
    checkpoint_path: Path | None = None
    checkpoint_every: int = 5_000
    restart: bool = False
    spec_fingerprint: str = ""
    detection_fingerprint: str = ""


@dataclass
class PipelineResult:
    aggregator: Aggregator
    resumed: bool
    stopped_early: bool  # hit --sample cap


def run_pipeline(
    source: Source,
    cfg: PipelineConfig,
    *,
    progress: Callable[[int, int], None] | None = None,
    total_estimate: int | None = None,
) -> PipelineResult:
    checkpoint = _resolve_checkpoint(cfg)
    resumed = checkpoint is not None

    if checkpoint is not None:
        agg = Aggregator.from_state(
            checkpoint.aggregator_state["agg"],
            distinct_cap=cfg.distinct_cap,
            excerpt_cap=cfg.excerpt_cap,
        )
        run_key = bytes.fromhex(checkpoint.aggregator_state["run_key"])
        scan_id = checkpoint.scan_id
        resume_cursor = checkpoint.cursor
    else:
        agg = Aggregator(distinct_cap=cfg.distinct_cap, excerpt_cap=cfg.excerpt_cap)
        run_key = secrets.token_bytes(32)
        scan_id = secrets.token_hex(8)
        resume_cursor = None

    sampler = _NerSampler(cfg, total_estimate, already_sampled=agg.ner_sample_records)
    ctx = _RunContext(source, cfg, agg, run_key, scan_id, sampler, progress)

    stopped_early = _drive(ctx, resume_cursor)

    _write(ctx, cursor=ctx.last_cursor)  # final checkpoint
    return PipelineResult(aggregator=agg, resumed=resumed, stopped_early=stopped_early)


# --------------------------------------------------------------------------


@dataclass
class _RunContext:
    source: Source
    cfg: PipelineConfig
    agg: Aggregator
    run_key: bytes
    scan_id: str
    sampler: _NerSampler
    progress: Callable[[int, int], None] | None
    last_cursor: str | None = None
    _last_ckpt_time: float = 0.0
    _since_ckpt: int = 0


def _drive(ctx: _RunContext, resume_cursor: str | None) -> bool:
    records = ctx.source.records(resume_cursor=resume_cursor)
    if ctx.cfg.workers > 1:
        return _drive_pool(ctx, records)
    return _drive_inline(ctx, records)


def _drive_inline(ctx: _RunContext, records) -> bool:
    state = make_state(ctx.cfg.root_config, ctx.cfg.deep, ctx.run_key)
    for record in records:
        in_ner = ctx.sampler.take(record.id)
        seeds = scan_with(state, record.id, record.text, in_ner)
        _consume(ctx, record, seeds, in_ner)
        if _hit_cap(ctx):
            return True
    return False


def _drive_pool(ctx: _RunContext, records) -> bool:
    # Submit CHUNKS of records, not one task per record -- the per-task
    # pickle/IPC cost dominates otherwise. Keep a bounded number of chunks
    # in flight and consume them oldest-first so the checkpoint watermark
    # only advances past fully-aggregated records.
    max_chunks = ctx.cfg.workers * 3
    inflight: deque[tuple[list[tuple[ScanRecord, bool]], Future]] = deque()

    with ProcessPoolExecutor(
        max_workers=ctx.cfg.workers,
        initializer=init_worker,
        initargs=(ctx.cfg.root_config, ctx.cfg.deep, ctx.run_key),
    ) as pool:
        for chunk in _chunked(records, ctx.sampler, _CHUNK):
            payload = [(r.id, r.text, in_ner) for r, in_ner in chunk]
            inflight.append((chunk, pool.submit(scan_batch, payload)))
            if len(inflight) >= max_chunks and _flush_chunk(ctx, inflight):
                return True
        while inflight:
            if _flush_chunk(ctx, inflight):
                return True
    return False


def _chunked(records, sampler: _NerSampler, size: int):
    batch: list[tuple[ScanRecord, bool]] = []
    for record in records:
        batch.append((record, sampler.take(record.id)))
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch


def _flush_chunk(ctx: _RunContext, inflight: deque) -> bool:
    chunk, fut = inflight.popleft()
    seeds_by_record: list[list[FindingSeed]] = fut.result()
    for (record, in_ner), seeds in zip(chunk, seeds_by_record, strict=True):
        _consume(ctx, record, seeds, in_ner)
        if _hit_cap(ctx):
            return True
    return False


def _consume(ctx: _RunContext, record: ScanRecord, seeds: list[FindingSeed], in_ner: bool) -> None:
    ctx.agg.add(
        seeds,
        provider=record.provider,
        service=record.service,
        timestamp=record.timestamp,
        in_ner_sample=in_ner and not ctx.cfg.deep,
    )
    ctx.last_cursor = ctx.source.cursor_after(record)
    ctx._since_ckpt += 1
    if ctx.progress is not None:
        ctx.progress(ctx.agg.records_processed, ctx.agg.total_measured)
    _maybe_checkpoint(ctx)


def _hit_cap(ctx: _RunContext) -> bool:
    return ctx.cfg.max_records is not None and ctx.agg.records_processed >= ctx.cfg.max_records


def _maybe_checkpoint(ctx: _RunContext) -> None:
    if ctx.cfg.checkpoint_path is None:
        return
    now = time.monotonic()
    if (
        ctx._since_ckpt >= ctx.cfg.checkpoint_every
        or (now - ctx._last_ckpt_time) >= _CHECKPOINT_SECONDS
    ):
        _write(ctx, cursor=ctx.last_cursor)
        ctx._since_ckpt = 0
        ctx._last_ckpt_time = now


def _write(ctx: _RunContext, *, cursor: str | None) -> None:
    if ctx.cfg.checkpoint_path is None:
        return
    write_checkpoint(
        ctx.cfg.checkpoint_path,
        Checkpoint(
            scan_id=ctx.scan_id,
            spec_fingerprint=ctx.cfg.spec_fingerprint,
            detection_fingerprint=ctx.cfg.detection_fingerprint,
            cursor=cursor,
            aggregator_state={"agg": ctx.agg.to_state(), "run_key": ctx.run_key.hex()},
        ),
    )


def _resolve_checkpoint(cfg: PipelineConfig) -> Checkpoint | None:
    if cfg.checkpoint_path is None or cfg.restart:
        return None
    return load_checkpoint(
        cfg.checkpoint_path,
        spec_fingerprint=cfg.spec_fingerprint,
        detection_fingerprint=cfg.detection_fingerprint,
    )


class _NerSampler:
    """Deterministic, resume-stable choice of which records get the (slow)
    NER pass. A record's fate depends only on its id, so a resumed run keeps
    the same sample."""

    def __init__(
        self, cfg: PipelineConfig, total_estimate: int | None, *, already_sampled: int
    ) -> None:
        self._deep = cfg.deep
        self._enabled = cfg.deep or cfg.ner_available
        self._target = cfg.ner_sample_target
        self._already = already_sampled
        if total_estimate and total_estimate > 0:
            self._every = max(1, round(total_estimate / max(cfg.ner_sample_target, 1)))
            self._blind = False
        else:
            self._every = 20  # ~5% until the target is met
            self._blind = True

    def take(self, record_id: str) -> bool:
        if self._deep:
            return True
        if not self._enabled:
            return False
        if self._blind and self._already >= self._target:
            return False
        if _stable_hash(record_id) % self._every == 0:
            self._already += 1
            return True
        return False


def _stable_hash(text: str) -> int:
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest(), "big")


__all__ = ["PipelineConfig", "PipelineResult", "run_pipeline", "CheckpointMismatch"]
