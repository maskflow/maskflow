from __future__ import annotations

import json

from maskflow import session as open_session
from maskflow_gateway.masking import (
    mask_arguments_json,
    mask_text,
    unmask_json,
)
from maskflow_gateway.providers import anthropic, openai

EMAIL = "alice@example.com"
PHONE = "415-555-0132"


def test_mask_text_counts_detections_by_type() -> None:
    with open_session(patterns_only=True) as s:
        det: dict[str, int] = {}
        out = mask_text(s, f"mail {EMAIL}", det)
    assert EMAIL not in out
    assert det.get("EMAIL") == 1


def test_mask_arguments_json_never_touches_keys() -> None:
    with open_session(patterns_only=True) as s:
        det: dict[str, int] = {}
        raw = json.dumps({"email": EMAIL, "note": "hi"})
        masked = mask_arguments_json(s, raw, det, max_depth=32, max_items=1000)
    parsed = json.loads(masked)
    assert "email" in parsed and parsed["email"] != EMAIL
    assert parsed["note"] == "hi"


def test_openai_request_masks_content_and_tool_args() -> None:
    with open_session(patterns_only=True) as s:
        det: dict[str, int] = {}
        body = {
            "messages": [
                {"role": "user", "content": f"reach {EMAIL}"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "c1",
                            "type": "function",
                            "function": {"name": "f", "arguments": json.dumps({"p": PHONE})},
                        }
                    ],
                },
                {"role": "tool", "tool_call_id": "c1", "content": f"found {PHONE}"},
            ]
        }
        masked = openai.mask_chat_request(s, body, det, max_depth=32, max_items=1000)
    blob = json.dumps(masked)
    assert EMAIL not in blob and PHONE not in blob
    # tool-result message (inbound) is masked too, with consistent identity
    assert masked["messages"][1]["tool_calls"][0]["function"]["arguments"].count("<PHONE_1>") == 1
    assert "<PHONE_1>" in masked["messages"][2]["content"]


def test_openai_multimodal_text_parts_masked_image_untouched() -> None:
    with open_session(patterns_only=True) as s:
        det: dict[str, int] = {}
        body = {
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"mail {EMAIL}"},
                        {"type": "image_url", "image_url": {"url": "https://x/y.png"}},
                    ],
                }
            ]
        }
        masked = openai.mask_chat_request(s, body, det, max_depth=32, max_items=1000)
    parts = masked["messages"][0]["content"]
    assert EMAIL not in parts[0]["text"]
    assert parts[1] == {"type": "image_url", "image_url": {"url": "https://x/y.png"}}


def test_anthropic_request_masks_system_blocks_and_tool_use_input() -> None:
    with open_session(patterns_only=True) as s:
        det: dict[str, int] = {}
        body = {
            "system": [{"type": "text", "text": f"user is {EMAIL}"}],
            "messages": [
                {
                    "role": "assistant",
                    "content": [
                        {"type": "tool_use", "id": "t1", "name": "q", "input": {"phone": PHONE}}
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {"type": "tool_result", "tool_use_id": "t1", "content": f"got {PHONE}"}
                    ],
                },
            ],
        }
        masked = anthropic.mask_messages_request(s, body, det, max_depth=32, max_items=1000)
    blob = json.dumps(masked)
    assert EMAIL not in blob and PHONE not in blob
    assert masked["messages"][0]["content"][0]["input"]["phone"] == "<PHONE_1>"


def test_unmask_json_restores_string_leaves_only() -> None:
    with open_session(patterns_only=True) as s:
        det: dict[str, int] = {}
        masked_email = mask_text(s, EMAIL, det)
        value = {"a": masked_email, "b": [masked_email, 5], "c": {"d": masked_email}}
        restored = unmask_json(value, s.mapping)
    assert restored == {"a": EMAIL, "b": [EMAIL, 5], "c": {"d": EMAIL}}
