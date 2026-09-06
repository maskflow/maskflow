"""MaskFlow release rule #1: raw PII never reaches logs, repr, callback
state, or the in-memory mapping structure's keys."""

from __future__ import annotations

import logging

import pytest
from langchain_core.language_models.fake import FakeListLLM
from maskflow_langchain import MaskflowLeakGuardCallback, MaskflowReversibleAnonymizer

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"
MOBILE = "9812345678"
SECRETS = (PAN, EMAIL, MOBILE)


def _clean(blob: str) -> None:
    for s in SECRETS:
        assert s not in blob


@pytest.mark.leak
def test_anonymizer_repr_has_no_pii() -> None:
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}, mail {EMAIL}, mobile {MOBILE}")
    _clean(repr(a))
    _clean(repr(a.deanonymizer))
    _clean(repr(a._session))  # type: ignore[attr-defined]


@pytest.mark.leak
def test_leak_guard_state_and_error_have_no_values() -> None:
    g = MaskflowLeakGuardCallback(raise_on_prompt_pii=False)
    llm = FakeListLLM(responses=[f"echo {EMAIL}"])
    llm.invoke(f"PAN {PAN} mobile {MOBILE}", config={"callbacks": [g]})
    _clean(repr(g.summary()))
    _clean(repr(g.prompt_detections))
    _clean(repr(g.completion_detections))


@pytest.mark.leak
def test_callback_logging_has_no_pii(caplog: pytest.LogCaptureFixture) -> None:
    g = MaskflowLeakGuardCallback(raise_on_prompt_pii=True)
    llm = FakeListLLM(responses=["x"])
    with caplog.at_level(logging.DEBUG), pytest.raises(Exception):  # noqa: B017,PT011
        llm.invoke(f"PAN {PAN} mail {EMAIL}", config={"callbacks": [g]})
    _clean(caplog.text)


@pytest.mark.leak
def test_deanonymizer_mapping_values_are_the_only_place_pii_lives() -> None:
    # The nested mapping's *values* are the originals by design (that is what
    # a reversible mapping is). Its keys (entity types + placeholders) are not.
    a = MaskflowReversibleAnonymizer()
    a.anonymize(f"PAN {PAN}")
    m = a.deanonymizer_mapping
    for entity_type, inner in m.items():
        assert PAN not in entity_type
        for placeholder in inner:
            assert PAN not in placeholder
