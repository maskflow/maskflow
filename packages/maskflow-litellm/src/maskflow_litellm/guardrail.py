"""``MaskflowGuardrail`` -- a LiteLLM custom guardrail that masks PII before
a request reaches the provider and restores it in the response.

Wiring (``config.yaml``)::

    guardrails:
      - guardrail_name: maskflow
        litellm_params:
          guardrail: maskflow_litellm.MaskflowGuardrail
          mode: [pre_call, post_call]        # both -- see below
          maskflow_min_confidence: 0.5       # optional
          maskflow_patterns_only: false      # optional; true skips the spaCy NER pass
          maskflow_session_ttl_seconds: 3600 # optional
          maskflow_redis_url: os.environ/MASKFLOW_REDIS_URL           # optional
          maskflow_session_encryption_key: os.environ/MASKFLOW_KEY    # optional (with redis)

``mode`` **must include both ``pre_call`` and ``post_call``**: ``pre_call``
masks the outgoing request, ``post_call`` (and the streaming iterator hook)
restores the originals in the reply. With ``pre_call`` only, the caller
sees ``<AADHAAR_1>`` tokens in the response.

Sessions
--------
Token identity (same value -> same ``<TYPE_n>`` token) is always stable for
one request. To keep it stable *across* requests in a multi-turn agent, the
client sends a session id -- either a ``maskflow_session_id`` field in the
request ``metadata`` or an ``X-Maskflow-Session: <id>`` header. See
``_sessions`` for the in-process vs Redis backends.

PII safety (MaskFlow release rule #1): this module never logs a mapping or
an original value. Only an opaque session ref (``c:<call-id>`` or
``s:<client-id>``) is written to request metadata.
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING, Any

from litellm._logging import verbose_proxy_logger
from litellm.integrations.custom_guardrail import CustomGuardrail
from litellm.types.guardrails import GuardrailEventHooks
from maskflow import RootConfig, Session

from ._masking import mask_request_data, unmask_anthropic_message, unmask_model_response
from ._sessions import InProcessSessionStore, RedisSessionStore, SessionStore
from ._streaming import unmask_stream

if TYPE_CHECKING:
    from litellm.proxy._types import UserAPIKeyAuth

_EPHEMERAL_PREFIX = "c:"
_KEYED_PREFIX = "s:"


def _decode_key(raw: str) -> bytes:
    """Accept a base64 or hex AES key string; validate the byte length."""
    for decoder in (
        lambda s: base64.b64decode(s, validate=True),
        binascii.unhexlify,
    ):
        try:
            key = decoder(raw)
        except (binascii.Error, ValueError):
            continue
        if len(key) in (16, 24, 32):
            return key
    raise ValueError(
        "maskflow_session_encryption_key must be a base64 or hex string decoding to "
        "16, 24, or 32 bytes."
    )


def _is_anthropic_message_dict(response: object) -> bool:
    return (
        isinstance(response, dict)
        and response.get("type") == "message"
        and isinstance(response.get("content"), list)
    )


class MaskflowGuardrail(CustomGuardrail):
    def __init__(
        self,
        *,
        maskflow_min_confidence: float | None = None,
        maskflow_patterns_only: bool = False,
        maskflow_session_ttl_seconds: int = 3600,
        maskflow_session_id_field: str = "maskflow_session_id",
        maskflow_redis_url: str | None = None,
        maskflow_session_encryption_key: str | None = None,
        maskflow_session_store: SessionStore | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)

        self._min_confidence = maskflow_min_confidence
        self._patterns_only = bool(maskflow_patterns_only)
        self._ttl_seconds = max(1, int(maskflow_session_ttl_seconds))
        self._session_id_field = maskflow_session_id_field
        # Masking config comes from litellm_params, never a filesystem
        # .maskflowrc -- pass an explicit empty RootConfig so Session skips
        # discovery entirely (same choice maskflow-gateway makes).
        self._config = RootConfig()

        self._inprocess_store: SessionStore = InProcessSessionStore(self._new_session)
        self._redis_store: SessionStore | None = None
        if maskflow_session_store is not None:
            self._redis_store = maskflow_session_store
        elif maskflow_redis_url:
            if not maskflow_session_encryption_key:
                raise ValueError(
                    "maskflow_redis_url needs maskflow_session_encryption_key (the session "
                    "snapshot is AES-GCM encrypted before it touches Redis)."
                )
            self._redis_store = RedisSessionStore(
                maskflow_redis_url,
                _decode_key(maskflow_session_encryption_key),
                self._new_session,
            )

        if not self._hooks_include_post_call():
            verbose_proxy_logger.warning(
                "maskflow guardrail %r: mode does not include 'post_call' -- responses "
                "will contain <PLACEHOLDER> tokens. Set mode: [pre_call, post_call].",
                self.guardrail_name,
            )

    # -- setup helpers ----------------------------------------------------
    @classmethod
    def get_supported_event_hooks(cls) -> list[GuardrailEventHooks]:
        return [GuardrailEventHooks.pre_call, GuardrailEventHooks.post_call]

    def _hooks_include_post_call(self) -> bool:
        hook = self.event_hook
        values = hook if isinstance(hook, (list, tuple)) else [hook]
        return any(getattr(v, "value", v) == GuardrailEventHooks.post_call.value for v in values)

    def _new_session(self, ttl_seconds: int) -> Session:
        kwargs: dict[str, Any] = {
            "ttl_seconds": ttl_seconds,
            "config": self._config,
            "patterns_only": self._patterns_only,
        }
        if self._min_confidence is not None:
            kwargs["min_confidence"] = self._min_confidence
        return Session(**kwargs)

    def _store_for(self, ref: str) -> SessionStore:
        if ref.startswith(_KEYED_PREFIX) and self._redis_store is not None:
            return self._redis_store
        return self._inprocess_store

    # -- session-ref resolution ----------------------------------------------
    def _client_session_id(self, data: dict[str, Any]) -> str | None:
        for container in (data.get("metadata"), data.get("litellm_metadata")):
            if isinstance(container, dict):
                value = container.get(self._session_id_field) or container.get(
                    "maskflow_session_id"
                )
                if value:
                    return str(value)
        headers = {}
        for source in (
            (data.get("metadata") or {}).get("headers"),
            (data.get("proxy_server_request") or {}).get("headers"),
        ):
            if isinstance(source, dict):
                headers = {str(k).lower(): v for k, v in source.items()}
                value = headers.get("x-maskflow-session")
                if value:
                    return str(value)
        return None

    def _session_ref(self, data: dict[str, Any]) -> tuple[str, bool]:
        session_id = self._client_session_id(data)
        if session_id:
            return f"{_KEYED_PREFIX}{session_id}", False
        call_id = data.get("litellm_call_id") or (data.get("litellm_metadata") or {}).get(
            "litellm_call_id"
        )
        return f"{_EPHEMERAL_PREFIX}{call_id or id(data)}", True

    # -- hooks ----------------------------------------------------------------
    async def async_pre_call_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        cache: Any,
        data: dict[str, Any],
        call_type: str | None,
    ) -> Exception | str | dict[str, Any] | None:
        run = self.should_run_guardrail(data=data, event_type=GuardrailEventHooks.pre_call)
        if run is not True:
            return data

        ref, ephemeral = self._session_ref(data)
        store = self._store_for(ref)
        session = await store.open(ref, self._ttl_seconds)
        try:
            mask_request_data(session, data)
        except Exception:
            # SDK guarantees no PII in the exception; still, fail open rather
            # than block a legitimate request on a masking bug.
            verbose_proxy_logger.exception(
                "maskflow guardrail %r: masking raised; forwarding the request unmasked",
                self.guardrail_name,
            )
            if ephemeral:
                await store.discard(ref, session)
            return data

        await store.persist(ref, session, self._ttl_seconds)
        data.setdefault("metadata", {})["maskflow_ref"] = ref
        return data

    async def async_post_call_success_hook(
        self,
        data: dict[str, Any],
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
    ) -> Any:
        ref = (data.get("metadata") or {}).get("maskflow_ref")
        if not ref or data.get("stream") is True:
            # stream=True responses are restored in the iterator hook; the
            # assembled response here is audit-only.
            return response

        ephemeral = ref.startswith(_EPHEMERAL_PREFIX)
        store = self._store_for(ref)
        session = await store.open(ref, self._ttl_seconds)
        try:
            if _is_anthropic_message_dict(response):
                unmask_anthropic_message(session, response)
            else:
                unmask_model_response(session, response)
        finally:
            if ephemeral:
                await store.discard(ref, session)
        return response

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
        request_data: dict[str, Any],
    ) -> Any:
        ref = (request_data.get("metadata") or {}).get("maskflow_ref") if request_data else None
        if not ref:
            async for chunk in response:
                yield chunk
            return

        ephemeral = ref.startswith(_EPHEMERAL_PREFIX)
        store = self._store_for(ref)
        session = await store.open(ref, self._ttl_seconds)
        try:
            async for chunk in unmask_stream(session, response):
                yield chunk
        finally:
            if ephemeral:
                await store.discard(ref, session)

    async def aclose(self) -> None:
        await self._inprocess_store.aclose()
        if self._redis_store is not None:
            await self._redis_store.aclose()
