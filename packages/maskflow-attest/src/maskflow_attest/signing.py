"""Ed25519 sign/verify over an :class:`~maskflow_attest.document.AttestationDocument`'s
canonical JSON bytes.

Requires the ``cryptography`` package (base dependency of this package --
signing is the entire point, unlike ``maskflow-core``'s optional
``[store]`` extra). A signature travels as ``"ed25519:<128 hex chars>"``; a
key travels as 32 raw bytes, hex-encoded -- never PEM, so it's
copy-pasteable into one config line or one env var.

**Security note.** :func:`verify` must be called with a public key the
caller already trusts from an out-of-band source -- this package's
published docs, a pinned config value -- never with a key read from the
same payload being verified. A re-signed forgery can trivially carry its
own "matching" key along with it; only a key the verifier already had
before opening the file means anything.
"""

from __future__ import annotations

from typing import Any

_HEX_KEY_LEN = 64  # 32 bytes, hex-encoded
_SIG_PREFIX = "ed25519:"


class SigningError(ValueError):
    """A key or signature was malformed -- never which bytes, just that
    they didn't parse (keys are secrets; never included in a message)."""


def _ed25519() -> Any:  # noqa: ANN401 - returns a module, typed loosely on purpose
    try:
        from cryptography.hazmat.primitives.asymmetric import ed25519
    except ModuleNotFoundError as exc:  # pragma: no cover - import guard
        raise ModuleNotFoundError(
            "maskflow-attest signing needs the 'cryptography' package"
        ) from exc
    return ed25519


def _decode_key(key_hex: str, *, what: str) -> bytes:
    try:
        key_bytes = bytes.fromhex(key_hex)
    except ValueError as exc:
        raise SigningError(f"{what} must be {_HEX_KEY_LEN} hex characters") from exc
    if len(key_bytes) != 32:
        raise SigningError(f"{what} must be 32 bytes ({_HEX_KEY_LEN} hex characters)")
    return key_bytes


def generate_keypair() -> tuple[str, str]:
    """Returns ``(private_key_hex, public_key_hex)``. Generate once,
    offline; the private half should never be written to a repo or a CI
    run -- store it only in a deploy-environment secret store."""
    ed25519 = _ed25519()
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    # Explicit `bytes` annotations: `ed25519` is typed `Any` (cryptography's
    # stubs are ignored project-wide, see root pyproject.toml), so without
    # these mypy sees `.hex()`'s result as `Any` too.
    private_bytes: bytes = private_key.private_bytes_raw()
    public_bytes: bytes = public_key.public_bytes_raw()
    return private_bytes.hex(), public_bytes.hex()


def public_key_for(private_key_hex: str) -> str:
    """Derives the public key hex for a private key hex -- lets ``verify``
    of a self-signed test fixture avoid keeping two copies in sync."""
    ed25519 = _ed25519()
    key_bytes = _decode_key(private_key_hex, what="private key")
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)
    public_bytes: bytes = private_key.public_key().public_bytes_raw()
    return public_bytes.hex()


def sign(payload: str, private_key_hex: str) -> str:
    """Signs ``payload`` (typically ``AttestationDocument.canonical_json()``)
    with the given private key, returning ``"ed25519:<hex>"``."""
    ed25519 = _ed25519()
    key_bytes = _decode_key(private_key_hex, what="private key")
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(key_bytes)
    signature: bytes = private_key.sign(payload.encode("utf-8"))
    return _SIG_PREFIX + signature.hex()


def verify(payload: str, signature: str, trusted_public_key_hex: str) -> bool:
    """True iff ``signature`` is a valid Ed25519 signature over ``payload``
    under ``trusted_public_key_hex``. Never raises on a bad signature or a
    malformed input -- returns ``False``, same as any other "does this
    check out" predicate; a caller that needs to know *why* should compare
    the returned key/signature shape itself, not catch an exception here."""
    ed25519 = _ed25519()
    from cryptography.exceptions import InvalidSignature

    if not signature.startswith(_SIG_PREFIX):
        return False
    try:
        sig_bytes = bytes.fromhex(signature[len(_SIG_PREFIX) :])
        key_bytes = _decode_key(trusted_public_key_hex, what="public key")
    except (ValueError, SigningError):
        return False
    if len(sig_bytes) != 64:
        return False
    public_key = ed25519.Ed25519PublicKey.from_public_bytes(key_bytes)
    try:
        public_key.verify(sig_bytes, payload.encode("utf-8"))
        return True
    except InvalidSignature:
        return False
