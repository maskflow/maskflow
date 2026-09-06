"""MaskflowLeakGuardCallback: audit tally + optional fail-closed."""

from __future__ import annotations

import pytest
from langchain_core.language_models.fake import FakeListLLM
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, HumanMessage
from maskflow_langchain import (
    AsyncMaskflowLeakGuardCallback,
    MaskflowLeakGuardCallback,
    MaskflowPIILeakError,
)

PAN = "ABCPE1234F"
EMAIL = "alice@example.com"


def test_audit_only_does_not_block() -> None:
    g = MaskflowLeakGuardCallback()  # raise_on_prompt_pii defaults False
    llm = FakeListLLM(responses=[f"the mail was {EMAIL}"])
    out = llm.invoke(f"my PAN is {PAN}", config={"callbacks": [g]})
    assert out == f"the mail was {EMAIL}"
    assert g.summary()["prompt"] == {"PAN": 1}
    assert g.summary()["completion"] == {"EMAIL": 1}


def test_raise_on_prompt_pii_aborts_chat_model() -> None:
    g = MaskflowLeakGuardCallback(raise_on_prompt_pii=True)
    llm = FakeMessagesListChatModel(responses=[AIMessage("ok")])
    with pytest.raises(MaskflowPIILeakError) as exc:
        llm.invoke([HumanMessage(f"PAN {PAN}")], config={"callbacks": [g]})
    assert exc.value.counts == {"PAN": 1}


def test_clean_prompt_passes_when_guard_on() -> None:
    g = MaskflowLeakGuardCallback(raise_on_prompt_pii=True)
    llm = FakeMessagesListChatModel(responses=[AIMessage("fine")])
    out = llm.invoke([HumanMessage("nothing sensitive here")], config={"callbacks": [g]})
    assert out.content == "fine"
    assert g.summary()["prompt"] == {}


def test_error_carries_no_values() -> None:
    g = MaskflowLeakGuardCallback(raise_on_prompt_pii=True)
    llm = FakeListLLM(responses=["x"])
    with pytest.raises(MaskflowPIILeakError) as exc:
        llm.invoke(f"PAN {PAN} mail {EMAIL}", config={"callbacks": [g]})
    assert PAN not in str(exc.value)
    assert EMAIL not in str(exc.value)


def test_cumulative_across_calls() -> None:
    g = MaskflowLeakGuardCallback()
    llm = FakeListLLM(responses=["a", "b"])
    llm.invoke(f"PAN {PAN}", config={"callbacks": [g]})
    llm.invoke(f"PAN {PAN} again", config={"callbacks": [g]})
    assert g.summary()["prompt"] == {"PAN": 2}


@pytest.mark.asyncio
async def test_async_guard() -> None:
    g = AsyncMaskflowLeakGuardCallback(raise_on_prompt_pii=True)
    llm = FakeMessagesListChatModel(responses=[AIMessage("ok")])
    with pytest.raises(MaskflowPIILeakError):
        await llm.ainvoke([HumanMessage(f"mail {EMAIL}")], config={"callbacks": [g]})


def test_patterns_only_mode() -> None:
    g = MaskflowLeakGuardCallback(patterns_only=True)
    llm = FakeListLLM(responses=["x"])
    llm.invoke(f"PAN {PAN}", config={"callbacks": [g]})
    assert g.summary()["prompt"] == {"PAN": 1}
