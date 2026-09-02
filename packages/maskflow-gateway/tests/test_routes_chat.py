"""End-to-end /v1/chat/completions: the upstream mock asserts it never
sees raw PII, and the gateway response must come back fully restored --
non-streaming and streaming, prose and tool calls."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

import httpx
import respx
from fastapi.testclient import TestClient
from helpers import OPENAI_BASE

EMAIL = "alice@example.com"
PHONE = "415-555-0132"


def _chunks(*parts: str) -> AsyncIterator[bytes]:
    async def gen() -> AsyncIterator[bytes]:
        for part in parts:
            yield part.encode("utf-8")

    return gen()


@respx.mock
def test_non_streaming_round_trip(client: TestClient) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        upstream_content = seen["body"]["messages"][0]["content"]  # the masked text
        assert EMAIL not in json.dumps(seen["body"])
        return httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": f"noted: {upstream_content}"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": f"mail {EMAIL}"}]},
        headers={"authorization": "Bearer sk-client"},
    )
    assert r.status_code == 200
    assert r.json()["choices"][0]["message"]["content"] == f"noted: mail {EMAIL}"


@respx.mock
def test_client_key_is_forwarded_upstream(client: TestClient) -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(
            200,
            json={"choices": [{"index": 0, "message": {"content": "hi"}, "finish_reason": "stop"}]},
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)
    client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hello"}]},
        headers={"authorization": "Bearer sk-client-xyz"},
    )
    assert captured["auth"] == "Bearer sk-client-xyz"


@respx.mock
def test_streaming_round_trip_with_split_placeholder(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        masked = body["messages"][0]["content"]
        assert EMAIL not in masked
        token = masked.split()[-1]  # "<EMAIL_1>"
        half = len(token) // 2

        def frame(delta: dict, finish: object = None) -> str:
            chunk = {"id": "c", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return f"data: {json.dumps(chunk)}\n\n"

        frames = [
            frame({"role": "assistant"}),
            frame({"content": f"here: {token[:half]}"}),
            frame({"content": f"{token[half:]} ok"}),
            frame({}, "stop"),
            "data: [DONE]\n\n",
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_chunks(*frames)
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "messages": [{"role": "user", "content": f"mail {EMAIL}"}],
        },
    ) as r:
        assert r.status_code == 200
        raw = b"".join(r.iter_bytes()).decode("utf-8")

    text = "".join(
        json.loads(line[6:])["choices"][0]["delta"].get("content", "")
        for line in raw.splitlines()
        if line.startswith("data: ") and line[6:].strip() not in ("[DONE]", "")
    )
    assert text == f"here: {EMAIL} ok"
    assert "<EMAIL_" not in raw


@respx.mock
def test_tool_call_arguments_are_masked_and_restored(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert PHONE not in json.dumps(body)
        # Echo the masked tool arg back as an assistant tool call.
        masked_arg = body["messages"][-1]["tool_calls"][0]["function"]["arguments"]
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "tool_calls": [
                                {
                                    "id": "call_1",
                                    "type": "function",
                                    "function": {"name": "lookup", "arguments": masked_arg},
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    r = client.post(
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "messages": [
                {"role": "user", "content": "look it up"},
                {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {
                                "name": "lookup",
                                "arguments": json.dumps({"phone": PHONE}),
                            },
                        }
                    ],
                },
            ],
        },
    )
    assert r.status_code == 200
    args = json.loads(r.json()["choices"][0]["message"]["tool_calls"][0]["function"]["arguments"])
    assert args == {"phone": PHONE}


@respx.mock
def test_streaming_tool_call_arguments_split_across_fragments(client: TestClient) -> None:
    """The model streams a tool call whose `arguments` (containing a
    placeholder split mid-token) arrives in fragments -- the client must
    end up with valid JSON carrying the restored value."""

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert PHONE not in json.dumps(body)
        # The model echoes the masked context: a tool call with the token.
        masked = json.loads(body["messages"][0]["content"].split("call ", 1)[1])
        arg = json.dumps({"phone": masked["phone"]})  # {"phone": "<PHONE_1>"}
        cut = arg.index("<PHONE_1>") + 4  # split mid-placeholder

        def frame(delta: dict, finish: object = None) -> str:
            chunk = {"id": "c", "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
            return f"data: {json.dumps(chunk)}\n\n"

        frames = [
            frame({"role": "assistant"}),
            frame(
                {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": "lookup", "arguments": ""},
                        }
                    ]
                }
            ),
            frame({"tool_calls": [{"index": 0, "function": {"arguments": arg[:cut]}}]}),
            frame({"tool_calls": [{"index": 0, "function": {"arguments": arg[cut:]}}]}),
            frame({}, "tool_calls"),
            "data: [DONE]\n\n",
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_chunks(*frames)
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "messages": [{"role": "user", "content": f"call {json.dumps({'phone': PHONE})}"}],
        },
    ) as r:
        raw = b"".join(r.iter_bytes()).decode("utf-8")

    assert "<PHONE_" not in raw
    # Reassemble tool_call arguments the way a client would.
    name = ""
    args = ""
    for line in raw.splitlines():
        if not line.startswith("data: ") or line[6:].strip() in ("[DONE]", ""):
            continue
        delta = json.loads(line[6:])["choices"][0]["delta"]
        for call in delta.get("tool_calls", []):
            fn = call.get("function", {})
            name += fn.get("name", "")
            args += fn.get("arguments", "")
    assert name == "lookup"
    assert json.loads(args) == {"phone": PHONE}


@respx.mock
def test_streaming_two_choices_are_unmasked_independently(client: TestClient) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        token = body["messages"][0]["content"].split()[-1]  # "<EMAIL_1>"

        def frame(idx: int, delta: dict, finish: object = None) -> str:
            choice = {"index": idx, "delta": delta, "finish_reason": finish}
            return f"data: {json.dumps({'id': 'c', 'choices': [choice]})}\n\n"

        frames = [
            frame(0, {"content": f"A: {token[:4]}"}),
            frame(1, {"content": f"B: {token[:2]}"}),
            frame(0, {"content": token[4:]}, "stop"),
            frame(1, {"content": token[2:]}, "stop"),
            "data: [DONE]\n\n",
        ]
        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=_chunks(*frames)
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    with client.stream(
        "POST",
        "/v1/chat/completions",
        json={
            "model": "gpt-4o",
            "stream": True,
            "n": 2,
            "messages": [{"role": "user", "content": f"mail {EMAIL}"}],
        },
    ) as r:
        raw = b"".join(r.iter_bytes()).decode("utf-8")

    per_choice: dict[int, str] = {}
    for line in raw.splitlines():
        if not line.startswith("data: ") or line[6:].strip() in ("[DONE]", ""):
            continue
        choice = json.loads(line[6:])["choices"][0]
        per_choice[choice["index"]] = per_choice.get(choice["index"], "") + choice["delta"].get(
            "content", ""
        )
    assert per_choice == {0: f"A: {EMAIL}", 1: f"B: {EMAIL}"}
    assert "<EMAIL_" not in raw


@respx.mock
def test_upstream_error_is_forwarded(client: TestClient) -> None:
    respx.post(f"{OPENAI_BASE}/chat/completions").mock(
        return_value=httpx.Response(429, json={"error": {"message": "slow down"}})
    )
    r = client.post(
        "/v1/chat/completions",
        json={"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]},
    )
    assert r.status_code == 429
    assert r.json()["error"]["message"] == "slow down"
