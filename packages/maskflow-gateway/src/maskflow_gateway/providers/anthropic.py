"""Anthropic Messages adapter: /v1/messages.

Same shape as the OpenAI adapter -- request masking walks ``system``,
message ``content`` blocks, ``tool_result`` content, and ``tool_use``
inputs; response restoration is structural (non-streaming) or incremental
(SSE). ``text_delta`` events are stitched by a ``StreamingUnmasker``;
``input_json_delta`` fragments are accumulated and emitted, unmasked, as
one delta before the block stops.
"""

from __future__ import annotations

import codecs
import copy
import json
from collections.abc import AsyncIterator, MutableMapping
from typing import Any

from maskflow import Session
from maskflow_core import Mapping

from ..masking import mask_json_value, mask_text, unmask_json
from ..streaming import SSEDecoder, StreamingUnmasker, format_sse, unmask_whole

NAME = "anthropic"


def base_url(settings: Any) -> str:
    return settings.anthropic_base_url.rstrip("/")


def _mask_block_list(
    session: Session, blocks: list[Any], detections: MutableMapping[str, int], **limits: int
) -> list[Any]:
    out = []
    for block in blocks:
        if not isinstance(block, dict):
            out.append(block)
            continue
        btype = block.get("type")
        if btype == "text" and isinstance(block.get("text"), str):
            block = {**block, "text": mask_text(session, block["text"], detections)}
        elif btype == "tool_use" and isinstance(block.get("input"), (dict, list)):
            block = {
                **block,
                "input": mask_json_value(session, block["input"], detections, **limits),
            }
        elif btype == "tool_result":
            block = {
                **block,
                "content": _mask_tool_result_content(session, block.get("content"), detections),
            }
        out.append(block)
    return out


def _mask_tool_result_content(
    session: Session, content: Any, detections: MutableMapping[str, int]
) -> Any:
    if isinstance(content, str):
        return mask_text(session, content, detections)
    if isinstance(content, list):
        return [
            {**b, "text": mask_text(session, b["text"], detections)}
            if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)
            else b
            for b in content
        ]
    return content


def mask_messages_request(
    session: Session,
    body: dict[str, Any],
    detections: MutableMapping[str, int],
    *,
    max_depth: int,
    max_items: int,
) -> dict[str, Any]:
    limits = {"max_depth": max_depth, "max_items": max_items}
    masked = copy.deepcopy(body)

    system = masked.get("system")
    if isinstance(system, str):
        masked["system"] = mask_text(session, system, detections)
    elif isinstance(system, list):
        masked["system"] = _mask_block_list(session, system, detections, **limits)

    for message in masked.get("messages", []):
        if not isinstance(message, dict):
            continue
        content = message.get("content")
        if isinstance(content, str):
            message["content"] = mask_text(session, content, detections)
        elif isinstance(content, list):
            message["content"] = _mask_block_list(session, content, detections, **limits)
    return masked


def unmask_messages_response(body: dict[str, Any], mapping: Mapping) -> dict[str, Any]:
    restored = copy.deepcopy(body)
    for block in restored.get("content", []):
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text" and isinstance(block.get("text"), str):
            block["text"] = unmask_whole(block["text"], mapping)
        elif block.get("type") == "tool_use" and isinstance(block.get("input"), (dict, list)):
            block["input"] = unmask_json(block["input"], mapping)
    return restored


# --------------------------------------------------------------------------
# streaming
# --------------------------------------------------------------------------
class _BlockState:
    def __init__(self, mapping: Any, kind: str) -> None:
        self.kind = kind  # "text" | "tool_use" | other
        self.text = StreamingUnmasker(mapping)
        self.json_fragments: list[str] = []


async def stream_messages_response(
    mapping: Mapping,
    source: AsyncIterator[bytes],
) -> AsyncIterator[bytes]:
    decoder = codecs.getincrementaldecoder("utf-8")()
    sse = SSEDecoder()
    blocks: dict[int, _BlockState] = {}

    def emit(event: str, obj: dict[str, Any]) -> bytes:
        return format_sse(json.dumps(obj, ensure_ascii=False), event=event).encode("utf-8")

    def process(event_name: str | None, data: str) -> list[bytes]:
        try:
            obj = json.loads(data)
        except (json.JSONDecodeError, ValueError):
            return []
        etype = obj.get("type") or event_name or ""
        out: list[bytes] = []

        if etype == "content_block_start":
            idx = obj.get("index", 0)
            kind = (obj.get("content_block") or {}).get("type", "text")
            blocks[idx] = _BlockState(mapping, kind)
            out.append(emit("content_block_start", obj))

        elif etype == "content_block_delta":
            idx = obj.get("index", 0)
            st = blocks.get(idx) or _BlockState(mapping, "text")
            blocks.setdefault(idx, st)
            delta = obj.get("delta") or {}
            if delta.get("type") == "text_delta" and isinstance(delta.get("text"), str):
                safe = st.text.feed(delta["text"])
                if safe:
                    out.append(
                        emit(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": idx,
                                "delta": {"type": "text_delta", "text": safe},
                            },
                        )
                    )
            elif delta.get("type") == "input_json_delta" and isinstance(
                delta.get("partial_json"), str
            ):
                st.json_fragments.append(delta["partial_json"])
            else:
                out.append(emit("content_block_delta", obj))

        elif etype == "content_block_stop":
            idx = obj.get("index", 0)
            st = blocks.get(idx)
            if st is not None and st.kind == "text":
                tail = st.text.flush()
                if tail:
                    out.append(
                        emit(
                            "content_block_delta",
                            {
                                "type": "content_block_delta",
                                "index": idx,
                                "delta": {"type": "text_delta", "text": tail},
                            },
                        )
                    )
            elif st is not None and st.json_fragments:
                restored = _restore_json("".join(st.json_fragments), mapping)
                out.append(
                    emit(
                        "content_block_delta",
                        {
                            "type": "content_block_delta",
                            "index": idx,
                            "delta": {"type": "input_json_delta", "partial_json": restored},
                        },
                    )
                )
            out.append(emit("content_block_stop", obj))

        elif etype:
            out.append(emit(etype, obj))
        return out

    async for raw in source:
        for event in sse.feed(decoder.decode(raw)):
            for piece in process(event.event, event.data):
                yield piece
    for event in sse.feed(decoder.decode(b"", final=True)):
        for piece in process(event.event, event.data):
            yield piece
    for event in sse.flush():
        for piece in process(event.event, event.data):
            yield piece


def _restore_json(raw: str, mapping: Mapping) -> str:
    try:
        parsed = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return unmask_whole(raw, mapping)
    return json.dumps(unmask_json(parsed, mapping), ensure_ascii=False)
