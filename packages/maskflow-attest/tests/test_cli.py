from __future__ import annotations

import json
from importlib.metadata import version as dist_version
from pathlib import Path

import maskflow_pack_india  # noqa: F401 -- registers AADHAAR/PAN/etc. recognizers
import maskflow_pack_intl  # noqa: F401 -- registers EMAIL/etc. recognizers (MaskflowAdapter needs both)
from maskflow_attest.cli import app
from typer.testing import CliRunner

runner = CliRunner()
_INSTALLED_INDIA_VERSION = dist_version("maskflow-pack-india")


def _write_fixture(path: Path) -> None:
    # PAN below is structurally well-formed but fabricated for this test,
    # not a real allotted number -- synthetic fixture data only. Offset
    # computed rather than hand-counted, see test_run.py's fixture.
    text = "Please update my PAN ABCPE1234F on file."
    pan_start = text.index("ABCPE1234F")
    row = {
        "id": "fixture-1",
        "text": text,
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
    }
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")


def _run_attestation(tmp_path: Path, keys_dir: Path, out: Path) -> None:
    corpus = tmp_path / "corpus.jsonl"
    _write_fixture(corpus)
    result = runner.invoke(
        app,
        [
            "run",
            "--pack-name",
            "maskflow-pack-india",
            "--pack-version",
            _INSTALLED_INDIA_VERSION,
            "--corpus",
            str(corpus),
            "--corpus-name",
            "fixture-corpus",
            "--corpus-version",
            "0.0.1",
            "--methodology",
            "unit test fixture",
            "--reproduction-command",
            "pytest",
            "--private-key-file",
            str(keys_dir / "private_key.hex"),
            "--out",
            str(out),
        ],
    )
    assert result.exit_code == 0, result.output


def test_keygen_writes_files(tmp_path: Path) -> None:
    result = runner.invoke(app, ["keygen", "--out-dir", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "private_key.hex").exists()
    assert (tmp_path / "public_key.hex").exists()
    assert "public key:" in result.output


def test_run_then_verify_round_trip(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    runner.invoke(app, ["keygen", "--out-dir", str(keys_dir)])
    attestation = tmp_path / "attestation.json"
    _run_attestation(tmp_path, keys_dir, attestation)
    assert attestation.exists()

    public_key = (keys_dir / "public_key.hex").read_text().strip()
    result = runner.invoke(app, ["verify", str(attestation), "--public-key-hex", public_key])
    assert result.exit_code == 0, result.output
    assert "VALID" in result.output


def test_verify_rejects_tampered_document(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    runner.invoke(app, ["keygen", "--out-dir", str(keys_dir)])
    attestation = tmp_path / "attestation.json"
    _run_attestation(tmp_path, keys_dir, attestation)

    data = json.loads(attestation.read_text())
    data["document"]["num_docs"] = 999999  # tamper after signing
    attestation.write_text(json.dumps(data))

    public_key = (keys_dir / "public_key.hex").read_text().strip()
    result = runner.invoke(app, ["verify", str(attestation), "--public-key-hex", public_key])
    assert result.exit_code == 1
    assert "INVALID" in result.output


def test_verify_rejects_wrong_public_key(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    other_keys_dir = tmp_path / "other-keys"
    runner.invoke(app, ["keygen", "--out-dir", str(keys_dir)])
    runner.invoke(app, ["keygen", "--out-dir", str(other_keys_dir)])
    attestation = tmp_path / "attestation.json"
    _run_attestation(tmp_path, keys_dir, attestation)

    wrong_public_key = (other_keys_dir / "public_key.hex").read_text().strip()
    result = runner.invoke(app, ["verify", str(attestation), "--public-key-hex", wrong_public_key])
    assert result.exit_code == 1
    assert "INVALID" in result.output


def test_run_rejects_pack_version_mismatch(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    runner.invoke(app, ["keygen", "--out-dir", str(keys_dir)])
    corpus = tmp_path / "corpus.jsonl"
    _write_fixture(corpus)

    result = runner.invoke(
        app,
        [
            "run",
            "--pack-name",
            "maskflow-pack-india",
            "--pack-version",
            "999.999.999",
            "--corpus",
            str(corpus),
            "--corpus-name",
            "fixture-corpus",
            "--corpus-version",
            "0.0.1",
            "--methodology",
            "unit test fixture",
            "--reproduction-command",
            "pytest",
            "--private-key-file",
            str(keys_dir / "private_key.hex"),
            "--out",
            str(tmp_path / "attestation.json"),
        ],
    )
    assert result.exit_code == 1
    assert "is installed, but this attestation is for" in result.output


def test_registry_add_show_revoke_round_trip(tmp_path: Path) -> None:
    keys_dir = tmp_path / "keys"
    runner.invoke(app, ["keygen", "--out-dir", str(keys_dir)])
    attestation = tmp_path / "attestation.json"
    _run_attestation(tmp_path, keys_dir, attestation)

    registry = tmp_path / "registry.jsonl"
    add_result = runner.invoke(
        app, ["registry", "add", str(attestation), "--registry", str(registry)]
    )
    assert add_result.exit_code == 0, add_result.output
    assert registry.exists()

    show_result = runner.invoke(
        app, ["registry", "show", "--pack-name", "maskflow-pack-india", "--registry", str(registry)]
    )
    assert show_result.exit_code == 0, show_result.output
    assert _INSTALLED_INDIA_VERSION in show_result.output

    revoke_result = runner.invoke(
        app,
        [
            "registry",
            "revoke",
            "--pack-name",
            "maskflow-pack-india",
            "--pack-version",
            _INSTALLED_INDIA_VERSION,
            "--reason",
            "test revocation",
            "--registry",
            str(registry),
        ],
    )
    assert revoke_result.exit_code == 0, revoke_result.output

    show_after_revoke = runner.invoke(
        app, ["registry", "show", "--pack-name", "maskflow-pack-india", "--registry", str(registry)]
    )
    assert show_after_revoke.exit_code == 1


def test_registry_revoke_no_match_fails(tmp_path: Path) -> None:
    registry = tmp_path / "registry.jsonl"
    result = runner.invoke(
        app,
        [
            "registry",
            "revoke",
            "--pack-name",
            "nope",
            "--pack-version",
            "1.0.0",
            "--reason",
            "x",
            "--registry",
            str(registry),
        ],
    )
    assert result.exit_code == 1
