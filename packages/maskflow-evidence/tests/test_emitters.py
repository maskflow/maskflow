from __future__ import annotations

import io
import json

import pytest
from maskflow_evidence import (
    EvidenceConfig,
    EvidenceEvent,
    NullEmitter,
    SafeEmitter,
    build_emitter,
)
from maskflow_evidence.emitters.file import FileEmitter
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
