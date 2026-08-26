import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import maskflow_pack_india  # noqa: F401 -- import side effect registers AADHAAR/AADHAAR_MASKED
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType, Span
from maskflow_pack_india.checksums import verhoeff_generate


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_unspaced_12_digit(self) -> None:
        assert (PIIType.AADHAAR, "234567890124") in _detected(
            "My Aadhaar number is 234567890124, please verify."
        )

    def test_spaced_form(self) -> None:
        assert (PIIType.AADHAAR, "2345 6789 0124") in _detected(
            "Aadhaar: 2345 6789 0124 submitted."
        )

    def test_hyphenated_form(self) -> None:
        assert (PIIType.AADHAAR, "7890-1234-5674") in _detected(
            "Aadhar no. 7890-1234-5674 was submitted for KYC."
        )

    def test_16_digit_vid(self) -> None:
        assert (PIIType.AADHAAR, "2345678901234565") in _detected(
            "UIDAI VID on file: 2345678901234565."
        )

    def test_masked_form_with_context(self) -> None:
        found = _detected("Your masked Aadhaar on file: XXXX XXXX 9012.")
        assert (PIIType.AADHAAR_MASKED, "XXXX XXXX 9012") in found

    def test_masked_form_needs_context_to_clear_threshold(self) -> None:
        # No "aadhaar"/"uidai"/etc. keyword nearby -- base confidence (0.45)
        # alone is below detect()'s default 0.5 threshold by design.
        found = _detected("Reference on file: XXXX XXXX 9012 for this ticket.")
        assert (PIIType.AADHAAR_MASKED, "XXXX XXXX 9012") not in found

    def test_hindi_context_boosts_detection(self) -> None:
        found = _detected("मेरा आधार नंबर 345678901238 है।")
        assert (PIIType.AADHAAR, "345678901238") in found


class TestInvalidChecksum:
    def test_bad_verhoeff_digit_is_rejected(self) -> None:
        # 234567890124 is Verhoeff-valid; corrupting the last digit is not.
        found = _detected("Applicant number 234567890125 was rejected during validation.")
        assert not any(t == PIIType.AADHAAR for t, _ in found)


class TestFormatVariants:
    def test_leading_zero_never_matches(self) -> None:
        found = _detected("Reference 023456789012 does not match our records.")
        assert not any(t == PIIType.AADHAAR for t, _ in found)

    def test_leading_one_never_matches(self) -> None:
        found = _detected("Reference 123456789012 does not match our records.")
        assert not any(t == PIIType.AADHAAR for t, _ in found)

    def test_mixed_separators_do_not_match(self) -> None:
        # Space then hyphen -- AADHAAR_RE's backreference requires the same
        # separator (or none) throughout; this is a deliberate non-match.
        base11 = "23456789012"
        check = verhoeff_generate(base11)
        text = f"Aadhaar 2345 6789-{base11[8:]}{check} noted."
        found = _detected(text)
        assert not any(t == PIIType.AADHAAR for t, _ in found)


class TestHardNegatives:
    def test_embedded_in_longer_digit_run_does_not_match(self) -> None:
        found = _detected("Order number 234567890124567 was shipped today.")
        assert not any(t == PIIType.AADHAAR for t, _ in found)

    def test_plain_prose_produces_no_aadhaar_finding(self) -> None:
        found = _detected("Please review the quarterly report before Friday.")
        assert not any(t in (PIIType.AADHAAR, PIIType.AADHAAR_MASKED) for t, _ in found)


class TestNoRawAadhaarLeak:
    """CLAUDE.md rule 1, called out explicitly for AADHAAR: no Aadhaar value
    may appear in any log or test-failure message. test_leak_gate_india.py
    covers the whole-session log/exception pool; this covers the direct
    repr() mechanism Span.text's repr=False field relies on."""

    def test_span_repr_never_contains_the_aadhaar_digits(self) -> None:
        real_looking_digits = "234567890124"  # Verhoeff-valid, synthetic
        span = Span(
            start=0,
            end=len(real_looking_digits),
            entity_type=PIIType.AADHAAR,
            score=0.95,
            recognizer="pattern:AADHAAR",
            text=real_looking_digits,
            validated=True,
        )
        assert real_looking_digits not in repr(span)

    def test_detect_call_never_raises_with_digits_in_message(self) -> None:
        # detect() shouldn't raise at all here, but if a future regression
        # made it raise, the exception text must never embed the value --
        # assert on the *type* of failure, never format an assert message
        # with the raw digits (see fixtures/pii_samples.py's own comments).
        try:
            detect("My Aadhaar number is 234567890124, please verify.")
        except Exception as exc:  # pragma: no cover -- defensive, not expected
            assert "234567890124" not in str(exc)
