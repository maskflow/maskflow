"""Gateway error type. CLAUDE.md rule 1: an error never carries raw PII --
only entity types, offsets, counts, and stage names. The message templates
here are deliberately value-free.
"""

from __future__ import annotations

from fastapi import status


class GatewayError(Exception):
    """Raised anywhere in request handling; turned into a JSON error
    response by the app's exception handler."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int = status.HTTP_502_BAD_GATEWAY,
        error_type: str = "gateway_error",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_type = error_type

    def to_body(self) -> dict[str, dict[str, str]]:
        # Shape mirrors OpenAI's {"error": {...}} so existing clients parse it.
        return {"error": {"message": self.message, "type": self.error_type}}


class RequestTooLarge(GatewayError):
    def __init__(self, limit: int) -> None:
        super().__init__(
            f"Request body exceeds the {limit}-byte limit.",
            status_code=413,
            error_type="request_too_large",
        )


class SessionUnavailable(GatewayError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Session store unavailable: {detail}",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            error_type="session_unavailable",
        )


class RateLimited(GatewayError):
    def __init__(self, retry_after_seconds: float) -> None:
        super().__init__(
            f"Rate limit exceeded; retry in {retry_after_seconds:.1f}s.",
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            error_type="rate_limited",
        )
        self.retry_after_seconds = retry_after_seconds


class UpstreamError(GatewayError):
    def __init__(self, detail: str, status_code: int = status.HTTP_502_BAD_GATEWAY) -> None:
        super().__init__(detail, status_code=status_code, error_type="upstream_error")
