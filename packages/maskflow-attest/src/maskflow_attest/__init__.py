"""Reproducible, signed accuracy attestations for a pinned MaskFlow
recognizer pack version.

Given a pack version, :func:`run_attestation` runs the full public
benchmark harness against it and produces a dated document; :func:`sign`
and :func:`verify` (Ed25519) make that document a citable, independently
checkable claim rather than an assertion. :class:`AttestationRegistry`
tracks every attestation issued, with revocation.

See ``docs/attestations.md`` for the mechanism and how to independently
verify an attestation. Issue #43.
"""

from __future__ import annotations

from .document import AttestationDocument, AttestationDocumentError
from .registry import AttestationRecord, AttestationRegistry
from .run import AttestationRunError, run_attestation
from .signing import SigningError, generate_keypair, public_key_for, sign, verify

__all__ = [
    "AttestationDocument",
    "AttestationDocumentError",
    "AttestationRecord",
    "AttestationRegistry",
    "AttestationRunError",
    "SigningError",
    "generate_keypair",
    "public_key_for",
    "run_attestation",
    "sign",
    "verify",
]
