"""`maskflow scan` -- the Typer command. Thin: parse args into a
SourceSpec + PipelineConfig, run the pipeline, render the report.
"""

from __future__ import annotations

import dataclasses
import hashlib
import os
import sys
import time
from datetime import datetime
from importlib import metadata
from pathlib import Path

import typer
from maskflow_core.config.resolve import ConfigResolutionError, resolve_config
from maskflow_core.config.schema import RootConfig

from . import TRUST_LINE
from .checkpoint import CheckpointMismatch
from .pipeline import PipelineConfig, run_pipeline
from .report import build_summary, render
from .sources import SOURCE_NAMES, get_source
from .sources.base import SourceError
from .spec import DetectionSpec, SourceSpec
from .worker import ner_available

_DEFAULT_WORKERS = min(8, os.cpu_count() or 4)
_API_SOURCES = {"langfuse", "helicone", "langsmith"}

# Module-level singletons for the options ruff's B008 flags (list / Path
# defaults) -- same pattern as commands/explain_cmd.py's _CONFIG_OPTION.
_FIELD_OPT = typer.Option(
    [], "--field", help="JSON path to text, e.g. messages[].content (repeatable)."
)
_COLUMNS_OPT = typer.Option(
    [], "--columns", help="CSV / postgres text columns, comma-separated (repeatable)."
)
_OUT_OPT = typer.Option(None, "--out", "-o", help="Output file (default: by format).")
_CHECKPOINT_OPT = typer.Option(None, "--checkpoint", help="Resumable checkpoint file.")
_CONFIG_OPT = typer.Option(None, "--config", help="Explicit .maskflowrc path.")
_SET_OPT = typer.Option([], "--set", help="Override a resolved config value (repeatable).")


def scan(  # noqa: PLR0913 - a CLI surface, each option is deliberate
    source: str = typer.Argument(..., metavar="SOURCE", help=f"One of: {', '.join(SOURCE_NAMES)}"),
    target: str = typer.Argument(
        "", help="Path, s3:// URI, or connection string. Omit for API sources."
    ),
    field: list[str] = _FIELD_OPT,
    columns: list[str] = _COLUMNS_OPT,
    query: str | None = typer.Option(None, "--query", help="postgres: SELECT ... ORDER BY <key>."),
    provider: str | None = typer.Option(None, "--provider", help="Constant provider label."),
    provider_field: str | None = typer.Option(None, "--provider-field"),
    service_field: str | None = typer.Option(None, "--service-field"),
    timestamp_field: str | None = typer.Option(None, "--timestamp-field"),
    role_field: str | None = typer.Option(None, "--role-field"),
    since: str | None = typer.Option(None, "--since", help="ISO date/datetime lower bound."),
    until: str | None = typer.Option(None, "--until", help="ISO date/datetime upper bound."),
    out: Path | None = _OUT_OPT,
    fmt: str = typer.Option("html", "--format", help="html | json | csv."),
    sample: int | None = typer.Option(None, "--sample", help="Process at most N records."),
    deep: bool = typer.Option(False, "--deep", help="Run full NER over every record (slow)."),
    workers: int = typer.Option(_DEFAULT_WORKERS, "--workers", min=1),
    checkpoint: Path | None = _CHECKPOINT_OPT,
    restart: bool = typer.Option(False, "--restart", help="Ignore an existing checkpoint."),
    distinct_cap: int = typer.Option(50_000, "--distinct-cap", min=1),
    excerpt_cap: int = typer.Option(20, "--excerpt-cap", min=0),
    checkpoint_every: int = typer.Option(5_000, "--checkpoint-every", min=1),
    ner_sample: int = typer.Option(5_000, "--ner-sample", min=1, help="Records sampled for NER."),
    config: Path | None = _CONFIG_OPT,
    set_: list[str] = _SET_OPT,
    quiet: bool = typer.Option(False, "--quiet"),
) -> None:
    """Scan historical LLM traffic for PII that already reached a provider,
    and write a self-contained report.

    Runs entirely locally. Nothing is transmitted -- API sources only READ
    from your own observability account.
    """
    if fmt not in ("html", "json", "csv"):
        _die(f"--format must be html, json, or csv (got {fmt!r})")
    if source not in SOURCE_NAMES:
        _die(f"unknown SOURCE {source!r}; choose one of: {', '.join(SOURCE_NAMES)}")

    root_config, config_fp = _resolve(config, set_)

    spec = SourceSpec(
        kind=source,
        target=target,
        fields=tuple(field),
        columns=tuple(columns),
        query=query,
        provider=provider,
        provider_field=provider_field,
        service_field=service_field,
        timestamp_field=timestamp_field,
        role_field=role_field,
        since=_parse_dt(since, "--since"),
        until=_parse_dt(until, "--until"),
    )
    detection = DetectionSpec(
        deep=deep,
        config_fingerprint=config_fp,
        core_version=_version("maskflow-core"),
    )

    _startup(spec, quiet)

    ner_ok, ner_reason = ner_available()
    if deep and not ner_ok:
        _die(
            f"--deep needs the NER pass, which is unavailable: {ner_reason}",
            code=2,
        )
    if not ner_ok and not quiet:
        typer.echo(
            f"note: NER pass unavailable ({ner_reason}) -- bare names and "
            "addresses will not be counted. Pattern-based PII is unaffected.",
            err=True,
        )

    try:
        src = get_source(spec)
        pf = src.preflight()
        if not pf.ok:
            _die(pf.reason, code=2)
        estimate = src.estimate()
    except SourceError as exc:
        _die(str(exc), code=2)

    out_path = out or Path(f"maskflow-scan-report.{fmt}")
    pcfg = PipelineConfig(
        root_config=root_config,
        deep=deep,
        ner_available=ner_ok,
        workers=workers,
        max_records=sample,
        ner_sample_target=ner_sample,
        distinct_cap=distinct_cap,
        excerpt_cap=excerpt_cap,
        checkpoint_path=checkpoint,
        checkpoint_every=checkpoint_every,
        restart=restart,
        spec_fingerprint=spec.fingerprint(),
        detection_fingerprint=detection.fingerprint(),
    )

    progress = None if quiet else _StderrProgress(estimate.total_records)
    started = time.monotonic()
    try:
        result = run_pipeline(src, pcfg, progress=progress, total_estimate=estimate.total_records)
    except CheckpointMismatch as exc:
        _die(str(exc), code=2)
    except SourceError as exc:
        _die(str(exc), code=2)
    if progress is not None:
        progress.done()

    summary = build_summary(
        result.aggregator,
        source_kind=spec.kind,
        source_target=spec.target or spec.kind,
        deep=deep,
        ner_available=ner_ok,
        generated_at=datetime.now().astimezone(),
        detector_versions=_detector_versions(),
        corpus_fingerprint=_corpus_fingerprint(
            spec, detection, result.aggregator.records_processed
        ),
        thresholds_note=_thresholds_note(config),
    )

    rendered = render(summary, fmt)
    if str(out_path) == "-":
        sys.stdout.write(rendered)
    else:
        out_path.write_text(rendered, encoding="utf-8")

    if not quiet:
        elapsed = time.monotonic() - started
        resumed = " (resumed)" if result.resumed else ""
        capped = " -- stopped at --sample cap" if result.stopped_early else ""
        records = result.aggregator.records_processed
        typer.echo(
            f"\nScanned {records:,} records in {elapsed:.1f}s{resumed}{capped}.\n"
            f"{summary.headline_total:,} PII instances reached providers "
            f"({summary.headline_distinct:,} distinct).\n"
            f"Report: {out_path}",
            err=True,
        )


# --------------------------------------------------------------------------


def _resolve(config: Path | None, sets: list[str]) -> tuple[RootConfig, str]:
    try:
        resolved = resolve_config(config_path_override=config, cli_sets=list(sets))
    except ConfigResolutionError as exc:
        for line in str(exc).splitlines():
            typer.echo(line, err=True)
        raise typer.Exit(code=1) from exc
    blob = repr(dataclasses.asdict(resolved.config)).encode()
    return resolved.config, hashlib.sha256(blob).hexdigest()[:16]


def _startup(spec: SourceSpec, quiet: bool) -> None:
    if quiet:
        return
    typer.echo(f"maskflow scan · {TRUST_LINE}", err=True)
    if spec.kind in _API_SOURCES:
        typer.echo(
            f"Reading from your {spec.kind} account over its API; no scan data is sent anywhere.",
            err=True,
        )


def _parse_dt(value: str | None, flag: str) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        _die(f"{flag}: not an ISO date/datetime: {value!r}")
        return None  # unreachable


def _version(dist: str) -> str:
    try:
        return metadata.version(dist)
    except metadata.PackageNotFoundError:
        return "unknown"


def _detector_versions() -> dict[str, str]:
    versions = {name: _version(name) for name in ("maskflow-core", "maskflow-cli")}
    for dist in metadata.distributions():
        name = dist.metadata.get("Name")
        if name and name.startswith("maskflow-pack-"):
            versions[name] = _version(name)
    try:
        import spacy

        versions["spaCy"] = spacy.__version__
    except ImportError:
        versions["spaCy"] = "not installed (NER pass disabled)"
    return versions


def _corpus_fingerprint(spec: SourceSpec, detection: DetectionSpec, records: int) -> str:
    blob = f"{spec.fingerprint()}|{detection.fingerprint()}|{records}"
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


def _thresholds_note(config: Path | None) -> str:
    if config is not None:
        return f"Detection thresholds and exclusions from {config}."
    return (
        "Detection used MaskFlow's default per-entity thresholds and any "
        "discovered .maskflowrc; see `maskflow doctor` for the active configuration."
    )


def _die(message: str, code: int = 1) -> None:
    typer.echo(f"error: {message}", err=True)
    raise typer.Exit(code=code)


class _StderrProgress:
    def __init__(self, total: int | None) -> None:
        self._total = total
        self._last = 0.0

    def __call__(self, processed: int, findings: int) -> None:
        now = time.monotonic()
        if now - self._last < 1.0:
            return
        self._last = now
        pct = f" ({100 * processed / self._total:.0f}%)" if self._total else ""
        sys.stderr.write(f"\r  {processed:,} records{pct} · {findings:,} PII instances   ")
        sys.stderr.flush()

    def done(self) -> None:
        sys.stderr.write("\r" + " " * 60 + "\r")
        sys.stderr.flush()
