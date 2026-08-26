"""Labeled PERSON_NAME (Indian) / INDIAN_ADDRESS examples for the L2
(structural) layer -- honorifics, relational markers, initials, form-field
labels (PERSON_NAME) and unit markers, landmark-relative phrases, locality
words, PIN_CODE reinforcement (INDIAN_ADDRESS). See india_l1_samples.py's
docstring for why these live separately from pii_samples.py's fixed 0.95
accuracy gate, and for the POSITIVE/NEGATIVE/HARD_NEGATIVE convention.

L2 patterns register alongside L1's gazetteer (both feed the same
PIIType.PERSON_NAME/INDIAN_ADDRESS), so bench/indiapii/report.py scores
these together with india_l1_samples.py's fixtures for one cumulative
L1+L2 number, not an isolated L2-only one -- there's no way to detect()
with only a subset of registered patterns active.

No real person's name or address appears here -- same synthetic-text
convention as india_l1_samples.py.
"""

from dataclasses import dataclass

import maskflow_pack_india  # noqa: F401 -- import side effect registers PERSON_NAME/INDIAN_ADDRESS
from maskflow_core.entities import PIIType


@dataclass
class Sample:
    text: str
    expected: list[tuple[PIIType, str]]


# ---------------------------------------------------------------------------
# PERSON_NAME (Indian) -- L2 structural
# ---------------------------------------------------------------------------

PERSON_NAME_POSITIVE_SAMPLES: list[Sample] = [
    # Honorific + name -- honorific itself must NOT be part of the span.
    Sample("Mr. Sharma will attend the meeting.", [(PIIType.PERSON_NAME, "Sharma")]),
    Sample(
        "Dr. Priya Iyer confirmed the appointment.",
        [(PIIType.PERSON_NAME, "Priya Iyer")],
    ),
    Sample(
        "Shri Ramesh Chandra Verma inaugurated the event.",
        [(PIIType.PERSON_NAME, "Ramesh Chandra Verma")],
    ),
    Sample("Smt. Kavita Nair addressed the gathering.", [(PIIType.PERSON_NAME, "Kavita Nair")]),
    # Relational marker -- both the subject and the relative's name.
    Sample(
        "Ramesh S/o Suresh Kumar submitted the form.",
        [(PIIType.PERSON_NAME, "Ramesh"), (PIIType.PERSON_NAME, "Suresh Kumar")],
    ),
    Sample(
        "Anita D/o Mohan Lal registered for the exam.",
        [(PIIType.PERSON_NAME, "Anita"), (PIIType.PERSON_NAME, "Mohan Lal")],
    ),
    # Initials before a surname (dotted form).
    Sample("K.S. Rao signed the document.", [(PIIType.PERSON_NAME, "K.S. Rao")]),
    Sample("R. Venkataraman was appointed director.", [(PIIType.PERSON_NAME, "R. Venkataraman")]),
    # Form-field label.
    Sample(
        "Name: Anjali Deshmukh, DOB 1990.",
        [(PIIType.PERSON_NAME, "Anjali Deshmukh")],
    ),
    Sample(
        "Customer Name Vikram Singh, account verified.",
        [(PIIType.PERSON_NAME, "Vikram Singh")],
    ),
]

PERSON_NAME_NEGATIVE_SAMPLES: list[str] = [
    "Please submit the report by Friday.",
    "The Sun rises in the east every morning.",
    "Contact HR for further assistance.",
]

PERSON_NAME_HARD_NEGATIVE_SAMPLES: list[str] = [
    # Honorific-shaped words that are this pack's own excluded vocabulary,
    # used in running text without actually preceding a name.
    "The doctor prescribed Dr. Reddy's brand medicine only.",
    # Trailing single-capital-letter noise that must NOT read as an initial
    # without any nearby name context.
    "Team A finished the project ahead of schedule.",
    "Please review Section B before submission.",
]

# ---------------------------------------------------------------------------
# INDIAN_ADDRESS -- L2 structural
# ---------------------------------------------------------------------------

INDIAN_ADDRESS_POSITIVE_SAMPLES: list[Sample] = [
    Sample(
        "H.No. 123, Sector 62, Noida.",
        [(PIIType.INDIAN_ADDRESS, "H.No. 123"), (PIIType.INDIAN_ADDRESS, "Sector 62")],
    ),
    Sample("Please deliver to Flat 4B, near the market.", [(PIIType.INDIAN_ADDRESS, "Flat 4B")]),
    Sample("The house is near City Hospital.", [(PIIType.INDIAN_ADDRESS, "City Hospital")]),
    Sample(
        "We live in Lajpat Nagar, close to the metro station.",
        [(PIIType.INDIAN_ADDRESS, "Lajpat Nagar")],
    ),
    Sample(
        "Their office is in Green Park Colony.",
        [(PIIType.INDIAN_ADDRESS, "Green Park Colony")],
    ),
    # PIN_CODE reinforcement: a bare city mention next to a PIN-shaped
    # number clears threshold even with no other address keyword nearby.
    Sample(
        "Please send it to Sector 45, Gurgaon - 122003.",
        [(PIIType.INDIAN_ADDRESS, "Sector 45"), (PIIType.INDIAN_ADDRESS, "Gurgaon")],
    ),
]

INDIAN_ADDRESS_NEGATIVE_SAMPLES: list[str] = [
    "The conference starts at 10 AM sharp.",
    "Our quarterly revenue grew by 12 percent.",
]

INDIAN_ADDRESS_HARD_NEGATIVE_SAMPLES: list[str] = [
    # Landmark-preposition-shaped text with no real proper-noun landmark.
    "The cat was hiding behind Curtains all day.",
    # A bare place mention with a nearby number that ISN'T PIN-shaped
    # (7 digits, not 6) -- reinforcement must not fire.
    "Mumbai's population crossed 12000000 this year.",
]
