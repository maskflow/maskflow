"""``maskflow-attest`` -- its own console script (see pyproject.toml), not a
subcommand of ``maskflow``: this package has no dependency on
``maskflow-cli`` and is meant to run standalone in a clean container, which
is exactly the reproduction environment an attestation's own
``reproduction_command`` points at.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import NoReturn

import typer

from .document import AttestationDocumentError
from .registry import AttestationRecord, AttestationRegistry
from .run import AttestationRunError, run_attestation
from .signing import SigningError, generate_keypair, public_key_for
from .signing import sign as sign_document
from .signing import verify as verify_signature

app = typer.Typer(
    help="Reproducible, signed accuracy attestations for a pinned MaskFlow pack version.",
    no_args_is_help=True,
)
registry_app = typer.Typer(help="Manage a local attestation registry file.", no_args_is_help=True)
app.add_typer(registry_app, name="registry")

# Module-level singletons for every typer.Option/Argument -- ruff's B008
# flags a function call in an argument default; same pattern as
# maskflow-cli's scan/cmd.py and commands/bench_cmd.py.
_KEYGEN_OUT_DIR_OPT = typer.Option(
    Path("."), "--out-dir", help="Directory to write private_key.hex and public_key.hex into."
)

_RUN_PACK_NAME_OPT = typer.Option(..., help="e.g. maskflow-pack-india")
_RUN_PACK_VERSION_OPT = typer.Option(..., help="Must match the version actually installed.")
_RUN_CORPUS_OPT = typer.Option(..., exists=True, dir_okay=False, help="Corpus JSONL path.")
_RUN_CORPUS_NAME_OPT = typer.Option(..., help="e.g. indiapii-v1.0")
_RUN_CORPUS_VERSION_OPT = typer.Option(..., help="e.g. 1.0")
_RUN_METHODOLOGY_OPT = typer.Option(..., help="One-paragraph summary of what was measured.")
_RUN_REPRO_CMD_OPT = typer.Option(
    ..., help="The exact command a third party runs to reproduce this."
)
_RUN_PRIVATE_KEY_FILE_OPT = typer.Option(
    ..., exists=True, dir_okay=False, help="File containing the signer's private key hex."
)
_RUN_OUT_OPT = typer.Option(..., help="Where to write the signed attestation record (JSON).")
_RUN_VALID_DAYS_OPT = typer.Option(90, help="Validity window in days from issuance.")
_RUN_LIMIT_OPT = typer.Option(None, help="Score only the first N documents.")
_RUN_REGISTRY_OPT = typer.Option(None, help="Also append the signed record to this registry file.")

_VERIFY_ATTESTATION_ARG = typer.Argument(..., exists=True, dir_okay=False)
_VERIFY_PUBLIC_KEY_FILE_OPT = typer.Option(
    None, "--public-key-file", exists=True, dir_okay=False, help="Trusted public key hex file."
)
_VERIFY_PUBLIC_KEY_HEX_OPT = typer.Option(
    None, "--public-key-hex", help="Trusted public key hex, inline (alternative to the file)."
)

_REGISTRY_RECORD_FILE_ARG = typer.Argument(..., exists=True, dir_okay=False)
_REGISTRY_PATH_OPT = typer.Option(...)
_REGISTRY_PACK_NAME_OPT = typer.Option(...)
_REGISTRY_PACK_VERSION_OPT = typer.Option(...)
_REGISTRY_PACK_VERSION_OPTIONAL_OPT = typer.Option(None)
_REGISTRY_REASON_OPT = typer.Option(...)


def _die(message: str) -> NoReturn:
    typer.echo(message, err=True)
    raise typer.Exit(code=1)


def _read_key_file(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


@app.command()
def keygen(out_dir: Path = _KEYGEN_OUT_DIR_OPT) -> None:
    """Generates a new Ed25519 keypair. Run this once, offline -- the
    private key file must never be committed to a repo or a CI run; move
    it to a deploy-environment secret store and delete the local copy."""
    private_hex, public_hex = generate_keypair()
    out_dir.mkdir(parents=True, exist_ok=True)
    private_path = out_dir / "private_key.hex"
    public_path = out_dir / "public_key.hex"
    private_path.write_text(private_hex + "\n", encoding="utf-8")
    try:
        private_path.chmod(0o600)
    except OSError:  # pragma: no cover - best-effort on platforms without POSIX perms
        pass
    public_path.write_text(public_hex + "\n", encoding="utf-8")
    typer.echo(f"wrote {private_path} (keep secret -- never commit) and {public_path}")
    typer.echo(f"public key: {public_hex}")


@app.command()
def run(
    pack_name: str = _RUN_PACK_NAME_OPT,
    pack_version: str = _RUN_PACK_VERSION_OPT,
    corpus: Path = _RUN_CORPUS_OPT,
    corpus_name: str = _RUN_CORPUS_NAME_OPT,
    corpus_version: str = _RUN_CORPUS_VERSION_OPT,
    methodology: str = _RUN_METHODOLOGY_OPT,
    reproduction_command: str = _RUN_REPRO_CMD_OPT,
    private_key_file: Path = _RUN_PRIVATE_KEY_FILE_OPT,
    out: Path = _RUN_OUT_OPT,
    valid_days: int = _RUN_VALID_DAYS_OPT,
    limit: int | None = _RUN_LIMIT_OPT,
    registry: Path | None = _RUN_REGISTRY_OPT,
) -> None:
    """Runs MaskFlow's detector against CORPUS, scores it, and writes a
    signed attestation. The pack under attestation must already be
    installed at exactly PACK_VERSION -- this never falls back to
    "whatever's installed", it verifies the match first."""
    try:
        document = run_attestation(
            corpus_path=corpus,
            corpus_name=corpus_name,
            corpus_version=corpus_version,
            pack_name=pack_name,
            pack_version=pack_version,
            methodology=methodology,
            reproduction_command=reproduction_command,
            valid_days=valid_days,
            limit=limit,
        )
    except AttestationRunError as exc:
        _die(str(exc))
    except ModuleNotFoundError as exc:
        _die(f"missing dependency: {exc}")

    private_key_hex = _read_key_file(private_key_file)
    try:
        signature = sign_document(document.canonical_json(), private_key_hex)
        signer_public_key = public_key_for(private_key_hex)
    except SigningError as exc:
        _die(f"signing failed: {exc}")

    record = AttestationRecord(
        document=document, signature=signature, signer_public_key=signer_public_key
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    typer.echo(f"wrote {out}")

    if registry is not None:
        reg = AttestationRegistry.load(registry)
        reg.add(record)
        reg.save(registry)
        typer.echo(f"appended to {registry}")


@app.command()
def verify(
    attestation: Path = _VERIFY_ATTESTATION_ARG,
    public_key_file: Path | None = _VERIFY_PUBLIC_KEY_FILE_OPT,
    public_key_hex: str | None = _VERIFY_PUBLIC_KEY_HEX_OPT,
) -> None:
    """Checks ATTESTATION's signature against a trusted public key you
    supply -- never a key found inside the file itself, which would let a
    re-signed forgery vouch for its own forger. Get the current trusted
    key from this package's docs, not from anywhere in this command."""
    if (public_key_file is None) == (public_key_hex is None):
        _die("pass exactly one of --public-key-file or --public-key-hex")

    if public_key_hex is not None:
        trusted_key = public_key_hex
    else:
        assert public_key_file is not None  # narrowed by the exactly-one-of check above
        trusted_key = _read_key_file(public_key_file)

    try:
        data = json.loads(attestation.read_text(encoding="utf-8"))
        record = AttestationRecord.from_dict(data)
    except (json.JSONDecodeError, AttestationDocumentError, KeyError) as exc:
        _die(f"{attestation}: not a valid attestation record ({exc})")

    ok = verify_signature(record.document.canonical_json(), record.signature, trusted_key)
    if not ok:
        typer.echo("INVALID -- signature does not match the supplied public key", err=True)
        raise typer.Exit(code=1)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    expired = record.document.valid_until < now
    revoked_note = ""
    if record.revoked:
        revoked_note = " (REVOKED" + (f": {record.revoked_reason}" if record.revoked_reason else "")
        revoked_note += ")"
    typer.echo(
        f"VALID -- {record.document.pack_name} {record.document.pack_version} "
        f"against {record.document.corpus_name}, issued {record.document.issued_at}, "
        f"valid until {record.document.valid_until}"
        + (" [EXPIRED]" if expired else "")
        + revoked_note
    )
    if record.revoked or expired:
        raise typer.Exit(code=1)


@registry_app.command("add")
def registry_add(
    record_file: Path = _REGISTRY_RECORD_FILE_ARG,
    registry: Path = _REGISTRY_PATH_OPT,
) -> None:
    """Appends a signed attestation record (as written by `run --out`) to
    REGISTRY. Does not itself verify the signature -- run `verify` first."""
    data = json.loads(record_file.read_text(encoding="utf-8"))
    record = AttestationRecord.from_dict(data)
    reg = AttestationRegistry.load(registry)
    reg.add(record)
    reg.save(registry)
    typer.echo(f"added {record.document.pack_name} {record.document.pack_version} to {registry}")


@registry_app.command("revoke")
def registry_revoke(
    pack_name: str = _REGISTRY_PACK_NAME_OPT,
    pack_version: str = _REGISTRY_PACK_VERSION_OPT,
    reason: str = _REGISTRY_REASON_OPT,
    registry: Path = _REGISTRY_PATH_OPT,
) -> None:
    """Marks every matching, non-revoked record revoked. The record and its
    original signature are kept, never deleted."""
    reg = AttestationRegistry.load(registry)
    changed = reg.revoke(pack_name, pack_version, reason=reason)
    reg.save(registry)
    if changed == 0:
        _die(f"no non-revoked record found for {pack_name} {pack_version} in {registry}")
    typer.echo(f"revoked {changed} record(s)")


@registry_app.command("show")
def registry_show(
    pack_name: str = _REGISTRY_PACK_NAME_OPT,
    pack_version: str | None = _REGISTRY_PACK_VERSION_OPTIONAL_OPT,
    registry: Path = _REGISTRY_PATH_OPT,
) -> None:
    """Prints the latest non-revoked record for PACK_NAME (optionally
    pinned to PACK_VERSION)."""
    reg = AttestationRegistry.load(registry)
    record = reg.latest(pack_name, pack_version)
    if record is None:
        _die(f"no attestation found for {pack_name}" + (f" {pack_version}" if pack_version else ""))
    typer.echo(json.dumps(record.to_dict(), indent=2, sort_keys=True))


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
