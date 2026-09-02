"""Shared shaping for API sources: turn a provider's free-form "input" /
"output" payload into (role, text) pairs, and page an offset/cursor API
into a flat record stream."""

from __future__ import annotations

from collections.abc import Iterator


def messages_from(payload: object, *, default_role: str) -> Iterator[tuple[str, str]]:
    """Yield (role, text) from whatever an LLM call's input/output looks
    like: a bare string, a chat-messages list, an OpenAI-ish
    {"messages": [...]}, or an Anthropic-ish {"content": "..."}."""
    if payload is None:
        return
    if isinstance(payload, str):
        if payload.strip():
            yield default_role, payload
        return
    if isinstance(payload, dict):
        if isinstance(payload.get("messages"), list):
            yield from messages_from(payload["messages"], default_role=default_role)
            return
        content = payload.get("content")
        role = payload.get("role", default_role)
        if isinstance(content, str) and content.strip():
            yield str(role), content
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    if part["text"].strip():
                        yield str(role), part["text"]
        return
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, str):
                if item.strip():
                    yield default_role, item
            elif isinstance(item, dict):
                yield from messages_from(item, default_role=default_role)
