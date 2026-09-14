from __future__ import annotations

import pytest
from maskflow_attest.signing import SigningError, generate_keypair, public_key_for, sign, verify


def test_generate_keypair_shapes() -> None:
    private_hex, public_hex = generate_keypair()
    assert len(private_hex) == 64
    assert len(public_hex) == 64
    bytes.fromhex(private_hex)
    bytes.fromhex(public_hex)


def test_generate_keypair_is_random() -> None:
    a = generate_keypair()
    b = generate_keypair()
    assert a != b


def test_public_key_for_matches_generated_pair() -> None:
    private_hex, public_hex = generate_keypair()
    assert public_key_for(private_hex) == public_hex


def test_sign_then_verify_round_trip() -> None:
    private_hex, public_hex = generate_keypair()
    signature = sign("hello world", private_hex)
    assert signature.startswith("ed25519:")
    assert verify("hello world", signature, public_hex) is True


def test_verify_rejects_tampered_payload() -> None:
    private_hex, public_hex = generate_keypair()
    signature = sign("original", private_hex)
    assert verify("tampered", signature, public_hex) is False


def test_verify_rejects_wrong_key() -> None:
    private_hex, _ = generate_keypair()
    _, other_public_hex = generate_keypair()
    signature = sign("payload", private_hex)
    assert verify("payload", signature, other_public_hex) is False


def test_verify_rejects_malformed_signature() -> None:
    _, public_hex = generate_keypair()
    assert verify("payload", "not-a-signature", public_hex) is False
    assert verify("payload", "ed25519:not-hex", public_hex) is False
    assert verify("payload", "ed25519:aabb", public_hex) is False  # too short


def test_verify_rejects_malformed_public_key() -> None:
    private_hex, _ = generate_keypair()
    signature = sign("payload", private_hex)
    assert verify("payload", signature, "not-hex") is False
    assert verify("payload", signature, "aabb") is False  # too short


def test_sign_rejects_malformed_private_key() -> None:
    with pytest.raises(SigningError):
        sign("payload", "not-hex")
    with pytest.raises(SigningError):
        sign("payload", "aabb")  # too short
