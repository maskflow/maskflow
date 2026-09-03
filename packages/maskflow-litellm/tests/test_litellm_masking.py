"""Request masking + response unmasking round-trips, litellm-free."""

from __future__ import annotations

import json

import maskflow
from litellm_response_fakes import choice, message, model_response, tool_call
from maskflow_litellm._masking import (
    mask_request_data,
    unmask_anthropic_message,
    unmask_model_response,
)

# Synthetic, structurally valid PAN (4th char 'P' = individual). Not a real card.
PAN = "ABCPE1234F"


def test_string_content_round_trips() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {"messages": [{"role": "user", "content": f"My PAN is {PAN}"}]}
    mask_request_data(session, data)

    masked = data["messages"][0]["content"]
    assert PAN not in masked
    assert "<PAN_1>" in masked

    resp = model_response(choice(message(content=f"Filed with {masked.split()[-1]}")))
    unmask_model_response(session, resp)
    assert resp.choices[0].message.content == f"Filed with {PAN}"


def test_multimodal_text_parts_masked() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"PAN {PAN}"},
                    {"type": "image_url", "image_url": {"url": "https://example.com/x.png"}},
                ],
            }
        ]
    }
    mask_request_data(session, data)
    parts = data["messages"][0]["content"]
    assert PAN not in parts[0]["text"]
    assert parts[1]["image_url"]["url"] == "https://example.com/x.png"


def test_tool_call_arguments_walked_as_json() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    args = json.dumps({"pan": PAN, "note": "urgent", "count": 3})
    data = {
        "messages": [
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {"type": "function", "function": {"name": "file", "arguments": args}}
                ],
            }
        ]
    }
    mask_request_data(session, data)
    masked_args = json.loads(data["messages"][0]["tool_calls"][0]["function"]["arguments"])
    assert masked_args["pan"] != PAN
    assert masked_args["note"] == "urgent"
    assert masked_args["count"] == 3  # non-PII int untouched
    assert list(masked_args.keys()) == ["pan", "note", "count"]  # keys never masked

    resp = model_response(
        choice(
            message(
                content=None,
                tool_calls=[
                    tool_call("file", data["messages"][0]["tool_calls"][0]["function"]["arguments"])
                ],
            )
        )
    )
    unmask_model_response(session, resp)
    assert json.loads(resp.choices[0].message.tool_calls[0].function.arguments)["pan"] == PAN


def test_same_value_same_token_within_session() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {
        "messages": [
            {"role": "user", "content": f"PAN {PAN}"},
            {"role": "user", "content": f"again, PAN {PAN}"},
        ]
    }
    mask_request_data(session, data)
    assert "<PAN_1>" in data["messages"][0]["content"]
    assert "<PAN_1>" in data["messages"][1]["content"]


def test_anthropic_message_response_unmasked() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {"messages": [{"role": "user", "content": f"PAN {PAN}"}]}
    mask_request_data(session, data)
    token = data["messages"][0]["content"].split()[-1]

    body = {
        "type": "message",
        "content": [
            {"type": "text", "text": f"Noted {token}."},
            {"type": "tool_use", "name": "f", "input": {"value": token}},
        ],
    }
    unmask_anthropic_message(session, body)
    assert body["content"][0]["text"] == f"Noted {PAN}."
    assert body["content"][1]["input"]["value"] == PAN


def test_no_pii_left_in_masked_request() -> None:
    session = maskflow.session(config=maskflow.RootConfig())
    data = {"messages": [{"role": "user", "content": f"PAN {PAN} and phone 9812345678"}]}
    mask_request_data(session, data)
    assert PAN not in json.dumps(data)
