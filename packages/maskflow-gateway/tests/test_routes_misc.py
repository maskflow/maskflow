from __future__ import annotations

import json

import httpx
import respx
from fastapi.testclient import TestClient
from helpers import OPENAI_BASE
from maskflow_gateway.app import create_app
from maskflow_gateway.config import Settings

EMAIL = "alice@example.com"


@respx.mock
def test_embeddings_masks_input_before_upstream(client: TestClient) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"object": "list", "data": [{"embedding": [0.1, 0.2]}]})

    respx.post(f"{OPENAI_BASE}/embeddings").mock(side_effect=handler)
    r = client.post(
        "/v1/embeddings",
        json={"model": "text-embedding-3-small", "input": [f"contact {EMAIL}", "no pii"]},
    )
    assert r.status_code == 200
    sent = captured["body"]["input"]
    assert EMAIL not in json.dumps(sent)
    assert sent[1] == "no pii"
    assert r.json()["data"][0]["embedding"] == [0.1, 0.2]


def test_mask_endpoint_returns_mapping_without_session(client: TestClient) -> None:
    r = client.post("/v1/mask", json={"text": f"mail {EMAIL}"})
    body = r.json()
    assert EMAIL not in body["masked_text"]
    assert EMAIL in body["mapping"].values()


def test_mask_and_unmask_endpoints_round_trip_via_body(client: TestClient) -> None:
    masked = client.post("/v1/mask", json={"text": f"mail {EMAIL}"}).json()
    back = client.post(
        "/v1/unmask", json={"text": masked["masked_text"], "mapping": masked["mapping"]}
    ).json()
    assert back["text"] == f"mail {EMAIL}"


def test_mask_endpoint_with_session_keeps_mapping_server_side(client: TestClient) -> None:
    headers = {"x-maskflow-session": "s-42"}
    masked = client.post("/v1/mask", json={"text": f"mail {EMAIL}"}, headers=headers).json()
    assert "mapping" not in masked
    back = client.post("/v1/unmask", json={"text": masked["masked_text"]}, headers=headers).json()
    assert back["text"] == f"mail {EMAIL}"


def test_request_body_size_limit() -> None:
    settings = Settings(
        openai_base_url=OPENAI_BASE, redis_url=None, max_request_bytes=200, _env_file=None
    )  # type: ignore[call-arg]
    with TestClient(create_app(settings)) as c:
        r = c.post(
            "/v1/chat/completions",
            json={"model": "gpt-4o", "messages": [{"role": "user", "content": "x" * 500}]},
        )
    assert r.status_code == 413


@respx.mock
def test_rate_limit_returns_429_with_retry_after() -> None:
    settings = Settings(
        openai_base_url=OPENAI_BASE,
        redis_url=None,
        rate_limit_per_minute=2,
        _env_file=None,
    )  # type: ignore[call-arg]
    respx.post(f"{OPENAI_BASE}/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"index": 0, "message": {"content": "ok"}, "finish_reason": "stop"}]},
        )
    )
    with TestClient(create_app(settings)) as c:
        payload = {"model": "gpt-4o", "messages": [{"role": "user", "content": "hi"}]}
        h = {"authorization": "Bearer sk-a"}
        assert c.post("/v1/chat/completions", json=payload, headers=h).status_code == 200
        assert c.post("/v1/chat/completions", json=payload, headers=h).status_code == 200
        limited = c.post("/v1/chat/completions", json=payload, headers=h)
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers
