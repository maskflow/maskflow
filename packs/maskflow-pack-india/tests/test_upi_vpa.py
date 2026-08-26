import maskflow_pack_india  # noqa: F401 -- import side effect registers UPI_VPA
import pytest
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType


def _detected(text: str) -> set[tuple[PIIType, str]]:
    return {(s.entity_type, s.text) for s in detect(text)}


class TestValid:
    def test_google_pay_hdfc_handle(self) -> None:
        assert (PIIType.UPI_VPA, "priya.sharma@okhdfcbank") in _detected(
            "Pay to UPI ID priya.sharma@okhdfcbank for the order."
        )

    def test_phonepe_ybl_handle(self) -> None:
        assert (PIIType.UPI_VPA, "raj_kumar@ybl") in _detected("VPA: raj_kumar@ybl")

    def test_paytm_handle(self) -> None:
        assert (PIIType.UPI_VPA, "anita.rao@paytm") in _detected("UPI id anita.rao@paytm noted.")

    def test_axis_handle(self) -> None:
        assert (PIIType.UPI_VPA, "vikram@oksbi") in _detected("gpay handle vikram@oksbi shared.")

    def test_hindi_context(self) -> None:
        assert (PIIType.UPI_VPA, "deepa.iyer@okaxis") in _detected(
            "यूपीआई आईडी deepa.iyer@okaxis है।"
        )


class TestHardNegatives:
    def test_unknown_handle_rejected(self) -> None:
        found = _detected("Contact handle raviteja@randomhandle isn't a real payment address.")
        assert not any(t == PIIType.UPI_VPA for t, _ in found)

    def test_email_domain_never_matches_as_upi(self) -> None:
        found = _detected("Reach out at priya.sharma@gmail.com anytime.")
        assert not any(t == PIIType.UPI_VPA for t, _ in found)


class TestCrossPackPrecisionAgainstEmail:
    """Explicit precision check requested for UPI_VPA: a real email domain
    must be claimed by EMAIL (maskflow-pack-intl), a known NPCI handle must
    be claimed by UPI_VPA (this pack) -- never the other type, never both.

    maskflow_core.registry's PATTERNS dict is process-global, so importing
    maskflow_pack_intl here registers EMAIL for the rest of this test
    session too -- harmless for every other test in this file/package (none
    of them assert EMAIL's *absence*), and this module is the last one
    pytest collects alphabetically, so it doesn't affect tests that already
    ran.
    """

    def test_gmail_dot_com_is_email_not_upi(self) -> None:
        pytest.importorskip("maskflow_pack_intl")
        import maskflow_pack_intl  # noqa: F401 -- registers EMAIL

        found = _detected("You can reach me at name@gmail.com anytime.")
        assert (PIIType.EMAIL, "name@gmail.com") in found
        assert not any(t == PIIType.UPI_VPA for t, _ in found)

    def test_okhdfcbank_is_upi_not_email(self) -> None:
        pytest.importorskip("maskflow_pack_intl")
        import maskflow_pack_intl  # noqa: F401 -- registers EMAIL

        found = _detected("Pay to name@okhdfcbank for the order.")
        assert (PIIType.UPI_VPA, "name@okhdfcbank") in found
        assert not any(t == PIIType.EMAIL for t, _ in found)


class TestFormatVariants:
    def test_no_at_sign_never_matches(self) -> None:
        found = _detected("Handle raviteja-okhdfcbank was mentioned.")
        assert not any(t == PIIType.UPI_VPA for t, _ in found)
