from __future__ import annotations

import json

import httpx
import respx
from fastapi.testclient import TestClient
from helpers import ANTHROPIC_BASE, byte_chunks

EMAIL = "alice@example.com"


@respx.mock
def test_messages_non_streaming_round_trip(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        masked = body["messages"][0]["content"]
        assert EMAIL not in json.dumps(body)
        return httpx.Response(
            200,
            json={
                "id": "msg_1",
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": f"noted {masked}"}],
                "stop_reason": "end_turn",
            },
        )

    respx.post(f"{ANTHROPIC_BASE}/messages").mock(side_effect=handler)
    r = client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 64,
            "messages": [{"role": "user", "content": f"mail {EMAIL}"}],
        },
    )
    assert r.status_code == 200
    assert r.json()["content"][0]["text"] == f"noted mail {EMAIL}"


@respx.mock
def test_messages_streaming_round_trip_split_placeholder(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        token = body["messages"][0]["content"].split()[-1]
        h = len(token) // 2
        frames = [
            'event: message_start\ndata: {"type":"message_start","message":{"id":"m"}}\n\n',
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,'
            '"content_block":{"type":"text","text":""}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"text_delta","text":"hi ' + token[:h] + '"}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"text_delta","text":"' + token[h:] + '!"}}\n\n',
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=byte_chunks(*frames)
        )

    respx.post(f"{ANTHROPIC_BASE}/messages").mock(side_effect=handler)
    with client.stream(
        "POST",
        "/v1/messages",
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 64,
            "stream": True,
            "messages": [{"role": "user", "content": f"mail {EMAIL}"}],
        },
    ) as r:
        raw = b"".join(r.iter_bytes()).decode("utf-8")

    text = "".join(
        json.loads(line[6:])["delta"]["text"]
        for line in raw.splitlines()
        if line.startswith("data: ") and '"text_delta"' in line
    )
    assert text == f"hi {EMAIL}!"
    assert "<EMAIL_" not in raw
    assert "event: message_stop" in raw


@respx.mock
def test_messages_streaming_tool_use_input_json_delta_is_restored(client: TestClient) -> None:
    """A streamed tool_use block whose input JSON arrives as
    `input_json_delta` fragments (placeholder split across them) must reach
    the client as valid JSON with the original value."""
    phone = "415-555-0132"

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert phone not in json.dumps(body)
        token = json.loads(body["messages"][0]["content"].split("call ", 1)[1])["phone"]
        arg = json.dumps({"phone": token})
        cut = arg.index(token) + 4
        frames = [
            'event: content_block_start\ndata: {"type":"content_block_start","index":0,'
            '"content_block":{"type":"tool_use","id":"tu_1","name":"lookup","input":{}}}\n\n',
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"input_json_delta","partial_json":' + json.dumps(arg[:cut]) + "}}\n\n",
            'event: content_block_delta\ndata: {"type":"content_block_delta","index":0,'
            '"delta":{"type":"input_json_delta","partial_json":' + json.dumps(arg[cut:]) + "}}\n\n",
            'event: content_block_stop\ndata: {"type":"content_block_stop","index":0}\n\n',
            'event: message_stop\ndata: {"type":"message_stop"}\n\n',
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=byte_chunks(*frames)
        )

    respx.post(f"{ANTHROPIC_BASE}/messages").mock(side_effect=handler)
    with client.stream(
        "POST",
        "/v1/messages",
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 64,
            "stream": True,
            "messages": [{"role": "user", "content": f"call {json.dumps({'phone': phone})}"}],
        },
    ) as r:
        raw = b"".join(r.iter_bytes()).decode("utf-8")

    assert "<PHONE_" not in raw
    partial = "".join(
        json.loads(line[6:])["delta"]["partial_json"]
        for line in raw.splitlines()
        if line.startswith("data: ") and '"input_json_delta"' in line
    )
    assert json.loads(partial) == {"phone": phone}
