"""Structural checks -- no full corpus run, fast."""

from __future__ import annotations

import json

import pytest

from bench.integrations.adapters import (
    ALL_ADAPTERS,
    LiteLLMAdapter,
    MaskRun,
    McpAdapter,
)
from bench.integrations.scoring import ParityTally, compare

_DOC = "KYC for Rahul Kumar: PAN ABCPE1234F, email rahul@example.com, GSTIN 27AAAPR6360Q4ZB"


def test_all_adapters_have_a_name_and_availability() -> None:
    names = {a.name for a in ALL_ADAPTERS}
    assert names == {"core", "litellm", "langchain", "llamaindex", "mcp"}
    for a in ALL_ADAPTERS:
        ok, reason = a.available()
        assert isinstance(ok, bool) and isinstance(reason, str)


def test_pairs_parses_type_from_token_regardless_of_counter_or_nonce() -> None:
    run = MaskRun(
        masked_text="x",
        token_map={
            "<PAN_1>": "AAAAA0000A",
            "<AADHAAR_2_a4f9>": "111122223333",
            "<not a token>": "z",
        },
        roundtrip="x",
    )
    assert run.pairs == frozenset({("PAN", "AAAAA0000A"), ("AADHAAR", "111122223333")})


def test_compare_flags_a_deliberately_broken_run() -> None:
    """If a wrapper drops a finding or invents one, compare() must record it
    -- proof the gate isn't passing trivially."""
    core = MaskRun("m", {"<PAN_1>": "AAAAA0000A", "<EMAIL_1>": "a@b.com"}, "orig")
    missed = MaskRun("m", {"<PAN_1>": "AAAAA0000A"}, "orig")  # dropped the email
    extra_map = {**core.token_map, "<PHONE_1>": "+1-202-555-0100"}
    extra = MaskRun("m", extra_map, "wrong")  # invented a PHONE + broken round-trip

    t = ParityTally(name="broken")
    compare(t, "d1", "orig", missed, core)
    compare(t, "d2", "orig", extra, core)
    assert t.detection_matches == 0
    assert t.missed_types["EMAIL"] == 1
    assert t.extra_types["PHONE"] == 1
    assert t.roundtrip_fail_docs == ["d2"]


def test_litellm_tool_argument_json_stays_valid_and_round_trips() -> None:
    pytest.importorskip("maskflow_litellm._masking")
    from maskflow import Session
    from maskflow_litellm._masking import _mask_json_string, _unmask_arguments

    with Session(ttl_seconds=None) as s:
        raw = json.dumps({"customer": "Rahul Kumar", "pan": "ABCPE1234F", "amount": 500})
        masked = _mask_json_string(s, raw)
        assert json.loads(masked)  # still valid JSON
        assert "Rahul Kumar" not in masked and "ABCPE1234F" not in masked
        restored = json.loads(_unmask_arguments(masked, s.mapping))
        assert restored == {"customer": "Rahul Kumar", "pan": "ABCPE1234F", "amount": 500}


def test_mcp_nested_arguments_round_trip_and_keys_untouched() -> None:
    pytest.importorskip("maskflow_mcp._masking")
    from maskflow import Session
    from maskflow_mcp._masking import mask_arguments, unmask_json

    with Session(ttl_seconds=None) as s:
        args = {"pan_field": "ABCPE1234F", "nested": {"email": "rahul@example.com"}, "n": 3}
        masked = mask_arguments(s, args)
        assert set(masked) == set(args)  # keys never masked
        assert masked["nested"]["email"] != "rahul@example.com"
        assert unmask_json(s, masked) == args


def test_litellm_and_mcp_adapters_agree_with_each_other_on_a_doc() -> None:
    lite, mcp = LiteLLMAdapter(), McpAdapter()
    if not lite.available()[0] or not mcp.available()[0]:
        return
    assert lite.run(_DOC).pairs == mcp.run(_DOC).pairs
