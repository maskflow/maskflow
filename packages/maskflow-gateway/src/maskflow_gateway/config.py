"""Gateway configuration -- every knob is an environment variable prefixed
``MASKFLOW_GATEWAY_``. Nothing here has a provider credential baked in;
``upstream_api_key`` is opt-in and, when unset (the default), the client's
own ``Authorization`` header is passed straight through and the gateway
stores no provider credentials at all.
"""

from __future__ import annotations

import functools

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MASKFLOW_GATEWAY_",
        env_file=".env",
        extra="ignore",
    )

    # --- upstreams -----------------------------------------------------
    openai_base_url: str = "https://api.openai.com/v1"
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    # If set, the gateway injects this as the upstream credential and
    # ignores the client's Authorization header. If unset (default), the
    # client's own key is forwarded and nothing is stored.
    upstream_api_key: SecretStr | None = None

    # --- masking -----------------------------------------------------
    # MASKFLOW_GATEWAY_NER=1 turns on the spaCy NER pass (bare Indian names
    # & addresses). Off by default: pattern/checksum + gazetteer only, which
    # is the far faster path. The load test publishes req/s for both.
    ner: bool = False
    min_confidence: float = 0.5
    tool_call_max_depth: int = 32
    tool_call_max_items: int = 10_000

    # --- sessions --------------------------------------------------
    # None => in-process ephemeral sessions only (single replica, no
    # multi-turn token identity across processes). A URL => Redis-backed
    # sessions, and session_key becomes mandatory.
    redis_url: str | None = None
    session_key: SecretStr | None = Field(
        default=None,
        description="Hex-encoded 32-byte key for AES-256-GCM encryption of "
        "session mappings at rest in Redis.",
    )
    session_ttl_seconds: int = 3600
    session_ttl_max_seconds: int = 86_400
    # Redis eviction silently drops a session mid-conversation => unmask
    # fails => raw placeholders shown to a user. /readyz fails closed unless
    # maxmemory-policy is noeviction. Set false only for a Redis you have
    # already sized to never evict by other means.
    require_maxmemory_noeviction: bool = True

    # --- limits / timeouts ---------------------------------------
    max_request_bytes: int = 2_000_000
    upstream_timeout_seconds: float = 120.0
    upstream_connect_timeout_seconds: float = 10.0
    # 0 disables per-key rate limiting. Otherwise a token bucket of
    # `rate_limit_burst` (defaults to the per-minute number) refilled at
    # rate_limit_per_minute/60 per second, keyed by a hash of the client's
    # Authorization header.
    rate_limit_per_minute: int = 0
    rate_limit_burst: int = 0

    # --- ops -----------------------------------------------------------
    json_logs: bool = True
    log_level: str = "INFO"
    cors_allow_origins: list[str] = Field(default_factory=list)

    @field_validator("session_key")
    @classmethod
    def _validate_key_length(cls, v: SecretStr | None) -> SecretStr | None:
        if v is None:
            return v
        try:
            raw = bytes.fromhex(v.get_secret_value())
        except ValueError as exc:
            raise ValueError("MASKFLOW_GATEWAY_SESSION_KEY must be hex-encoded") from exc
        if len(raw) != 32:
            raise ValueError(
                f"MASKFLOW_GATEWAY_SESSION_KEY must decode to 32 bytes (got {len(raw)})"
            )
        return v

    def require_session_key_bytes(self) -> bytes:
        if self.session_key is None:
            raise RuntimeError(
                "MASKFLOW_GATEWAY_REDIS_URL is set but MASKFLOW_GATEWAY_SESSION_KEY "
                "is not -- refusing to persist session mappings unencrypted."
            )
        return bytes.fromhex(self.session_key.get_secret_value())

    def effective_rate_limit_burst(self) -> int:
        return self.rate_limit_burst or self.rate_limit_per_minute


@functools.lru_cache
def get_settings() -> Settings:
    return Settings()
