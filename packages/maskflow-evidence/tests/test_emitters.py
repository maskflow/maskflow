from __future__ import annotations

import io
import json
import time

import httpx
import pytest
from maskflow_evidence import (
    EvidenceConfig,
    EvidenceEvent,
    NullEmitter,
    SafeEmitter,
    build_emitter,
)
from maskflow_evidence.emitters.file import FileEmitter
from maskflow_evidence.emitters.hosted import HostedEmitter
from maskflow_evidence.emitters.stdout import StdoutEmitter


def _event(**over: object) -> EvidenceEvent:
    base = dict(
        entity_type="AADHAAR",
        count=2,
        score=0.97,
        recognizer="pattern:AADHAAR",
        action="masked",
        service="svc",
        environment="prod",
        session_id="sess0000abcd",
        pack_version="0.5.0",
        engine_version="0.6.0",
    )
    base.update(over)
    return EvidenceEvent(**base)  # type: ignore[arg-type]


def test_disabled_config_gives_null_emitter() -> None:
    assert isinstance(build_emitter(EvidenceConfig(enabled=False)), NullEmitter)


def test_stdout_emitter_writes_one_json_line() -> None:
    buf = io.StringIO()
    StdoutEmitter(buf).emit(_event())
    line = buf.getvalue().strip()
    parsed = json.loads(line)
    assert parsed["entity_type"] == "AADHAAR"
    assert parsed["count"] == 2


def test_file_emitter_appends_and_rotates(tmp_path) -> None:
    path = tmp_path / "sub" / "evidence.log"
    emitter = FileEmitter(path, max_bytes=200, backups=2)
    for _ in range(20):
        emitter.emit(_event())
    emitter.close()
    assert path.exists()
    assert (tmp_path / "sub").glob("evidence.log*")
    first = path.read_text().splitlines()[0]
    assert json.loads(first)["recognizer"] == "pattern:AADHAAR"


def test_build_emitter_file_sink(tmp_path) -> None:
    cfg = EvidenceConfig(enabled=True, sink="file", path=str(tmp_path / "e.log"))
    emitter = build_emitter(cfg)
    assert isinstance(emitter, SafeEmitter)
    emitter.emit(_event())
    emitter.close()
    assert (tmp_path / "e.log").read_text().strip()


def test_safe_emitter_swallows_failures() -> None:
    class Boom:
        def emit(self, event: object) -> None:
            raise RuntimeError("sink down")

        def close(self) -> None:
            raise RuntimeError("close down")

    safe = SafeEmitter(Boom())
    safe.emit(_event())  # must not raise
    safe.close()
    assert safe.dropped == 1


def test_unknown_sink_rejected() -> None:
    with pytest.raises(ValueError):
        EvidenceConfig(enabled=True, sink="carrier-pigeon")


# --- hosted emitter ------------------------------------------------------


def _stub_post(calls: list[object], *, status_code: int = 200):
    def post(url: str, json: object) -> httpx.Response:
        calls.append(json)
        return httpx.Response(status_code, request=httpx.Request("POST", url))

    return post


def test_hosted_emitter_requires_api_key() -> None:
    with pytest.raises(ValueError, match="api_key"):
        HostedEmitter("")


def test_hosted_emitter_batches_before_flushing() -> None:
    emitter = HostedEmitter("k", batch_size=3)
    calls: list[object] = []
    emitter._client.post = _stub_post(calls)  # type: ignore[method-assign]

    emitter.emit(_event())
    emitter.emit(_event())
    assert calls == []  # not flushed yet -- batch_size not reached

    emitter.emit(_event())
    assert len(calls) == 1
    assert len(calls[0]["events"]) == 3  # type: ignore[index]


def test_hosted_emitter_close_flushes_remainder() -> None:
    emitter = HostedEmitter("k", batch_size=5)
    calls: list[object] = []
    emitter._client.post = _stub_post(calls)  # type: ignore[method-assign]

    emitter.emit(_event())
    emitter.emit(_event())
    emitter.close()
    assert len(calls) == 1
    assert len(calls[0]["events"]) == 2  # type: ignore[index]


def test_hosted_emitter_retries_on_5xx_then_succeeds(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    emitter = HostedEmitter("k", batch_size=1, max_retries=2)
    codes = iter([500, 200])
    calls: list[object] = []

    def post(url: str, json: object) -> httpx.Response:
        calls.append(json)
        return httpx.Response(next(codes), request=httpx.Request("POST", url))

    emitter._client.post = post  # type: ignore[method-assign]
    emitter.emit(_event())  # batch_size=1 -> flushes immediately
    assert len(calls) == 2


def test_hosted_emitter_gives_up_after_max_retries(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    emitter = HostedEmitter("k", batch_size=1, max_retries=1)
    calls: list[object] = []
    emitter._client.post = _stub_post(calls, status_code=500)  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        emitter.emit(_event())
    assert len(calls) == 2  # initial attempt + 1 retry
    assert emitter._buffer == []  # dropped batch is never re-queued


def test_hosted_emitter_does_not_retry_on_4xx(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    emitter = HostedEmitter("k", batch_size=1, max_retries=3)
    calls: list[object] = []
    emitter._client.post = _stub_post(calls, status_code=401)  # type: ignore[method-assign]

    with pytest.raises(httpx.HTTPStatusError):
        emitter.emit(_event())
    assert len(calls) == 1  # a client error is not retried


def test_hosted_emitter_wrapped_by_safe_emitter_never_raises(monkeypatch) -> None:
    monkeypatch.setattr(time, "sleep", lambda seconds: None)
    inner = HostedEmitter("k", batch_size=1, max_retries=0)
    inner._client.post = _stub_post([], status_code=500)  # type: ignore[method-assign]

    safe = SafeEmitter(inner)
    safe.emit(_event())  # must not raise
    assert safe.dropped == 1


def test_build_emitter_hosted_sink() -> None:
    cfg = EvidenceConfig(enabled=True, sink="hosted", api_key="k")
    emitter = build_emitter(cfg)
    assert isinstance(emitter, SafeEmitter)
    assert isinstance(emitter._inner, HostedEmitter)


def test_hosted_emitter_batched_payload_is_metadata_only() -> None:
    from maskflow_evidence.guard import assert_no_pii

    emitter = HostedEmitter("k", batch_size=1)
    calls: list[object] = []
    emitter._client.post = _stub_post(calls)  # type: ignore[method-assign]
    emitter.emit(_event(entity_type="EMAIL", recognizer="pattern:EMAIL"))
    assert_no_pii(json.dumps(calls[0]))
