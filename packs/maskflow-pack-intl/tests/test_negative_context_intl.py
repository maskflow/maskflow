"""Negative-context suppression (#63): an illustrative-value marker within
40 chars of a candidate lowers its confidence by 0.3 -- enough to drop the
shape-only, context-gated matches (SSN_PLAIN, a bare IPv4) while validated /
high-confidence structural matches (EMAIL, dashed SSN) stay above threshold.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import maskflow_pack_intl  # noqa: F401 -- import side effect registers the pack + negative keywords
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _types(text: str) -> set[PIIType]:
    return {s.entity_type for s in detect(text)}


class TestSuppressesContextGatedTypes:
    def test_plain_ssn_with_keyword_but_example_marker_is_dropped(self) -> None:
        # "ssn" context lifts SSN_PLAIN (0.35) over the bar; "for example" -0.3 undoes it.
        assert PIIType.SSN in _types("My SSN is 234567890 for verification.")
        assert PIIType.SSN not in _types("For example, an SSN like 234567890 is nine digits.")

    def test_bare_ipv4_near_sample_marker_is_dropped(self) -> None:
        assert PIIType.IP_ADDRESS in _types("The server replied from 192.168.14.22 last night.")
        assert PIIType.IP_ADDRESS not in _types(
            "For example, a private address is 192.168.14.22 on most routers."
        )


class TestHighConfidenceMatchesSurvive:
    def test_email_near_example_marker_is_still_masked(self) -> None:
        assert PIIType.EMAIL in _types("For example, email jane.doe@contoso.com for access.")

    def test_dashed_ssn_near_example_marker_is_still_masked(self) -> None:
        assert PIIType.SSN in _types("For example, an SSN is formatted 234-56-7890.")

    def test_no_suppression_when_marker_is_far_from_the_match(self) -> None:
        # "for example" is present but well beyond the 40-char window.
        text = (
            "For example, the onboarding checklist walks a new hire through every step. "
            "My SSN is 234567890 on the signed form."
        )
        assert PIIType.SSN in _types(text)
