"""OpenAI-compatible adapter: /v1/chat/completions and /v1/embeddings.

Request masking walks ``messages`` (prose content, multimodal text parts,
and ``tool_calls[].function.arguments`` JSON). Response restoration is
structural for the non-streaming case and incremental for SSE -- a
placeholder split across ``content`` deltas is stitched by a
``StreamingUnmasker``; ``tool_calls`` argument deltas are accumulated and
emitted, unmasked, as one synthesized chunk before the finish chunk.
"""

from __future__ import annotations

import codecs
import copy
import json
from collections.abc import AsyncIterator, MutableMapping
from typing import Any

from maskflow import Session
from maskflow_core import Mapping

from ..masking import mask_arguments_json, mask_text, unmask_json
from ..streaming import SSEDecoder, StreamingUnmasker, format_sse, unmask_whole

NAME = "openai"


def base_url(settings: Any) -> str:
    return settings.openai_base_url.rstrip("/")


# --------------------------------------------------------------------------
# request masking
# --------------------------------------------------------------------------
def _mask_message_content(
    session: Session, content: Any, detections: MutableMapping[str, int], **limits: int
) -> Any:
    if isinstance(content, str):
        return mask_text(session, content, detections)
    if isinstance(content, list):
        out = []
        for part in content:
            if (
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
            ):
                part = {**part, "text": mask_text(session, part["text"], detections)}
            out.append(part)
        return out
    return content


def mask_chat_request(
    session: Session,
    body: dict[str, Any],
    detections: MutableMapping[str, int],
    *,
    max_depth: int,
    max_items: int,
) -> dict[str, Any]:
    masked = copy.deepcopy(body)
    for message in masked.get("messages", []):
        if not isinstance(message, dict):
            continue
        if "content" in message and message["content"] is not None:
            message["content"] = _mask_message_content(session, message["content"], detections)
        for call in message.get("tool_calls", []) or []:
            fn = call.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                fn["arguments"] = mask_arguments_json(
                    session, fn["arguments"], detections, max_depth=max_depth, max_items=max_items
                )
    return masked


def mask_embeddings_request(
    session: Session,
    body: dict[str, Any],
    detections: MutableMapping[str, int],
) -> dict[str, Any]:
    masked = copy.deepcopy(body)
    value = masked.get("input")
    if isinstance(value, str):
        masked["input"] = mask_text(session, value, detections)
    elif isinstance(value, list):
        masked["input"] = [
            mask_text(session, item, detections) if isinstance(item, str) else item
            for item in value
        ]
    return masked


# --------------------------------------------------------------------------
# non-streaming response restoration
# --------------------------------------------------------------------------
def unmask_chat_response(body: dict[str, Any], mapping: Mapping) -> dict[str, Any]:
    restored = copy.deepcopy(body)
    for choice in restored.get("choices", []):
        message = choice.get("message")
        if not isinstance(message, dict):
            continue
        if isinstance(message.get("content"), str):
            message["content"] = unmask_whole(message["content"], mapping)
        elif isinstance(message.get("content"), list):
            message["content"] = unmask_json(message["content"], mapping)
        for call in message.get("tool_calls", []) or []:
            fn = call.get("function")
            if isinstance(fn, dict) and isinstance(fn.get("arguments"), str):
                fn["arguments"] = _unmask_arguments(fn["arguments"], mapping)
    return restored


def _unmask_arguments(raw: str, mapping: Mapping) -> str:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return unmask_whole(raw, mapping)
    return json.dumps(unmask_json(parsed, mapping), ensure_ascii=False)


# --------------------------------------------------------------------------
# streaming response restoration
# --------------------------------------------------------------------------
class _ChoiceState:
    def __init__(self, mapping: Any) -> None:
        self.content = StreamingUnmasker(mapping)
        # tool_call index -> list of masked argument fragments
        self.tool_args: dict[int, list[str]] = {}
        self.tool_emitted_meta: set[int] = set()


async def stream_chat_response(
    mapping: Mapping,
    source: AsyncIterator[bytes],
) -> AsyncIterator[bytes]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    sse = SSEDecoder()
    choices: dict[int, _ChoiceState] = {}
    template: dict[str, Any] = {}

    def state(idx: int) -> _ChoiceState:
        if idx not in choices:
            choices[idx] = _ChoiceState(mapping)
        return choices[idx]

    def chunk(delta: dict[str, Any], idx: int, finish_reason: Any = None) -> bytes:
        payload = {
            **{
                k: template[k]
                for k in ("id", "created", "model", "system_fingerprint")
                if k in template
            },
            "object": "chat.completion.chunk",
            "choices": [{"index": idx, "delta": delta, "finish_reason": finish_reason}],
        }
        return format_sse(json.dumps(payload, ensure_ascii=False)).encode("utf-8")

    def process(data: str) -> list[bytes]:
        if data.strip() == "[DONE]":
            return [format_sse("[DONE]").encode("utf-8")]
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return []
        for key in ("id", "created", "model", "system_fingerprint"):
            if key in obj:
                template[key] = obj[key]

        out: list[bytes] = []
        for choice in obj.get("choices", []):
            idx = choice.get("index", 0)
            st = state(idx)
            delta = choice.get("delta") or {}

            if "role" in delta:
                out.append(chunk({"role": delta["role"]}, idx))

            if isinstance(delta.get("content"), str):
                safe = st.content.feed(delta["content"])
                if safe:
                    out.append(chunk({"content": safe}, idx))

            for call in delta.get("tool_calls", []) or []:
                tc_idx = call.get("index", 0)
                fn = call.get("function") or {}
                meta_delta: dict[str, Any] = {}
                if "id" in call:
                    meta_delta["id"] = call["id"]
                if "type" in call:
                    meta_delta["type"] = call["type"]
                if isinstance(fn.get("name"), str):
                    meta_delta.setdefault("function", {})["name"] = fn["name"]
                if meta_delta and tc_idx not in st.tool_emitted_meta:
                    st.tool_emitted_meta.add(tc_idx)
                    out.append(chunk({"tool_calls": [{"index": tc_idx, **meta_delta}]}, idx))
                if isinstance(fn.get("arguments"), str):
                    st.tool_args.setdefault(tc_idx, []).append(fn["arguments"])

            finish_reason = choice.get("finish_reason")
            if finish_reason is not None:
                tail = st.content.flush()
                if tail:
                    out.append(chunk({"content": tail}, idx))
                for tc_idx, fragments in sorted(st.tool_args.items()):
                    restored = _unmask_arguments("".join(fragments), mapping)
                    out.append(
                        chunk(
                            {
                                "tool_calls": [
                                    {"index": tc_idx, "function": {"arguments": restored}}
                                ]
                            },
                            idx,
                        )
                    )
                st.tool_args.clear()
                extra = {"delta": {}, "finish_reason": finish_reason}
                payload = {
                    **{
                        k: template[k]
                        for k in ("id", "created", "model", "system_fingerprint")
                        if k in template
                    },
                    "object": "chat.completion.chunk",
                    "choices": [{"index": idx, **extra}],
                }
                if "usage" in obj and obj["usage"] is not None:
                    payload["usage"] = obj["usage"]
                out.append(format_sse(json.dumps(payload, ensure_ascii=False)).encode("utf-8"))
        return out

    async for raw in source:
        for event in sse.feed(decoder.decode(raw)):
            for piece in process(event.data):
                yield piece
    for event in sse.feed(decoder.decode(b"", final=True)):
        for piece in process(event.data):
            yield piece
    for event in sse.flush():
        for piece in process(event.data):
            yield piece
    # Safety net: if the stream ended without a finish_reason, flush content.
    for idx, st in choices.items():
        tail = st.content.flush()
        if tail:
            yield chunk({"content": tail}, idx)
