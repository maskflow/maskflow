"""_masking primitives (no llama_index import)."""

from __future__ import annotations

import pytest
from maskflow_llamaindex import mask_pii
from maskflow_llamaindex._masking import build_config, new_session, session_mapping

PAN = "ABCPE1234F"  # synthetic, structurally valid
EMAIL = "alice@example.com"


def test_mask_pii_replace_is_reversible() -> None:
    masked, mapping = mask_pii(f"PAN {PAN}, mail {EMAIL}")
    assert PAN not in masked and EMAIL not in masked
    assert mapping == {"<PAN_1>": PAN, "<EMAIL_1>": EMAIL}


def test_mask_pii_redact_has_no_mapping() -> None:
    masked, mapping = mask_pii(f"PAN {PAN}", strategy="redact")
    assert masked == "PAN [REDACTED_PAN]"
    assert mapping == {}


def test_mask_pii_surrogate_is_reversible_with_fake_value() -> None:
    masked, mapping = mask_pii(f"mail {EMAIL}", strategy="surrogate")
    assert EMAIL not in masked and "@" in masked
    assert list(mapping.values()) == [EMAIL]


def test_bad_strategy_rejected() -> None:
    with pytest.raises(ValueError, match="strategy="):
        mask_pii("x", strategy="nonsense")  # type: ignore[arg-type]


def test_build_config_entity_whitelist() -> None:
    cfg = build_config(entities=["EMAIL"])
    with new_session(strategy="replace") as _:
        pass
    import maskflow

    with maskflow.session(config=cfg, ttl_seconds=None) as s:
        out = s.mask(f"PAN {PAN} mail {EMAIL}")
    assert PAN in out and EMAIL not in out


def test_session_mapping_present_in_filters() -> None:
    with new_session() as s:
        s.mask(f"PAN {PAN}")
        s.mask(f"mail {EMAIL}")
        full = session_mapping(s)
        just_pan = session_mapping(s, present_in="see <PAN_1> here")
    assert set(full) == {"<PAN_1>", "<EMAIL_1>"}
    assert set(just_pan) == {"<PAN_1>"}
