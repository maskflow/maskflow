"""Request masking / response unmasking over LiteLLM's already-parsed
message and response shapes.

Everything here is provider-agnostic and free of any ``litellm`` import: it
walks plain ``dict`` / ``list`` structures (the request ``data`` and, for
Anthropic passthrough, the response body) and duck-typed response objects
(``.choices[].message.content`` ...). The round-trip guarantees live in
``maskflow`` -- ``Session.mask`` / ``Session.mask_json`` on the way in and
``maskflow_core.unmask`` on the way out. This module only decides *which
strings* to hand them.

Design notes
------------
* Tool-call ``arguments`` is a JSON string: parse it and walk it with
  ``Session.mask_json`` (string / numeric *values* only, keys never), so a
  masked argument blob stays valid JSON. If it does not parse, fall back to
  masking the whole string.
* Inbound tool results (``role: "tool"`` messages, Anthropic ``tool_result``
  blocks) are masked *through the session*, never unmasked toward the model
  -- a value the model already saw as ``<AADHAAR_1>`` keeps that token, a
  new value gets the next counter. This keeps placeholder identity stable
  across a whole agent run.
* ``max_depth`` / ``max_items`` bound the JSON walk against adversarial
  tool-argument payloads (same defaults as ``Session.mask_json``).
"""

from __future__ import annotations

import json
from typing import Any

from maskflow import Session
from maskflow.streaming import unmask_whole
from maskflow_core import Mapping

_MAX_DEPTH = 32
_MAX_ITEMS = 10_000


# --------------------------------------------------------------------------
# request side
# --------------------------------------------------------------------------
def _mask_json_string(session: Session, raw: str) -> str:
    """Mask a JSON-object string (a tool call's ``arguments``). Falls back to
    whole-string masking if it does not parse."""
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return session.mask(raw)
    masked = session.mask_json(parsed, max_depth=_MAX_DEPTH, max_items=_MAX_ITEMS)
    return json.dumps(masked, ensure_ascii=False)


def _mask_content(session: Session, content: Any) -> Any:
    """Mask an OpenAI/Anthropic message ``content``: a bare string, or a list
    of content parts (``{"type": "text", "text": ...}`` and Anthropic
    ``tool_result`` / ``tool_use`` blocks)."""
    if isinstance(content, str):
        return session.mask(content)
    if not isinstance(content, list):
        return content

    out: list[Any] = []
    for part in content:
        if not isinstance(part, dict):
            out.append(part)
            continue
        ptype = part.get("type")
        if ptype in (None, "text") and isinstance(part.get("text"), str):
            out.append({**part, "text": session.mask(part["text"])})
        elif ptype == "tool_result":
            # Anthropic inbound tool result -- mask through the session.
            out.append({**part, "content": _mask_content(session, part.get("content"))})
        elif ptype == "tool_use" and part.get("input") is not None:
            out.append(
                {
                    **part,
                    "input": session.mask_json(
                        part["input"], max_depth=_MAX_DEPTH, max_items=_MAX_ITEMS
                    ),
                }
            )
        else:
            out.append(part)
    return out


def mask_request_data(session: Session, data: dict[str, Any]) -> None:
    """Mask every model-visible string in a LiteLLM request ``data`` dict,
    in place. Covers ``messages[].content`` (prose + multimodal text parts +
    Anthropic blocks), ``messages[].tool_calls[].function.arguments``,
    Anthropic top-level ``system``, and OpenAI ``input`` (embeddings)."""
    system = data.get("system")
    if isinstance(system, str):
        data["system"] = session.mask(system)
    elif isinstance(system, list):
        data["system"] = _mask_content(session, system)

    for message in data.get("messages", []) or []:
        if not isinstance(message, dict):
            continue
        if message.get("content") is not None:
            message["content"] = _mask_content(session, message["content"])
        for call in message.get("tool_calls", []) or []:
            fn = call.get("function") if isinstance(call, dict) else None
            if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                fn["arguments"] = _mask_json_string(session, fn["arguments"])

    value = data.get("input")
    if isinstance(value, str):
        data["input"] = session.mask(value)
    elif isinstance(value, list):
        data["input"] = [session.mask(item) if isinstance(item, str) else item for item in value]


# --------------------------------------------------------------------------
# response side (non-streaming)
# --------------------------------------------------------------------------
def _unmask_json_leaves(value: Any, mapping: Mapping) -> Any:
    if isinstance(value, str):
        return unmask_whole(value, mapping)
    if isinstance(value, dict):
        return {k: _unmask_json_leaves(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [_unmask_json_leaves(v, mapping) for v in value]
    return value


def _unmask_arguments(raw: str, mapping: Mapping) -> str:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return unmask_whole(raw, mapping)
    return json.dumps(_unmask_json_leaves(parsed, mapping), ensure_ascii=False)


def unmask_model_response(session: Session, response: Any) -> None:
    """Restore originals in a duck-typed ``ModelResponse``-shaped object, in
    place: ``choices[].message.content`` (str or list parts),
    ``choices[].message.tool_calls[].function.arguments``, and
    ``choices[].message.reasoning_content`` when present."""
    mapping = session.mapping
    for choice in getattr(response, "choices", None) or []:
        message = getattr(choice, "message", None)
        if message is None:
            continue
        content = getattr(message, "content", None)
        if isinstance(content, str):
            message.content = unmask_whole(content, mapping)
        elif isinstance(content, list):
            message.content = _unmask_json_leaves(content, mapping)
        reasoning = getattr(message, "reasoning_content", None)
        if isinstance(reasoning, str):
            message.reasoning_content = unmask_whole(reasoning, mapping)
        for call in getattr(message, "tool_calls", None) or []:
            fn = getattr(call, "function", None)
            if fn is not None and isinstance(getattr(fn, "arguments", None), str):
                fn.arguments = _unmask_arguments(fn.arguments, mapping)


def unmask_anthropic_message(session: Session, body: dict[str, Any]) -> None:
    """Restore originals in an Anthropic native ``/v1/messages`` response
    dict, in place (``content`` blocks: ``text`` and ``tool_use.input``)."""
    mapping = session.mapping
    for block in body.get("content", []) or []:
        if not isinstance(block, dict):
            continue
        if isinstance(block.get("text"), str):
            block["text"] = unmask_whole(block["text"], mapping)
        if block.get("type") == "tool_use" and block.get("input") is not None:
            block["input"] = _unmask_json_leaves(block["input"], mapping)
