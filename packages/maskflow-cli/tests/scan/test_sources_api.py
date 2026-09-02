"""API sources: config/auth handling and payload shaping, no network."""

from __future__ import annotations

import pytest
from maskflow_cli.scan.sources import get_source
from maskflow_cli.scan.sources._api_common import messages_from
from maskflow_cli.scan.sources.base import SourceAuthError
from maskflow_cli.scan.spec import SourceSpec


@pytest.mark.parametrize(
    ("kind", "env"),
    [
        ("langfuse", ["LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY"]),
        ("helicone", ["HELICONE_API_KEY"]),
        ("langsmith", ["LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"]),
    ],
)
def test_api_source_needs_credentials(
    monkeypatch: pytest.MonkeyPatch, kind: str, env: list
) -> None:
    for var in env:
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(SourceAuthError):
        get_source(SourceSpec(kind=kind, target=""))


def test_api_source_builds_with_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HELICONE_API_KEY", "sk-test")
    src = get_source(SourceSpec(kind="helicone", target=""))
    assert src.name == "helicone"


def test_messages_from_bare_string() -> None:
    assert list(messages_from("hello", default_role="user")) == [("user", "hello")]


def test_messages_from_chat_list() -> None:
    payload = [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}]
    assert list(messages_from(payload, default_role="user")) == [("system", "sys"), ("user", "hi")]


def test_messages_from_openai_wrapper() -> None:
    payload = {"messages": [{"role": "user", "content": "q"}]}
    assert list(messages_from(payload, default_role="user")) == [("user", "q")]


def test_messages_from_anthropic_content_blocks() -> None:
    payload = {
        "role": "assistant",
        "content": [{"type": "text", "text": "a1"}, {"type": "text", "text": "a2"}],
    }
    assert list(messages_from(payload, default_role="assistant")) == [
        ("assistant", "a1"),
        ("assistant", "a2"),
    ]


def test_messages_from_ignores_blank_and_none() -> None:
    assert list(messages_from(None, default_role="user")) == []
    assert list(messages_from("   ", default_role="user")) == []
