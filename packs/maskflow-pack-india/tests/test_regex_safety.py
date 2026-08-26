"""Guards against unbounded-regex backtracking blowing up on adversarial
input (CLAUDE.md rule #3). None of this pack's patterns use unbounded
quantifiers -- every digit/letter run is a fixed {n} count except
UPI_VPA_RE's local-part ({2,256}), which is still bounded -- but a timing
budget is asserted anyway rather than just eyeballing the regex shape,
matching maskflow-pack-intl's convention (test_regex_safety.py).
"""

import time

import pytest
from maskflow_pack_india.patterns import (
    AADHAAR_MASKED_RE,
    AADHAAR_RE,
    AADHAAR_VID_RE,
    ABHA_ADDRESS_RE,
    ABHA_NUMBER_RE,
    BANK_ACCOUNT_IN_RE,
    DRIVING_LICENCE_RE,
    GSTIN_RE,
    IFSC_RE,
    INDIAN_MOBILE_RE,
    INDIAN_PASSPORT_MRZ_RE,
    INDIAN_PASSPORT_RE,
    PAN_EMBEDDED_IN_GSTIN_RE,
    PAN_RE,
    PIN_CODE_RE,
    UPI_VPA_RE,
    VEHICLE_REG_RE,
    VOTER_ID_RE,
)

TIME_BUDGET_SECONDS = 1.0

ALL_PATTERNS = (
    AADHAAR_RE,
    AADHAAR_VID_RE,
    AADHAAR_MASKED_RE,
    PAN_RE,
    PAN_EMBEDDED_IN_GSTIN_RE,
    GSTIN_RE,
    IFSC_RE,
    UPI_VPA_RE,
    INDIAN_MOBILE_RE,
    PIN_CODE_RE,
    VOTER_ID_RE,
    INDIAN_PASSPORT_RE,
    INDIAN_PASSPORT_MRZ_RE,
    DRIVING_LICENCE_RE,
    VEHICLE_REG_RE,
    ABHA_NUMBER_RE,
    ABHA_ADDRESS_RE,
    BANK_ACCOUNT_IN_RE,
)


@pytest.mark.benchmark
@pytest.mark.parametrize("pattern", ALL_PATTERNS, ids=[p.pattern for p in ALL_PATTERNS])
def test_stays_linear_on_long_digit_run(pattern: object) -> None:
    adversarial = "23456789" * 20_000  # 160,000 digits, no valid match anywhere

    start = time.monotonic()
    pattern.findall(adversarial)  # type: ignore[attr-defined]
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"{pattern.pattern!r} took {elapsed:.2f}s on a long digit run, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )


@pytest.mark.benchmark
def test_upi_vpa_stays_linear_on_long_local_part_without_at_sign() -> None:
    # No '@' anywhere -- forces the engine to try (and fail) the local-part
    # class at every offset across a long run.
    adversarial = "a" * 100_000 + " no at sign here"

    start = time.monotonic()
    UPI_VPA_RE.findall(adversarial)
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"UPI_VPA_RE took {elapsed:.2f}s on adversarial input, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )


@pytest.mark.benchmark
def test_aadhaar_stays_linear_on_long_alternating_separator_run() -> None:
    # Exercises the \2 backreference against a long run that almost, but
    # never quite, satisfies the consistent-separator requirement.
    adversarial = "2345-6789 " * 20_000

    start = time.monotonic()
    AADHAAR_RE.findall(adversarial)
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"AADHAAR_RE took {elapsed:.2f}s on adversarial input, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )


@pytest.mark.benchmark
def test_driving_licence_stays_linear_on_long_alternating_separator_run() -> None:
    # Same \2 backreference hazard as AADHAAR_RE, exercised against a run
    # that is state-code-and-year-shaped but never satisfies the
    # consistent-separator requirement.
    adversarial = "MH12-2011 0012345 " * 20_000

    start = time.monotonic()
    DRIVING_LICENCE_RE.findall(adversarial)
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"DRIVING_LICENCE_RE took {elapsed:.2f}s on adversarial input, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )


@pytest.mark.benchmark
def test_vehicle_reg_stays_linear_on_long_near_miss_run() -> None:
    adversarial = "MH-12-AB-123 " * 20_000  # one digit short of matching, every time

    start = time.monotonic()
    VEHICLE_REG_RE.findall(adversarial)
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"VEHICLE_REG_RE took {elapsed:.2f}s on adversarial input, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )


@pytest.mark.benchmark
def test_indian_passport_mrz_stays_linear_on_long_near_miss_multiline_input() -> None:
    # A repeated line-1-shaped run with no line 2 ever following it -- forces
    # the engine to attempt (and fail) the full two-line match at every
    # newline across a long input.
    adversarial = ("P<INDSHARMA<<ROHIT<<<<<<<<<<<<<<<<<<<<<<<<<<\n") * 20_000

    start = time.monotonic()
    INDIAN_PASSPORT_MRZ_RE.findall(adversarial)
    elapsed = time.monotonic() - start

    assert elapsed < TIME_BUDGET_SECONDS, (
        f"INDIAN_PASSPORT_MRZ_RE took {elapsed:.2f}s on adversarial input, "
        f"expected < {TIME_BUDGET_SECONDS}s -- possible backtracking regression."
    )
