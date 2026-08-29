"""Canonical entity taxonomy (the corpus's own positive labels) and each
adapter's raw-label -> canonical-label map.

The canonical taxonomy is never a new ontology invented here -- it's
whatever `value_class: "positive"` labels actually appear in the loaded
corpus, so a future corpus version's label set is picked up automatically
rather than drifting out of sync with a hardcoded list here.

Every LABEL_MAP below is intentionally partial: a raw label an adapter
emits with no entry here is dropped before scoring rather than counted as
a false positive against some unrelated canonical type -- see matching.py
and the harness plan's "Label mapping" section for why (mirrors the
`target_types`-restricted convention already used by
bench/indiapii/metrics.py).
"""

from __future__ import annotations

from collections.abc import Iterable

from .corpus import Document

# One-line definitions handed to the LLM adapter's prompt -- the taxonomy
# itself always comes from canonical_labels(docs) below; this dict is just
# human-readable glosses for whichever of those labels happen to have one.
LABEL_DESCRIPTIONS: dict[str, str] = {
    "AADHAAR": "12-digit Indian national ID (Aadhaar), may be spaced/hyphenated in groups of 4",
    "AADHAAR_MASKED": "Aadhaar number with first 8 digits masked, only last 4 digits visible",
    "ABHA_ADDRESS": "Ayushman Bharat Health Account address, email-shaped (e.g. name@abdm)",
    "ABHA_NUMBER": "14-digit Ayushman Bharat Health Account number",
    "BANK_ACCOUNT_IN": "Indian bank account number, 9-18 digits",
    "DRIVING_LICENCE": "Indian driving licence number (state code + digits)",
    "GSTIN": "15-character Goods and Services Tax Identification Number",
    "IFSC": "11-character bank branch code (4 letters + 0 + 6 alphanumeric)",
    "INDIAN_ADDRESS": "a residential/postal address in India (street, locality, city, state)",
    "INDIAN_MOBILE": "Indian mobile phone number, 10 digits, optionally with +91 prefix",
    "INDIAN_PASSPORT": "Indian passport number (1 letter + 7 digits) or its MRZ block",
    "PAN": "10-character Permanent Account Number (5 letters + 4 digits + 1 letter)",
    "PERSON_NAME": "a person's full name",
    "PIN_CODE": "6-digit Indian postal PIN code",
    "UPI_VPA": "UPI Virtual Payment Address, looks like username@bank-handle",
    "VEHICLE_REG": "Indian vehicle registration number (state code + district + series + digits)",
    "VOTER_ID": "Voter ID / EPIC number, 3 letters + 7 digits",
}


def canonical_labels(docs: Iterable[Document]) -> tuple[str, ...]:
    labels: set[str] = set()
    for doc in docs:
        for _start, _end, label in doc.gold:
            labels.add(label)
    return tuple(sorted(labels))


# maskflow's own PIIType values are literally the corpus's label vocabulary
# (the corpus was generated from maskflow-pack-india's own types) -- no
# translation needed, but adapters.base.Adapter still calls through this
# module for a uniform code path, so this is an identity function.
def identity_map(raw_labels: Iterable[str]) -> dict[str, str]:
    return {label: label for label in raw_labels}


PRESIDIO_LABEL_MAP: dict[str, str] = {
    "PERSON": "PERSON_NAME",
    "PHONE_NUMBER": "INDIAN_MOBILE",
    "LOCATION": "INDIAN_ADDRESS",
}

# Same as PRESIDIO_LABEL_MAP, plus the two custom pattern recognizers
# presidio_custom_adapter.py registers directly under these names.
PRESIDIO_CUSTOM_LABEL_MAP: dict[str, str] = {
    **PRESIDIO_LABEL_MAP,
    "IN_AADHAAR": "AADHAAR",
    "IN_PAN": "PAN",
}

# mask-privacy's DLP registry (core/dlp/registry.py) has zero India-specific
# entity types (confirmed by inspecting the installed package -- 38 raw
# types, all US/EU/generic: BANK_ACCT_NUM, PHONE_NUM, EMAIL_ADDR, US_SSN,
# VEHICLE_PLATE, ...). Its Tier-2 NLP tier is Presidio underneath, reusing
# the same spaCy PERSON/LOCATION labels as PRESIDIO_LABEL_MAP.
MASK_PRIVACY_LABEL_MAP: dict[str, str] = {
    "PERSON": "PERSON_NAME",
    "LOCATION": "INDIAN_ADDRESS",
    "PHONE_NUM": "INDIAN_MOBILE",
    "PHONE_NUM_INTL": "INDIAN_MOBILE",
    "BANK_ACCT_NUM": "BANK_ACCOUNT_IN",
    "VEHICLE_PLATE": "VEHICLE_REG",
}

# naive_regex_adapter.py's own made-up label names, mapped to canonical.
NAIVE_REGEX_LABEL_MAP: dict[str, str] = {
    "PHONE_SHAPED": "INDIAN_MOBILE",
    "AADHAAR_SHAPED": "AADHAAR",
    "PAN_SHAPED": "PAN",
    "PINCODE_SHAPED": "PIN_CODE",
}
