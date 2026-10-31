"""Synthetic identities, built on the pack's own surrogate generators.

Reuse rather than reimplementation is the point. `maskflow_pack_india.
surrogates` already produces values that are checksum-valid where the type
has a published checksum, draws its handles/bank/RTO codes from the bundled
reference data, and carries a prose provenance note per type. Writing a
second generator here would fork the checksum logic and guarantee the two
drift.

(`bench/indiapii/generator/identifiers.py` has the nicer
`generate_<type>(rng)` shape, but `bench/` has no `__init__.py` anywhere and
is not a uv workspace member, so a distributed package cannot import it.
This module mirrors that signature on top of the shipped surrogates.)

**Honesty, carried into the manifest and the docs.** Only Aadhaar (Verhoeff),
GSTIN (mod-36) and the passport MRZ (ICAO 9303) are genuinely
checksum-bearing. PAN, IFSC, VOTER_ID, PIN_CODE, BANK_ACCOUNT_IN,
DRIVING_LICENCE and VEHICLE_REG have no published checksum and are
*format*-valid only; ABHA_NUMBER has no validator at all. So the guarantee
is "checksum-valid where a published checksum exists, structurally valid to
the documented format otherwise" -- never more.

**A generated Aadhaar-shaped number could collide with a real one.** It is
random digits plus a valid check digit, drawn from no registry, but the
space is finite. Canaries therefore never leave a local or test environment
and are never transmitted anywhere except the intercepted test run, whose
whole purpose is that the request does not reach a provider.
"""

from __future__ import annotations

import random

from maskflow_pack_india import surrogates  # type: ignore[import-untyped]

#: The entity types a canary identity covers, with the seed value each
#: surrogate shape-matches against. The surrogate API takes an `original`
#: it mirrors the separators of, so each entry supplies a canonical
#: template rather than a real value.
_TEMPLATES: dict[str, tuple[str, object]] = {
    "AADHAAR": ("000000000000", surrogates.surrogate_aadhaar),
    "PAN": ("AAAPA0000A", surrogates.surrogate_pan),
    "GSTIN": ("00AAAPA0000A0Z0", surrogates.surrogate_gstin),
    "IFSC": ("AAAA0000000", surrogates.surrogate_ifsc),
    "UPI_VPA": ("name@okaxis", surrogates.surrogate_upi_vpa),
    "INDIAN_MOBILE": ("9000000000", surrogates.surrogate_indian_mobile),
    "PERSON_NAME": ("Name Surname", surrogates.surrogate_person_name),
    "INDIAN_ADDRESS": ("H.No. 1, Nagar, City, State", surrogates.surrogate_indian_address),
    "PIN_CODE": ("500001", surrogates.surrogate_pin_code),
    "VOTER_ID": ("AAA0000000", surrogates.surrogate_voter_id),
    "ABHA_ADDRESS": ("name@abdm", surrogates.surrogate_abha_address),
    "BANK_ACCOUNT_IN": ("000000000000", surrogates.surrogate_bank_account),
}

#: Public, ordered list of the types a canary identity carries.
CANARY_TYPES: tuple[str, ...] = tuple(_TEMPLATES)

#: Types whose value is genuinely checksum-verified by the pack. Everything
#: else in CANARY_TYPES is format-valid only -- the manifest records which
#: is which so the report never over-claims.
CHECKSUM_BEARING: frozenset[str] = frozenset({"AADHAAR", "GSTIN"})


def generate_value(entity_type: str, rng: random.Random) -> str:
    """One synthetic value of `entity_type`, deterministic from `rng`."""
    try:
        template, generator = _TEMPLATES[entity_type]
    except KeyError:
        raise ValueError(
            f"unknown canary type {entity_type!r}; known: {list(CANARY_TYPES)}"
        ) from None
    return str(generator(template, rng))  # type: ignore[operator]


def generate_identity(rng: random.Random) -> dict[str, str]:
    """A correlated synthetic person: one value per CANARY_TYPES entry.

    Correlated matters. Seeding one Aadhaar proves an Aadhaar column
    leaks; seeding a *person* -- their name, their Aadhaar, their PAN,
    their UPI handle -- is what catches an app that masks the identifier
    column and passes the name through in the same prompt.
    """
    return {entity_type: generate_value(entity_type, rng) for entity_type in CANARY_TYPES}
