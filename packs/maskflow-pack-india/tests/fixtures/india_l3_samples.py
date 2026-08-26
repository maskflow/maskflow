"""Labeled PERSON_NAME (Indian) examples for the L3 (NLP agreement) layer --
spaCy PERSON entities down-weighted standalone... except NOT down-weighted
in this pack's actual registration (see __init__.py's L3 comment for why:
preserving maskflow-pack-intl's existing 0.75 standalone baseline so
non-Indian names aren't regressed), up-weighted when they overlap an L1
(gazetteer) or L2 (structural) candidate of the same type, even one that
scored below its own threshold. Agreement is recorded in span.explanation
(see ner.py's detect_ner()).

INDIAN_ADDRESS has NO L3 fixtures here -- a GPE/LOC agreement mapping was
implemented, tested, and deliberately dropped this session (see
__init__.py): it measurably promoted bare place mentions ("Mumbai is a
city in India.") past threshold with no address context, which the work
order's own INDIAN_ADDRESS design principle ("a bare place mention isn't
an address by itself") explicitly rules out. The empty lists below are
intentional, not an oversight -- kept so bench/indiapii/report.py's generic
per-module loader doesn't need special-casing.

See india_l1_samples.py's docstring for the POSITIVE/NEGATIVE/HARD_NEGATIVE
convention. HARD_NEGATIVE_SAMPLES below includes cases that are KNOWN,
PRE-EXISTING maskflow-pack-intl behavior (confirmed present with ONLY
pack-intl loaded, no pack-india) -- included for honest reporting of the
combined system's real precision, not because this session introduced or
is expected to fix them.

No real person's name appears here -- same synthetic-text convention as
india_l1_samples.py/india_l2_samples.py.
"""

from dataclasses import dataclass

import maskflow_pack_india  # noqa: F401 -- import side effect registers PERSON_NAME/INDIAN_ADDRESS
from maskflow_core.entities import PIIType


@dataclass
class Sample:
    text: str
    expected: list[tuple[PIIType, str]]


INDIAN_ADDRESS_POSITIVE_SAMPLES: list[Sample] = []
INDIAN_ADDRESS_NEGATIVE_SAMPLES: list[str] = []
INDIAN_ADDRESS_HARD_NEGATIVE_SAMPLES: list[str] = []

# ---------------------------------------------------------------------------
# PERSON_NAME -- L3 agreement. Deliberately NOT down-weighted standalone
# (see __init__.py) -- these positives confirm that decision: a real,
# non-Indian, gazetteer-absent name still gets detected via spaCy alone,
# same as it always has via maskflow-pack-intl.
# ---------------------------------------------------------------------------

PERSON_NAME_POSITIVE_SAMPLES: list[Sample] = [
    # No gazetteer/structural match at all -- standalone spaCy recall,
    # preserved at pack-intl's existing 0.75 (not down-weighted).
    Sample(
        "I met a person called Zbigniew Wozniak at the summit.",
        [(PIIType.PERSON_NAME, "Zbigniew Wozniak")],
    ),
    Sample(
        "Please forward this to Jennifer Lee.",
        [(PIIType.PERSON_NAME, "Jennifer Lee")],
    ),
]

PERSON_NAME_NEGATIVE_SAMPLES: list[str] = [
    "The shipment was delayed due to weather.",
]

PERSON_NAME_HARD_NEGATIVE_SAMPLES: list[str] = []

# Deliberately NOT duplicated here: india_l1_samples.py's PERSON_NAME_HARD_
# NEGATIVE_SAMPLES already includes "She wore a Rose in her hair...", "The
# garden was full of Lily and Jasmine...", and "Devi temples..." -- L3's
# PERSON registration picks those up automatically (report.py runs one
# detect() per sample against every layer's recognizers combined), and
# re-listing them here would double-count the same failures. Confirmed
# KNOWN, PRE-EXISTING maskflow-pack-intl behavior (present with ONLY
# pack-intl loaded, no pack-india): spaCy's generic English NER tags
# common-word/name collisions as PERSON at pack-intl's flat 0.75 regardless
# of context. This session's agreement_boost doesn't change WHETHER these
# fire (0.75 alone already clears DEFAULT_MIN_CONFIDENCE) -- only pushes an
# already-firing false positive's score higher (0.75 -> 0.95) when the word
# also happens to sit in this pack's gazetteer. Not fixed here: no
# negative-context mechanism exists in core yet (see __init__.py's module
# docstring), and this is pack-intl's recognizer, not pack-india's.

# NOT reproduced as a standalone hard-negative above (couldn't construct one
# without also containing a real name spaCy correctly finds, which would
# make hard-negative scoring double-penalize a true positive): spaCy's
# English-trained model tags "Mera naam" ("my name") itself as part of a
# PERSON entity span when a real name immediately follows it, e.g. "Mera
# naam Sanjiv hai" -> spaCy finds "Mera naam" AND "Sanjiv" as two separate
# PERSON entities. Already caught as over-detection by india_l1_samples.py's
# "Mera naam Sanjiv hai..." positive sample (which correctly expects
# "Sanjiv" alone) -- documented here, not fixed, same reasoning as the
# common-word-collision cases above (no negative-context mechanism in core
# yet; regressing PERSON's standalone confidence to suppress this would
# also suppress genuine non-Indian-name recall).
