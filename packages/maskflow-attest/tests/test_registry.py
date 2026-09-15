from __future__ import annotations

from pathlib import Path

from maskflow_attest.document import AttestationDocument
from maskflow_attest.registry import AttestationRecord, AttestationRegistry


def _record(pack_version: str, issued_at: str, *, revoked: bool = False) -> AttestationRecord:
    doc = AttestationDocument(
        pack_name="maskflow-pack-india",
        pack_version=pack_version,
        corpus_name="indiapii-v1.0",
        corpus_version="1.0",
        num_docs=10,
        canonical_labels=("PAN",),
        metrics={},
        methodology="test",
        reproduction_command="maskflow-attest run ...",
        engine_version="0.8.0",
        issued_at=issued_at,
        valid_until="2099-01-01T00:00:00Z",
    )
    return AttestationRecord(
        document=doc, signature="ed25519:" + "aa" * 64, signer_public_key="bb" * 32, revoked=revoked
    )


def test_add_and_latest() -> None:
    reg = AttestationRegistry()
    older = _record("0.5.0", "2026-01-01T00:00:00Z")
    newer = _record("0.5.1", "2026-02-01T00:00:00Z")
    reg.add(older)
    reg.add(newer)

    assert reg.latest("maskflow-pack-india") is newer
    assert reg.latest("maskflow-pack-india", "0.5.0") is older
    assert reg.latest("maskflow-pack-india", "9.9.9") is None
    assert reg.latest("some-other-pack") is None


def test_latest_ignores_revoked() -> None:
    reg = AttestationRegistry()
    reg.add(_record("0.5.1", "2026-02-01T00:00:00Z", revoked=True))
    assert reg.latest("maskflow-pack-india") is None


def test_revoke_flips_flag_and_returns_count() -> None:
    reg = AttestationRegistry()
    reg.add(_record("0.5.1", "2026-02-01T00:00:00Z"))
    reg.add(_record("0.5.1", "2026-03-01T00:00:00Z"))
    reg.add(_record("0.5.0", "2026-01-01T00:00:00Z"))  # different version, untouched

    changed = reg.revoke("maskflow-pack-india", "0.5.1", reason="dataset bug found")
    assert changed == 2
    assert all(r.revoked for r in reg.records if r.document.pack_version == "0.5.1")
    assert all(
        r.revoked_reason == "dataset bug found"
        for r in reg.records
        if r.document.pack_version == "0.5.1"
    )
    assert not any(r.revoked for r in reg.records if r.document.pack_version == "0.5.0")

    # already-revoked records aren't touched again / double-counted
    assert reg.revoke("maskflow-pack-india", "0.5.1", reason="again") == 0


def test_revoke_no_match_returns_zero() -> None:
    reg = AttestationRegistry()
    assert reg.revoke("nope", "1.0.0", reason="x") == 0


def test_save_and_load_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "registry.jsonl"
    reg = AttestationRegistry()
    reg.add(_record("0.5.0", "2026-01-01T00:00:00Z"))
    reg.add(_record("0.5.1", "2026-02-01T00:00:00Z"))
    reg.save(path)

    loaded = AttestationRegistry.load(path)
    assert len(loaded.records) == 2
    assert {r.document.pack_version for r in loaded.records} == {"0.5.0", "0.5.1"}


def test_load_missing_file_is_empty(tmp_path: Path) -> None:
    reg = AttestationRegistry.load(tmp_path / "does-not-exist.jsonl")
    assert reg.records == ()
