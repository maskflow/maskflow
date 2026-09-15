"""Runs MaskFlow's own detector against a labelled corpus and packages the
result as an *unsigned* :class:`~maskflow_attest.document.AttestationDocument`
-- ``signing.py`` and the CLI's ``run`` command handle signing it.

Corpus-agnostic on purpose: nothing here knows about IndiaPII specifically.
The corpus path is a parameter, reused from ``maskflow-bench`` (the same
corpus-agnostic scoring core ``maskflow bench --my-data`` and
``bench/indiapii/harness`` already share) rather than re-derived. See
``docs/attestations.md`` for the concrete IndiaPII-Bench reproduction
command this powers.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _dist_version
from pathlib import Path

from .document import AttestationDocument

_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


class AttestationRunError(RuntimeError):
    """The environment can't actually produce the attestation being asked
    for -- e.g. the pack under attestation isn't installed. An attestation
    only ever describes what was actually run; it is never allowed to fall
    back to "whatever happens to be installed" silently."""


def _engine_version() -> str:
    try:
        return _dist_version("maskflow-core")
    except PackageNotFoundError:  # pragma: no cover - core is always installed here
        return "unknown"


def _pack_installed_version(pack_name: str) -> str:
    try:
        return _dist_version(pack_name)
    except PackageNotFoundError as exc:
        raise AttestationRunError(
            f"{pack_name!r} is not installed in this environment -- an attestation can "
            "only describe a pack version that was actually run, never an assumed one. "
            f"Install it first: pip install '{pack_name}==<version>'"
        ) from exc


def run_attestation(
    *,
    corpus_path: Path,
    corpus_name: str,
    corpus_version: str,
    pack_name: str,
    pack_version: str,
    methodology: str,
    reproduction_command: str,
    valid_days: int = 90,
    limit: int | None = None,
) -> AttestationDocument:
    """Loads ``corpus_path``, runs MaskFlow's detector once, scores
    strict-span and partial-overlap precision/recall/F1 per entity type,
    and returns an unsigned document.

    Raises :class:`AttestationRunError` if ``pack_name`` isn't actually
    installed, or its installed version doesn't match ``pack_version`` --
    the whole point of an attestation is describing exactly what ran, never
    a claim about a version that wasn't actually measured.
    """
    installed = _pack_installed_version(pack_name)
    if installed != pack_version:
        raise AttestationRunError(
            f"{pack_name} {installed} is installed, but this attestation is for "
            f"{pack_version} -- install the exact version first: "
            f"pip install '{pack_name}=={pack_version}'"
        )

    # Imported here, not at module scope: verify()/registry management
    # (and the CLI's `verify`/`registry` subcommands) must work without
    # maskflow-bench -- or the pack under attestation -- installed at all.
    from maskflow_bench.adapters.maskflow_adapter import MaskflowAdapter
    from maskflow_bench.corpus import load_corpus
    from maskflow_bench.labels import canonical_labels, identity_map
    from maskflow_bench.matching import PRFResult
    from maskflow_bench.runner import run_adapter

    def _prf(r: PRFResult) -> dict[str, float | int | None]:
        return {
            "precision": r.precision,
            "recall": r.recall,
            "f1": r.f1,
            "tp": r.tp,
            "fp": r.fp,
            "fn": r.fn,
        }

    docs = load_corpus(corpus_path, limit=limit)
    if not docs:
        raise AttestationRunError(f"{corpus_path}: no documents found -- is the file empty?")
    labels = canonical_labels(docs)
    entry = (MaskflowAdapter(), identity_map(labels))
    result = run_adapter(entry, docs, labels)

    metrics = {
        label: {"strict": _prf(result.strict[label]), "partial": _prf(result.partial[label])}
        for label in labels
    }

    issued = datetime.now(timezone.utc)
    return AttestationDocument(
        pack_name=pack_name,
        pack_version=pack_version,
        corpus_name=corpus_name,
        corpus_version=corpus_version,
        num_docs=len(docs),
        canonical_labels=labels,
        metrics=metrics,
        methodology=methodology,
        reproduction_command=reproduction_command,
        engine_version=_engine_version(),
        issued_at=issued.strftime(_TS_FORMAT),
        valid_until=(issued + timedelta(days=valid_days)).strftime(_TS_FORMAT),
    )
