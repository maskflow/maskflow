"""save/load_deanonymizer_mapping + shape parity with the Presidio anonymizer."""

from __future__ import annotations

import json

import pytest
from maskflow_langchain import MaskflowReversibleAnonymizer
from maskflow_langchain._mapping import merge_into

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def test_save_load_json_round_trip(tmp_path) -> None:
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}, mail {EMAIL}")
    path = tmp_path / "mapping.json"
    a.save_deanonymizer_mapping(path)

    saved = json.loads(path.read_text())
    assert saved == {"PAN": {"<PAN_1>": PAN}, "EMAIL": {"<EMAIL_1>": EMAIL}}

    # a fresh anonymizer can deanonymize from the loaded file
    b = MaskflowReversibleAnonymizer()
    b.load_deanonymizer_mapping(path)
    assert b.deanonymize("ref <PAN_1> and <EMAIL_1>") == f"ref {PAN} and {EMAIL}"


def test_save_load_yaml_round_trip(tmp_path) -> None:
    pytest.importorskip("yaml")
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}")
    path = tmp_path / "mapping.yaml"
    a.save_deanonymizer_mapping(path)
    b = MaskflowReversibleAnonymizer()
    b.load_deanonymizer_mapping(path)
    assert b.deanonymize("<PAN_1>") == PAN


def test_unknown_suffix_rejected(tmp_path) -> None:
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}")
    with pytest.raises(ValueError, match="expected .json"):
        a.save_deanonymizer_mapping(tmp_path / "x.txt")


def test_loaded_mapping_merges_with_session_mapping(tmp_path) -> None:
    path = tmp_path / "m.json"
    path.write_text(json.dumps({"PHONE": {"<PHONE_1>": "+1-202-555-0100"}}))
    a = MaskflowReversibleAnonymizer()
    a.load_deanonymizer_mapping(path)
    a.anonymize(f"PAN {PAN}")
    m = a.deanonymizer_mapping
    assert m["PHONE"] == {"<PHONE_1>": "+1-202-555-0100"}
    assert m["PAN"] == {"<PAN_1>": PAN}


def test_mapping_is_the_langchain_nested_shape() -> None:
    # MappingDataType == Dict[str, Dict[str, str]]; every value is a str.
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}, mail {EMAIL}")
    m = a.deanonymizer_mapping
    assert all(
        isinstance(et, str)
        and isinstance(inner, dict)
        and all(isinstance(k, str) and isinstance(v, str) for k, v in inner.items())
        for et, inner in m.items()
    )


def test_merge_into_does_not_overwrite() -> None:
    dst = {"PAN": {"<PAN_1>": "AAAAA0000A"}}
    merge_into(dst, {"PAN": {"<PAN_1>": "BBBBB1111B", "<PAN_2>": "CCCCC2222C"}})
    assert dst["PAN"] == {"<PAN_1>": "AAAAA0000A", "<PAN_2>": "CCCCC2222C"}
