from __future__ import annotations

import pytest
from maskflow_gateway.config import Settings


def test_defaults_are_safe() -> None:
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ner is False  # pattern-only unless explicitly enabled
    assert s.redis_url is None  # ephemeral sessions by default
    assert s.upstream_api_key is None  # pass the client's key through, store nothing
    assert s.require_maxmemory_noeviction is True
    assert s.session_ttl_seconds == 3600


def test_env_vars_are_read_with_prefix(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MASKFLOW_GATEWAY_NER", "1")
    monkeypatch.setenv("MASKFLOW_GATEWAY_OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MASKFLOW_GATEWAY_RATE_LIMIT_PER_MINUTE", "120")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.ner is True
    assert s.openai_base_url == "https://example.test/v1"
    assert s.rate_limit_per_minute == 120
    assert s.effective_rate_limit_burst() == 120


def test_rejects_redis_without_key() -> None:
    s = Settings(redis_url="redis://localhost:6379/0", _env_file=None)  # type: ignore[call-arg]
    with pytest.raises(RuntimeError, match="SESSION_KEY"):
        s.require_session_key_bytes()


def test_rejects_wrong_key_length() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        Settings(session_key="00" * 16, _env_file=None)  # type: ignore[call-arg]


def test_accepts_valid_32_byte_hex_key() -> None:
    s = Settings(session_key="ab" * 32, _env_file=None)  # type: ignore[call-arg]
    assert len(s.require_session_key_bytes()) == 32
