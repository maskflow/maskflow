from __future__ import annotations

import json
from importlib.metadata import version as dist_version
from pathlib import Path

import maskflow_pack_india  # noqa: F401 -- registers AADHAAR/PAN/etc. recognizers
import maskflow_pack_intl  # noqa: F401 -- registers EMAIL/etc. recognizers (MaskflowAdapter needs both)
import pytest
from maskflow_attest.run import AttestationRunError, run_attestation

_INSTALLED_INDIA_VERSION = dist_version("maskflow-pack-india")


def _write_fixture(path: Path) -> None:
    # PAN below is structurally well-formed (5 letters + 4 digits + 1
    # letter) but fabricated for this test, not a real allotted number --
    # synthetic fixture data only, per project policy. Offsets computed
    # rather than hand-counted, so a wording change can't silently misalign
    # start/end and produce a false tp=0.
    text1 = "Please update my PAN ABCPE1234F on file."
    pan_start = text1.index("ABCPE1234F")
    rows = [
        {
            "id": "fixture-1",
            "text": text1,
            "domain": "test",
            "lang": "en",
            "entities": [
                {
                    "start": pan_start,
                    "end": pan_start + len("ABCPE1234F"),
                    "label": "PAN",
                    "value_class": "positive",
                }
            ],
        },
        {
            "id": "fixture-2",
            "text": "No PII in this line at all.",
            "domain": "test",
            "lang": "en",
            "entities": [],
        },
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")


def test_run_attestation_end_to_end(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_fixture(corpus)

    doc = run_attestation(
        corpus_path=corpus,
        corpus_name="fixture-corpus",
        corpus_version="0.0.1",
        pack_name="maskflow-pack-india",
        pack_version=_INSTALLED_INDIA_VERSION,
        methodology="unit test fixture",
        reproduction_command="pytest",
    )

    assert doc.pack_name == "maskflow-pack-india"
    assert doc.pack_version == _INSTALLED_INDIA_VERSION
    assert doc.corpus_name == "fixture-corpus"
    assert doc.num_docs == 2
    assert doc.canonical_labels == ("PAN",)
    assert "PAN" in doc.metrics
    assert doc.metrics["PAN"]["strict"]["tp"] == 1
    assert doc.metrics["PAN"]["strict"]["fn"] == 0
    assert doc.methodology == "unit test fixture"
    assert doc.reproduction_command == "pytest"
    assert doc.issued_at
    assert doc.valid_until > doc.issued_at


def test_run_attestation_respects_limit(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_fixture(corpus)

    doc = run_attestation(
        corpus_path=corpus,
        corpus_name="fixture-corpus",
        corpus_version="0.0.1",
        pack_name="maskflow-pack-india",
        pack_version=_INSTALLED_INDIA_VERSION,
        methodology="unit test fixture",
        reproduction_command="pytest",
        limit=1,
    )
    assert doc.num_docs == 1


def test_run_attestation_rejects_version_mismatch(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_fixture(corpus)

    with pytest.raises(AttestationRunError, match="is installed, but this attestation is for"):
        run_attestation(
            corpus_path=corpus,
            corpus_name="fixture-corpus",
            corpus_version="0.0.1",
            pack_name="maskflow-pack-india",
            pack_version="999.999.999",
            methodology="unit test fixture",
            reproduction_command="pytest",
        )


def test_run_attestation_rejects_uninstalled_pack(tmp_path: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_fixture(corpus)

    with pytest.raises(AttestationRunError, match="is not installed"):
        run_attestation(
            corpus_path=corpus,
            corpus_name="fixture-corpus",
            corpus_version="0.0.1",
            pack_name="maskflow-pack-does-not-exist",
            pack_version="1.0.0",
            methodology="unit test fixture",
            reproduction_command="pytest",
        )


def test_run_attestation_rejects_empty_corpus(tmp_path: Path) -> None:
    corpus = tmp_path / "empty.jsonl"
    corpus.write_text("", encoding="utf-8")

    with pytest.raises(AttestationRunError, match="no documents found"):
        run_attestation(
            corpus_path=corpus,
            corpus_name="fixture-corpus",
            corpus_version="0.0.1",
            pack_name="maskflow-pack-india",
            pack_version=_INSTALLED_INDIA_VERSION,
            methodology="unit test fixture",
            reproduction_command="pytest",
        )
