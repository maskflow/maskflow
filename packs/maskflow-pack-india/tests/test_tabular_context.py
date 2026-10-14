"""Column-header context for India types in tabular text (CSV, psql, mysql,
markdown, sqlite). Before maskflow-core 0.8.3 a bare mobile number more than
40 chars below its `mobile` header had no context and leaked.

All identifiers below are SYNTHETIC: generated from a seeded RNG in the
shape of each type (10 digits starting 6-9, etc.), not real people's data.
"""

import random

import maskflow_pack_india  # noqa: F401 -- import side effect registers the India types
import pytest
from maskflow_core.detection import detect
from maskflow_core.entities import PIIType
from maskflow_core.masking import mask, unmask

_RNG = random.Random(20261014)


def _synthetic_mobile() -> str:
    # SYNTHETIC: random 10 digits in TRAI's assignable 6-9 range.
    return str(_RNG.randint(6, 9)) + "".join(str(_RNG.randint(0, 9)) for _ in range(9))


MOBILES = [_synthetic_mobile() for _ in range(500)]


def _found(text: str, pii_type: PIIType) -> set[str]:
    return {s.text for s in detect(text) if s.entity_type == pii_type}


def _csv(header: str, values: list[str]) -> str:
    return f"id,{header},status\n" + "".join(f"{i},{v},ok\n" for i, v in enumerate(values, 1))


class TestMobileHeaderPositive:
    @pytest.mark.parametrize("rows", [3, 5, 500])
    def test_csv_every_row_masked(self, rows: int) -> None:
        values = MOBILES[:rows]
        assert _found(_csv("mobile", values), PIIType.INDIAN_MOBILE) == set(values)

    @pytest.mark.parametrize(
        "header",
        ["mobile", "Mobile No.", "mobile_number", "phone", "PhoneNo", "contact_number",
         "whatsapp", "mob", "mob_no", "ph", "msisdn", "contact", "tel", "मोबाइल"],
    )  # fmt: skip
    def test_header_variants(self, header: str) -> None:
        values = MOBILES[:6]
        assert _found(_csv(header, values), PIIType.INDIAN_MOBILE) == set(values)

    def test_psql(self) -> None:
        a, b, c = MOBILES[:3]
        text = (
            " id | mobile     | status\n----+------------+--------\n"
            f"  1 | {a} | ok\n  2 | {b} | ok\n  3 | {c} | ok\n(3 rows)"
        )
        assert _found(text, PIIType.INDIAN_MOBILE) == {a, b, c}

    def test_mysql_box(self) -> None:
        a, b = MOBILES[:2]
        text = (
            "+----+------------+\n| id | phone_no   |\n+----+------------+\n"
            f"|  1 | {a} |\n|  2 | {b} |\n+----+------------+"
        )
        assert _found(text, PIIType.INDIAN_MOBILE) == {a, b}

    def test_markdown(self) -> None:
        a, b = MOBILES[:2]
        text = f"| Customer | Mobile |\n|---|---|\n| x | {a} |\n| y | {b} |"
        assert _found(text, PIIType.INDIAN_MOBILE) == {a, b}

    def test_call_me_on_free_text(self) -> None:
        a = MOBILES[0]
        assert _found(f"pls call me on {a} after 5", PIIType.INDIAN_MOBILE) == {a}


class TestMobileHeaderNegative:
    @pytest.mark.parametrize(
        "header", ["order_id", "txn_ref", "amount", "invoice_no", "timestamp", "ticket"]
    )
    def test_non_phone_column_not_masked(self, header: str) -> None:
        assert not _found(_csv(header, MOBILES[:6]), PIIType.INDIAN_MOBILE)

    def test_headerless_numeric_table_not_masked(self) -> None:
        text = "".join(f"{i},{v},7\n" for i, v in enumerate(MOBILES[:6], 1))
        assert not _found(text, PIIType.INDIAN_MOBILE)


class TestMobileHeaderHardNegative:
    @pytest.mark.parametrize(
        "header", ["mobile_app_build", "mobile_app_version", "phone_model", "test_mobile",
                   "sample_phone", "dummy_contact", "mock_msisdn"],
    )  # fmt: skip
    def test_qualified_header_not_masked(self, header: str) -> None:
        assert not _found(_csv(header, MOBILES[:6]), PIIType.INDIAN_MOBILE)


class TestOtherTypes:
    def test_bank_account_column(self) -> None:
        # SYNTHETIC 11-digit account-shaped numbers.
        accounts = [str(_RNG.randint(10**10, 10**11 - 1)) for _ in range(6)]
        assert _found(_csv("account_no", accounts), PIIType.BANK_ACCOUNT_IN) == set(accounts)
        assert _found(_csv("acc_no", accounts), PIIType.BANK_ACCOUNT_IN) == set(accounts)

    @pytest.mark.parametrize("header", ["account_id", "account_type_code", "user_account_id"])
    def test_internal_account_id_not_bank_account(self, header: str) -> None:
        accounts = [str(_RNG.randint(10**10, 10**11 - 1)) for _ in range(6)]
        assert not _found(_csv(header, accounts), PIIType.BANK_ACCOUNT_IN)

    def test_pin_code_column(self) -> None:
        # SYNTHETIC 6-digit codes in India Post's 1-8 zone range.
        pins = [str(_RNG.randint(1, 8)) + f"{_RNG.randint(0, 99999):05d}" for _ in range(6)]
        assert _found(_csv("zipcode", pins), PIIType.PIN_CODE) == set(pins)
        assert not _found(_csv("batch", pins), PIIType.PIN_CODE)


class TestPersonNameHeader:
    def _scores(self, header: str, cells: list[str]) -> dict[str, float]:
        text = _csv(header, cells)
        return {
            s.text: s.score
            for s in detect(text, min_confidence=0.0)
            if s.entity_type == PIIType.PERSON_NAME
        }

    def test_name_column_never_lowers_scores(self) -> None:
        cells = ["Ravi Kumar", "Priya Sharma", "Arjun Mehta", "Kavya Iyer"]
        baseline = self._scores("col", cells)
        boosted = self._scores("customer_name", cells)
        for name, score in baseline.items():
            assert boosted.get(name, 0.0) >= score

    @pytest.mark.parametrize("header", ["product_name", "file_name", "branch_name", "company_name"])
    def test_qualified_name_headers_never_raise_scores(self, header: str) -> None:
        cells = ["Ravi Shampoo", "Lakshmi Gold", "Ganesh Traders", "Krishna Dairy"]
        baseline = self._scores("col", cells)
        for name, score in self._scores(header, cells).items():
            assert score <= baseline.get(name, score)


@pytest.mark.parametrize(
    "text",
    [
        _csv("mobile", MOBILES[:20]),
        _csv("Mobile No.", MOBILES[:5]).replace("\n", "\r\n"),
        "| Name | Phone |\n|---|---|\n| रवि | " + MOBILES[0] + " |\n| 😀 | " + MOBILES[1] + " |",
        _csv("mobile", ["<INDIAN_MOBILE_1>", MOBILES[2], MOBILES[3]]),
    ],
    ids=["csv", "crlf", "unicode-markdown", "placeholder-lookalike"],
)
def test_round_trip(text: str) -> None:
    result = mask(text)
    assert unmask(result.masked_text, result.mapping) == text
