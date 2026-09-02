from __future__ import annotations

import pytest
from maskflow_cli.scan.fieldsel import FieldSelector, extract_all, first_str
from maskflow_cli.scan.sources.base import SourceConfigError


def test_simple_key() -> None:
    assert list(FieldSelector.parse("prompt").extract({"prompt": "hi"})) == ["hi"]


def test_nested_key() -> None:
    row = {"data": {"input": "x"}}
    assert list(FieldSelector.parse("data.input").extract(row)) == ["x"]


def test_list_iteration() -> None:
    row = {"messages": [{"content": "a"}, {"content": "b"}, {"role": "x"}]}
    assert list(FieldSelector.parse("messages[].content").extract(row)) == ["a", "b"]


def test_non_string_leaves_skipped() -> None:
    row = {"messages": [{"content": 5}, {"content": None}, {"content": "ok"}]}
    assert list(FieldSelector.parse("messages[].content").extract(row)) == ["ok"]


def test_missing_key_is_empty_not_error() -> None:
    assert list(FieldSelector.parse("nope.deeper").extract({"a": 1})) == []


def test_extract_all_orders_by_selector_then_document() -> None:
    row = {"a": "1", "b": ["2", "3"]}
    sels = (FieldSelector.parse("a"), FieldSelector.parse("b[]"))
    assert extract_all(row, sels) == ["1", "2", "3"]


def test_first_str() -> None:
    assert first_str({"m": "gpt-4o"}, "m") == "gpt-4o"
    assert first_str({}, None) is None


@pytest.mark.parametrize("bad", ["", "a..b", "a[].b[c]", "a b"])
def test_rejects_malformed(bad: str) -> None:
    with pytest.raises(SourceConfigError):
        FieldSelector.parse(bad)


def test_rejects_too_deep() -> None:
    with pytest.raises(SourceConfigError):
        FieldSelector.parse(".".join(["a"] * 40))
