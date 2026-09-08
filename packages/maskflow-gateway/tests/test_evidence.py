from __future__ import annotations

import json

import pytest
import respx
from maskflow import session as open_session
from maskflow_evidence import EvidenceConfig
from maskflow_gateway.observability import metrics
from maskflow_gateway.observability.evidence import GatewayEvidence, _session_slug

pytestmark = pytest.mark.leak

EMAIL = "alice@example.com"


def test_disabled_by_default_emits_nothing() -> None:
    ev = GatewayEvidence.from_config(EvidenceConfig())
    assert ev.enabled is False
    with open_session(patterns_only=True) as s:
        s.mask(f"mail {EMAIL}")
        n = ev.emit_request(
            s.mapping, list(s.mapping), provider="openai", model="gpt-4o", raw_session_id="c1c1c1c1"
        )
    assert n == 0


def test_enabled_file_sink_emits_metadata_only(tmp_path) -> None:
    path = tmp_path / "evidence.log"
    cfg = EvidenceConfig(
        enabled=True, sink="file", path=str(path), service="gw-test", environment="ci"
    )
    ev = GatewayEvidence.from_config(cfg)
    before = metrics.EVIDENCE_EMITTED.labels(sink="file")._value.get()

    with open_session(patterns_only=True) as s:
        s.mask(f"mail {EMAIL} and {EMAIL} again")
        n = ev.emit_request(
            s.mapping,
            list(s.mapping),
            provider="openai",
            model="gpt-4o",
            raw_session_id="client-session-42",
        )
    ev.close()

    assert n == 1
    line = path.read_text().strip()
    record = json.loads(line)
    assert record["entity_type"] == "EMAIL"
    assert record["service"] == "gw-test"
    assert record["environment"] == "ci"
    assert record["provider"] == "openai"
    assert record["model"] == "gpt-4o"
    assert EMAIL not in line
    assert "client-session-42" not in line  # session id is hashed
    assert metrics.EVIDENCE_EMITTED.labels(sink="file")._value.get() == before + 1


def test_bad_model_string_is_dropped_not_fatal(tmp_path) -> None:
    cfg = EvidenceConfig(enabled=True, sink="file", path=str(tmp_path / "e.log"))
    ev = GatewayEvidence.from_config(cfg)
    with open_session(patterns_only=True) as s:
        s.mask(f"mail {EMAIL}")
        # a model string with a space is not a slug -> model field omitted,
        # never raised
        n = ev.emit_request(
            s.mapping,
            list(s.mapping),
            provider="openai",
            model="some model with spaces",
            raw_session_id=None,
        )
    ev.close()
    assert n == 1
    record = json.loads((tmp_path / "e.log").read_text().strip())
    assert record["model"] is None


def test_session_slug_is_opaque_and_bounded() -> None:
    assert _session_slug("alice@example.com") != "alice@example.com"
    assert 8 <= len(_session_slug(None)) <= 128
    assert 8 <= len(_session_slug("x")) <= 128


@respx.mock
def test_end_to_end_proxy_emits_when_enabled(tmp_path, monkeypatch) -> None:
    """The full proxy flow writes one evidence event per detected type."""
    import httpx
    from fastapi.testclient import TestClient
    from helpers import OPENAI_BASE
    from maskflow_gateway.app import create_app
    from maskflow_gateway.config import Settings

    path = tmp_path / "evidence.log"
    monkeypatch.setenv("MASKFLOW_GATEWAY_EVIDENCE_ENABLED", "true")
    monkeypatch.setenv("MASKFLOW_GATEWAY_EVIDENCE_SINK", "file")
    monkeypatch.setenv("MASKFLOW_GATEWAY_EVIDENCE_PATH", str(path))
    monkeypatch.setenv("MASKFLOW_GATEWAY_EVIDENCE_SERVICE", "e2e")

    def handler(request: httpx.Request) -> httpx.Response:
        assert EMAIL not in request.content.decode()
        return httpx.Response(
            200,
            json={
                "id": "cmpl-1",
                "object": "chat.completion",
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": "noted"},
                        "finish_reason": "stop",
                    }
                ],
            },
        )

    respx.post(f"{OPENAI_BASE}/chat/completions").mock(side_effect=handler)

    settings = Settings(
        openai_base_url=OPENAI_BASE,
        redis_url=None,
        ner=False,
        json_logs=False,
        _env_file=None,  # type: ignore[call-arg]
    )
    with TestClient(create_app(settings)) as client:
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "gpt-4o",
                "messages": [{"role": "user", "content": f"mail {EMAIL}"}],
            },
        )
    assert resp.status_code == 200
    record = json.loads(path.read_text().strip().splitlines()[0])
    assert record["entity_type"] == "EMAIL"
    assert record["service"] == "e2e"
    assert EMAIL not in path.read_text()
