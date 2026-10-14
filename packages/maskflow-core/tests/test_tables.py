"""tables.find_tables(): block detection and header lookup across the table
shapes a coding agent or a log export actually produces. Cell values are
synthetic placeholders (NUM-*), not PII."""

import time
from collections.abc import Callable

import pytest
from maskflow_core.tables import MAX_LINES, find_tables


def _header_at(text: str, needle: str) -> str | None:
    start = text.index(needle)
    return find_tables(text).header_for(start, start + len(needle))


CSV = "id,mobile,status\n1,NUM-1,ok\n2,NUM-2,ok\n3,NUM-3,ok\n4,NUM-4,ok\n5,NUM-5,ok\n"


@pytest.mark.parametrize(
    "text",
    [
        CSV,
        CSV.replace(",", "\t"),
        CSV.replace(",", ";"),
        CSV.replace("\n", "\r\n"),
        # psql
        "id | mobile | status\n----+--------+-------\n 1 | NUM-1 | ok\n 2 | NUM-5 | ok\n(2 rows)",
        # mysql box
        "+----+--------+\n| id | mobile |\n+----+--------+\n"
        "| 1 | NUM-1 |\n| 2 | NUM-5 |\n+----+--------+",
        # markdown
        "| id | mobile |\n|---|:---|\n| 1 | NUM-1 |\n| 2 | NUM-5 |",
        # sqlite -header
        "id|mobile|status\n1|NUM-1|ok\n2|NUM-5|ok",
    ],
    ids=["csv", "tsv", "semicolon", "crlf", "psql", "mysql", "markdown", "sqlite"],
)
def test_header_found_for_every_table_shape(text: str) -> None:
    assert _header_at(text, "NUM-5") == "mobile"


def test_header_found_far_below_header_row() -> None:
    rows = "\n".join(f"{i},NUM-{i},ok" for i in range(1, 501))
    text = "id,mobile,status\n" + rows
    assert _header_at(text, "NUM-500") == "mobile"


def test_quoted_csv_cell_with_delimiter_inside() -> None:
    text = 'name,mobile\n"Kumar, R",NUM-1\n"Iyer, S",NUM-2\n"Das, P",NUM-3'
    assert _header_at(text, "NUM-3") == "mobile"


def test_quoted_header_is_unquoted() -> None:
    text = '"id","mobile"\n"1","NUM-1"\n"2","NUM-2"'
    assert _header_at(text, "NUM-2") == "mobile"


def test_devanagari_header() -> None:
    text = "क्रम,मोबाइल\n1,NUM-1\n2,NUM-2"
    assert _header_at(text, "NUM-2") == "मोबाइल"


def test_table_inside_prose_and_two_tables() -> None:
    text = (
        "Here is the export you asked for.\n\n"
        "id,mobile\n1,NUM-1\n2,NUM-2\n\n"
        "And the accounts:\n\n"
        "id,account_no\n1,NUM-3\n2,NUM-4\n\n"
        "Let me know if anything is off."
    )
    assert _header_at(text, "NUM-2") == "mobile"
    assert _header_at(text, "NUM-4") == "account_no"


def test_header_row_itself_has_no_header() -> None:
    assert _header_at(CSV, "mobile") is None


def test_span_crossing_cells_has_no_header() -> None:
    start = CSV.index("1,NUM-1")
    assert find_tables(CSV).header_for(start, start + len("1,NUM-1")) is None


@pytest.mark.parametrize(
    "text",
    [
        "id|name|mobile|status\n4|R|NUM-1|stuck",  # sqlite3 -header, one row
        "id,name,mobile\n4,R,NUM-1\n",
        " id | name | mobile\n----+------+-------\n  4 | R | NUM-1\n(1 row)",  # psql
        "| id | name | mobile |\n|---|---|---|\n| 4 | R | NUM-1 |",
    ],
    ids=["sqlite", "csv", "psql", "markdown"],
)
def test_single_row_lookup_with_three_columns_is_a_table(text: str) -> None:
    assert _header_at(text, "NUM-1") == "mobile"


class TestNotATable:
    def test_single_line(self) -> None:
        assert not find_tables("id,mobile,NUM-1")

    def test_header_plus_one_row_is_too_short(self) -> None:
        assert not find_tables("id,mobile\n1,NUM-1")

    def test_numeric_first_row_is_not_a_header(self) -> None:
        assert not find_tables("1,NUM-1\n2,NUM-2\n3,NUM-3")

    def test_prose_with_commas(self) -> None:
        text = (
            "Hello team, please review the attached report before Friday.\n"
            "Thanks, and let me know if the numbers look odd to you.\n"
            "Regards, the platform team at the head office in Pune."
        )
        assert not find_tables(text)

    def test_two_prose_lines_with_commas(self) -> None:
        text = (
            "Thanks for the update, the numbers look fine, ship it today.\n"
            "Also, once merged, ping the team so they can rebase."
        )
        assert not find_tables(text)

    def test_ragged_rows_end_the_block(self) -> None:
        text = "id,mobile\n1,NUM-1\n2,NUM-2,extra\n3,NUM-3"
        assert _header_at(text, "NUM-3") is None

    def test_unbalanced_quote_line_breaks_the_block(self) -> None:
        text = 'id,note\n1,"open\n2,closed"\n3,x'
        assert _header_at(text, "x") is None

    def test_line_cap(self) -> None:
        text = "id,mobile\n" + "1,NUM-1\n" * (MAX_LINES + 1)
        assert not find_tables(text)


def _scan_seconds(text: str) -> float:
    find_tables.cache_clear()
    started = time.perf_counter()
    find_tables(text)
    return time.perf_counter() - started


@pytest.mark.benchmark
@pytest.mark.parametrize(
    "make",
    [
        lambda n: "id,mobile,status\n" + "".join(f"{i},NUM-{i},ok\n" for i in range(n)),
        lambda n: ('|,;\t"' * 400 + "\n") * (n // 50),
    ],
    ids=["csv", "delimiter-soup"],
)
def test_scan_time_grows_linearly(make: Callable[[int], str]) -> None:
    # Growth ratio, not wall-clock: CI runs this under coverage on slow
    # runners. 4x the input should cost ~4x (linear), never ~16x (quadratic).
    small, large = make(10_000), make(40_000)
    _scan_seconds(small)  # warm-up
    ratio = _scan_seconds(large) / max(_scan_seconds(small), 1e-4)
    assert ratio < 8, f"4x input took {ratio:.1f}x as long"
