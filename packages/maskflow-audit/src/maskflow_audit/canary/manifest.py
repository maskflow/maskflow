"""The canary manifest: what was seeded, and proof it is detectable.

Two jobs.

First, **self-check**: every generated value is re-validated against
maskflow-pack-india's own `validate_*()` functions before it is allowed
anywhere near a test run. A canary MaskFlow would not detect proves
nothing -- if it escaped, that would be a generator bug masquerading as a
finding. Ported from `bench/indiapii/generator/generate.py:82 self_check()`,
including the rule that failure descriptions carry labels only, never the
offending value (rule 1).

Second, **identity**: a canary must be recognisable as a canary in the
manifest while looking entirely real to the code under test. The manifest
holds the mapping; the seeded application sees only the value.

Seeds, not values, are what may be committed. The seed defaults to a fresh
random draw per run (so no repository ever accumulates a PII-shaped
constant, per rule 2) and is recorded here, so `--seed` reproduces an exact
run when you need to.
"""

from __future__ import annotations

import random
import secrets
from dataclasses import dataclass, field

from maskflow_pack_india import patterns  # type: ignore[import-untyped]

from .generate import CANARY_TYPES, CHECKSUM_BEARING, generate_identity

#: entity type -> the pack's own validator. A type absent from this map has
#: no published checksum or validator (ABHA_NUMBER has neither), so its
#: value is format-valid only and the manifest says so rather than
#: pretending it was verified.
_VALIDATORS = {
    "AADHAAR": patterns.validate_aadhaar,
    "PAN": patterns.validate_pan,
    "GSTIN": patterns.validate_gstin,
    "IFSC": patterns.validate_ifsc,
    "UPI_VPA": patterns.validate_upi_vpa,
    "INDIAN_MOBILE": patterns.validate_indian_mobile,
    "ABHA_ADDRESS": patterns.validate_abha_address,
    "VEHICLE_REG": patterns.validate_vehicle_reg,
    "DRIVING_LICENCE": patterns.validate_driving_licence,
}


class SelfCheckFailure(Exception):
    """A generated canary failed the pack's own validator.

    Fatal on purpose: continuing would run an audit whose negative results
    mean nothing. Carries entity-type labels only, never a value.
    """

    def __init__(self, failures: list[str]) -> None:
        self.failures = failures
        joined = "\n".join(f"  - {f}" for f in failures)
        super().__init__(
            f"{len(failures)} generated canary value(s) failed the pack's own "
            f"validators -- this is a generator bug, not a finding:\n{joined}"
        )


@dataclass(frozen=True)
class Canary:
    """One synthetic value, and what is known about it.

    `value` is repr-excluded. A canary is not real personal data, but it is
    identifier-shaped, it could collide with a real value, and a traceback
    that printed one would train everybody reading it to expect values in
    tracebacks. Same discipline as `Span.text` and `MappingEntry.original`.
    """

    entity_type: str
    value: str = field(repr=False)
    checksum_verified: bool
    identity: int  # which synthetic person this value belongs to

    @property
    def validation(self) -> str:
        """How strong the guarantee on this value actually is."""
        if self.checksum_verified:
            return "checksum-valid (published checksum, verified by the pack)"
        if self.entity_type in _VALIDATORS:
            return "format-valid (no published checksum; validator-verified)"
        return "format-valid (no published checksum and no validator for this type)"


@dataclass(frozen=True)
class CanaryManifest:
    """Every canary for one audit run."""

    seed: int
    identities: int
    canaries: tuple[Canary, ...]

    def values(self) -> tuple[str, ...]:
        return tuple(c.value for c in self.canaries)

    def by_value(self) -> dict[str, Canary]:
        return {c.value: c for c in self.canaries}

    def for_identity(self, identity: int) -> dict[str, str]:
        """The `{entity_type: value}` map for one synthetic person."""
        return {c.entity_type: c.value for c in self.canaries if c.identity == identity}

    def summary(self) -> dict[str, int]:
        """Counts by entity type -- safe to log, unlike the values."""
        out: dict[str, int] = {}
        for canary in self.canaries:
            out[canary.entity_type] = out.get(canary.entity_type, 0) + 1
        return out


def self_check(canaries: tuple[Canary, ...]) -> tuple[int, int, list[str]]:
    """Returns (checked, failed, failure descriptions).

    Failure descriptions carry the entity type and the identity index only
    -- never the underlying value (rule 1).
    """
    checked = 0
    failures: list[str] = []
    for canary in canaries:
        validator = _VALIDATORS.get(canary.entity_type)
        if validator is None:
            continue
        checked += 1
        if validator(canary.value) is None:
            failures.append(
                f"{canary.entity_type} (identity {canary.identity}) was rejected by "
                f"the pack's validate_{canary.entity_type.lower()}()"
            )
    return checked, len(failures), failures


def build_manifest(*, seed: int | None = None, identities: int = 1) -> CanaryManifest:
    """Generate `identities` synthetic people and verify every value.

    `seed` defaults to a fresh random draw, so no run reuses values and no
    repository accumulates a PII-shaped constant. The chosen seed is
    recorded on the manifest and reported, so a run can be reproduced.
    """
    if identities < 1:
        raise ValueError(f"identities must be >= 1 (got {identities})")

    resolved_seed = seed if seed is not None else secrets.randbits(32)
    rng = random.Random(resolved_seed)

    canaries: list[Canary] = []
    for identity in range(identities):
        for entity_type, value in generate_identity(rng).items():
            canaries.append(
                Canary(
                    entity_type=entity_type,
                    value=value,
                    checksum_verified=entity_type in CHECKSUM_BEARING,
                    identity=identity,
                )
            )

    frozen = tuple(canaries)
    _, failed, failures = self_check(frozen)
    if failed:
        raise SelfCheckFailure(failures)

    return CanaryManifest(seed=resolved_seed, identities=identities, canaries=frozen)


def expected_types() -> tuple[str, ...]:
    return CANARY_TYPES
