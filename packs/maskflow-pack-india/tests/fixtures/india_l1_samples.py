"""Labeled PERSON_NAME (Indian) / INDIAN_ADDRESS examples for the L1
(gazetteer-only) layer of the work order's four-layer build -- separate from
pii_samples.py's POSITIVE_SAMPLES/NEGATIVE_SAMPLES (which feed
test_detection.py's fixed 0.95 accuracy gate for the checksum-backed India
types) because L1's expected recall, especially for INDIAN_ADDRESS, is
deliberately low by design (see gazetteer.py) -- mixing these in would
either break that gate or force it down for every other recognizer.

POSITIVE samples: `expected` findings must show up in detect()'s output.
NEGATIVE samples: plain sentences (no name/place-shaped text at all) that
must produce zero PERSON_NAME/INDIAN_ADDRESS findings.
HARD_NEGATIVE samples: text that IS gazetteer-shaped (a real name or place
token, capitalized, word-boundary-clean) but used in a non-PII sense --
common-word/name collisions ("Rose" the flower), a bare place mention with
no address context, a common-tier name with no name-context nearby. These
are the precision signal L1 has no negative-context mechanism to lean on
for (see __init__.py's docstring) -- bench/indiapii/report.py scores all
three buckets together via bench/indiapii/metrics.py.

No real person's name or address appears here -- every positive sample
pairs a gazetteer entry (all either bundled name-corpus tokens or
well-known public place names, never information about a specific real
individual) with synthetic surrounding text, same spirit as CLAUDE.md rule
2 applied to the other India recognizers' fixtures.
"""

from dataclasses import dataclass

import maskflow_pack_india  # noqa: F401 -- import side effect registers PERSON_NAME/INDIAN_ADDRESS
from maskflow_core.entities import PIIType


@dataclass
class Sample:
    text: str
    expected: list[tuple[PIIType, str]]


# ---------------------------------------------------------------------------
# PERSON_NAME (Indian)
# ---------------------------------------------------------------------------

PERSON_NAME_POSITIVE_SAMPLES: list[Sample] = [
    # Rare-tier full name (given + surname), no context needed -- multi-token
    # coalescing + MULTI_TOKEN_BONUS should clear threshold on its own.
    Sample(
        "Rohit Sharma called yesterday to confirm the appointment.",
        [(PIIType.PERSON_NAME, "Rohit Sharma")],
    ),
    Sample(
        "Please contact Priya Iyer at the front desk.",
        [(PIIType.PERSON_NAME, "Priya Iyer")],
    ),
    Sample(
        "The delivery was signed for by Anjali Deshmukh this morning.",
        [(PIIType.PERSON_NAME, "Anjali Deshmukh")],
    ),
    # Rare-tier single given name, no context needed.
    Sample(
        "Bharathushan finished the report ahead of schedule.",
        [(PIIType.PERSON_NAME, "Bharathushan")],
    ),
    # Common-tier surname (in _COMMON_INDIAN_SURNAMES, needs nearby context).
    Sample(
        "Customer name: Kumar, verified against the KYC form.",
        [(PIIType.PERSON_NAME, "Kumar")],
    ),
    Sample(
        "Applicant name Devi was shortlisted for the interview.",
        [(PIIType.PERSON_NAME, "Devi")],
    ),
    # Common-word-collision name WITH context -- should clear threshold.
    Sample(
        "Applicant name Rose submitted the documents on time.",
        [(PIIType.PERSON_NAME, "Rose")],
    ),
    # Hindi/Devanagari context keyword ("naam"/नाम) alongside a Latin-script
    # name -- MaskFlow's India text is expected to mix scripts this way.
    Sample(
        "Mera naam Sanjiv hai aur main Delhi mein rehta hoon.",
        [(PIIType.PERSON_NAME, "Sanjiv")],
    ),
    # Programmatic spelling variant (Krishna -> Krishnaa via the suffix rule).
    Sample(
        "Krishnaa joined the call five minutes late.",
        [(PIIType.PERSON_NAME, "Krishnaa")],
    ),
]

PERSON_NAME_NEGATIVE_SAMPLES: list[str] = [
    "Please review the quarterly report before Friday.",
    "The stock price rose by 4.5 percent today.",
    "Our server uptime this month was 99.98 percent.",
    "Ship the package to the warehouse by Monday.",
    "The meeting has been rescheduled to next week.",
]

PERSON_NAME_HARD_NEGATIVE_SAMPLES: list[str] = [
    # Common-word-collision names used in their NON-name sense, no name
    # context nearby -- must NOT fire (tests tier-gating, not just recall).
    "She wore a Rose in her hair for the wedding.",
    "The garden was full of Lily and Jasmine in full bloom.",
    "We wished them Joy and Happy holidays this year.",
    "The forecast says Rain is expected over the Star observatory tonight.",
    # Common-tier surname with NO nearby context -- must NOT fire alone.
    "Kumar is a common word that appears in many contexts.",
    "Devi temples are found across many parts of India.",
]

# ---------------------------------------------------------------------------
# INDIAN_ADDRESS
# ---------------------------------------------------------------------------

INDIAN_ADDRESS_POSITIVE_SAMPLES: list[Sample] = [
    # State/city + explicit address context -- L1's low base confidence (0.3)
    # needs a nearby keyword to clear DEFAULT_MIN_CONFIDENCE at this layer.
    Sample(
        "Please update the address on file: Chennai, Tamil Nadu.",
        [(PIIType.INDIAN_ADDRESS, "Chennai"), (PIIType.INDIAN_ADDRESS, "Tamil Nadu")],
    ),
    Sample(
        "Resident of Pune since 2015, currently residing at the same address.",
        [(PIIType.INDIAN_ADDRESS, "Pune")],
    ),
    Sample(
        "Ghar ka pata: Lucknow, Uttar Pradesh.",
        [(PIIType.INDIAN_ADDRESS, "Lucknow"), (PIIType.INDIAN_ADDRESS, "Uttar Pradesh")],
    ),
]

INDIAN_ADDRESS_NEGATIVE_SAMPLES: list[str] = [
    "Please review the quarterly report before Friday.",
    "The stock price rose by 4.5 percent today.",
]

INDIAN_ADDRESS_HARD_NEGATIVE_SAMPLES: list[str] = [
    # Bare place mention, no address context nearby -- must NOT fire (L1 is
    # deliberately gazetteer-plus-context-only, not "any place name").
    "I visited Mumbai last week for a conference.",
    "Chennai's weather is humid for most of the year.",
    "Karnataka is known for its IT industry and coffee plantations.",
    "We watched a documentary about the history of Jaipur.",
]
