"""_masking primitives (no fastmcp import)."""

from __future__ import annotations

import maskflow
from maskflow_mcp import mask_arguments, unmask_json, unmask_text
from maskflow_mcp._masking import mask_new_json, parse_json_string

PAN = "ABCPE1234F"  # synthetic, structurally valid
EMAIL = "alice@example.com"


def _session():
    return maskflow.session(ttl_seconds=None, config=maskflow.RootConfig())


def test_mask_arguments_walks_values_not_keys() -> None:
    s = _session()
    args = {"name": "Ramesh Kumar", "PAN": PAN, "count": 3, "nested": {"email": EMAIL}}
    out = mask_arguments(s, args)
    assert out["name"] != "Ramesh Kumar" and "<PERSON_NAME_1>" in out["name"]
    assert out["PAN"] == "<PAN_1>"
    assert out["count"] == 3
    assert out["nested"]["email"] == "<EMAIL_1>"
    assert set(out) == {"name", "PAN", "count", "nested"}  # keys unchanged


def test_mask_arguments_empty() -> None:
    assert mask_arguments(_session(), None) == {}
    assert mask_arguments(_session(), {}) == {}


def test_unmask_round_trip() -> None:
    s = _session()
    masked = mask_arguments(s, {"q": f"look up {EMAIL}"})
    assert unmask_text(s, f"found {masked['q']}") == f"found look up {EMAIL}"
    assert unmask_json(s, {"a": [masked["q"]], "b": 1}) == {"a": [f"look up {EMAIL}"], "b": 1}


def test_stable_identity_across_calls() -> None:
    s = _session()
    a = mask_arguments(s, {"x": f"PAN {PAN}"})
    b = mask_arguments(s, {"y": f"PAN {PAN} again"})
    assert "<PAN_1>" in a["x"] and "<PAN_1>" in b["y"]


def test_mask_new_json() -> None:
    s = _session()
    out = mask_new_json(s, {"result": f"customer {EMAIL}"})
    assert EMAIL not in out["result"] and "<EMAIL_1>" in out["result"]


def test_parse_json_string() -> None:
    assert parse_json_string('{"a": 1}') == (True, {"a": 1})
    assert parse_json_string("not json") == (False, "not json")
