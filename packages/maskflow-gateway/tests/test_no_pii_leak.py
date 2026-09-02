"""CLAUDE.md rule 1 gate for the gateway: a PII value the gateway detected
and masked must never resurface in a log line, an error body, the metrics
exposition, or the bytes sent upstream. Run in CI as `pytest -m leak`.
"""

from __future__ import annotations

import json
import logging

import httpx
import pytest
import respx
from fastapi.testclient import TestClient
from helpers import OPENAI_BASE
from maskflow_gateway.app import create_app
from maskflow_gateway.config import Settings
from maskflow_gateway.observability import metrics

pytestmark = pytest.mark.leak

# Reliably pattern-detected with no NER pass needed.
EMAIL = "raju.patel@example.com"


@respx.mock
def test_masked_value_never_leaks(caplog: pytest.LogCaptureFixture) -> None:
    seen_upstream: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_upstream["body"] = request.content.decode("utf-8")
        return httpx.Response(500, text="upstream boom")

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    settings = Settings(openai_base_url=OPENAI_BASE, redis_url=None, _env_file=None)  # type: ignore[call-arg]
    with caplog.at_level(logging.DEBUG), TestClient(create_app(settings)) as client:
        r = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": f"email me at {EMAIL}"}],
            },
        )

    # The email was detected -> it must be masked on the wire...
    assert EMAIL not in seen_upstream["body"]
    assert "<EMAIL_1>" in seen_upstream["body"]

    # ...and absent from the error response and every log record.
    assert EMAIL not in r.text
    log_blob = "\n".join(
        rec.getMessage() + json.dumps(rec.__dict__, default=str) for rec in caplog.records
    )
    assert EMAIL not in log_blob

    assert EMAIL not in metrics.render()[0].decode("utf-8")


@respx.mock
def test_broken_stream_error_event_has_no_pii() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=b"data: {not valid json\n\n",
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)
    settings = Settings(openai_base_url=OPENAI_BASE, redis_url=None, _env_file=None)  # type: ignore[call-arg]
    with (
        TestClient(create_app(settings)) as client,
        client.stream(
            "POST",
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "stream": True,
                "messages": [{"role": "user", "content": f"email {EMAIL}"}],
            },
        ) as r,
    ):
        raw = b"".join(r.iter_bytes()).decode("utf-8")
    assert EMAIL not in raw
