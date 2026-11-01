"""Patch the HTTP transports, capture the stack, return a canned response.

Three hard requirements shape this module.

**No request may reach a provider.** The audit runs somebody's test suite
with canary data in it; a request that escaped would ship synthetic
identifiers to a third party and bill them for it. Every patch here
short-circuits -- it never calls the real transport -- so the failure mode
is a captured request, never a sent one.

**The suite must keep passing.** If the patch raised, or returned nothing,
every test that asserts on a model response would fail and the run would
tell us nothing about egress. So each patch returns a minimally valid
response in the provider's own shape (`choices[0].message.content` for
OpenAI, `content[0].text` for Anthropic), which is enough for the SDKs to
parse and for most application code to proceed.

**The stack must be captured at send time.** This is the whole reason for
patching in-process rather than running a proxy: `traceback.extract_stack()`
inside the patched send is what turns "this flow looks unmasked" into "this
line sent it, through these twenty frames of SDK".

The patches are monkeypatches applied inside a context manager and undone
on exit, including on exception. We patch at the lowest layer each library
offers -- `httpx.Client.send`, not `httpx.Client.post` -- so a call through
any of the convenience wrappers is still caught exactly once.
"""

from __future__ import annotations

import contextlib
import importlib
import json
import pathlib
import traceback
from collections.abc import Iterator
from typing import Any, cast
from urllib.parse import urlparse

from .capture import Capture, CaptureStore, StackFrame

#: Hosts whose traffic the audit considers third-party egress. Kept here
#: rather than read from the sink registry because interception is about
#: *where a socket is going*, which is a different question from which SDK
#: call shape produced it -- a request to api.openai.com counts whether it
#: came from the openai package or a hand-rolled httpx call.
PROVIDER_HOSTS: frozenset[str] = frozenset(
    {
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
        "aiplatform.googleapis.com",
        "api.cohere.ai",
        "api.cohere.com",
        "api.mistral.ai",
        "api.groq.com",
        "api.together.xyz",
        "api.replicate.com",
        "openrouter.ai",
        "api.deepseek.com",
        "api.perplexity.ai",
        "api.voyageai.com",
        # Observability vendors that receive the prompt itself.
        "cloud.langfuse.com",
        "us.cloud.langfuse.com",
        "api.smith.langchain.com",
        "api.helicone.ai",
        "oai.helicone.ai",
        "gateway.helicone.ai",
        # Managed vector stores -- an embedding write carries the text.
        "api.pinecone.io",
    }
)

#: Hosts matched by suffix, for the many-subdomain vendors.
_PROVIDER_SUFFIXES: tuple[str, ...] = (
    ".openai.azure.com",
    ".pinecone.io",
    ".weaviate.network",
    ".qdrant.io",
    ".cognitiveservices.azure.com",
)

#: Frames in these packages are never the interesting answer, but they are
#: kept in the captured stack -- the report trims, the capture does not,
#: because a user debugging a surprising finding wants the whole path.
_MAX_STACK = 60


def is_provider_host(host: str) -> bool:
    """Is this host third-party LLM/observability/vector egress?"""
    lowered = (host or "").lower().split(":")[0]
    if lowered in PROVIDER_HOSTS:
        return True
    return any(lowered.endswith(suffix) for suffix in _PROVIDER_SUFFIXES)


#: Our own package directory -- frames inside it are the interception
#: machinery, not the application's path to the provider, and showing them
#: would put this file at the top of every finding.
_OWN_PREFIX = str(pathlib.Path(__file__).resolve().parents[1])


def _stack() -> tuple[StackFrame, ...]:
    """The Python stack at this point, outermost first.

    Only file / line / function -- never a source line (`extract_stack`
    would happily include one) and never a local, because the locals at an
    LLM send site are the prompt itself. Frames belonging to maskflow-audit
    are dropped: the deepest remaining frame is the application code that
    actually sent the request, which is what the report quotes.
    """
    frames = [
        f
        for f in traceback.extract_stack()
        if not str(pathlib.Path(f.filename).resolve()).startswith(_OWN_PREFIX)
    ]
    return tuple(
        StackFrame(file=f.filename, line=f.lineno or 0, function=f.name)
        for f in frames[-_MAX_STACK:]
    )


def _body_to_text(body: Any) -> str:
    """Whatever a library handed us as a request body, as searchable text."""
    if body is None:
        return ""
    if isinstance(body, str):
        return body
    if isinstance(body, (bytes, bytearray, memoryview)):
        return bytes(body).decode("utf-8", errors="replace")
    try:
        return json.dumps(body, default=str)
    except (TypeError, ValueError):
        return str(body)


def _openai_response_body() -> dict[str, Any]:
    return {
        "id": "chatcmpl-maskflow-audit",
        "object": "chat.completion",
        "created": 0,
        "model": "maskflow-audit-stub",
        "choices": [
            {
                "index": 0,
                "finish_reason": "stop",
                "message": {"role": "assistant", "content": "[maskflow audit] response withheld"},
            }
        ],
        "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        # Embeddings and moderations read different keys; including them all
        # keeps one stub valid for every OpenAI route the registry knows.
        "data": [{"object": "embedding", "index": 0, "embedding": [0.0] * 8}],
        "results": [{"flagged": False, "categories": {}, "category_scores": {}}],
    }


def _anthropic_response_body() -> dict[str, Any]:
    return {
        "id": "msg_maskflow_audit",
        "type": "message",
        "role": "assistant",
        "model": "maskflow-audit-stub",
        "stop_reason": "end_turn",
        "content": [{"type": "text", "text": "[maskflow audit] response withheld"}],
        "usage": {"input_tokens": 0, "output_tokens": 0},
    }


def _canned_body(host: str) -> dict[str, Any]:
    if "anthropic" in host:
        return _anthropic_response_body()
    return _openai_response_body()


#: The httpx-shaped transports we patch. `httpx2` is a SEPARATE
#: distribution, not a version of httpx: `openai` >= 3.0 is built on it, so
#: an audit that patches only `httpx` silently misses every modern openai
#: call -- reporting zero captures while the request reaches the provider,
#: the one failure this module must never have. Each name is optional; a
#: project that has only one is handled.
_HTTPX_MODULES: tuple[str, ...] = ("httpx", "httpx2")


@contextlib.contextmanager
def _patch_httpx(store: CaptureStore) -> Iterator[None]:
    """Patch every httpx-shaped transport that is importable."""
    with contextlib.ExitStack() as stack:
        for name in _HTTPX_MODULES:
            stack.enter_context(_patch_httpx_module(store, name))
        yield


@contextlib.contextmanager
def _patch_httpx_module(store: CaptureStore, module_name: str) -> Iterator[None]:
    """One httpx-shaped module: patch Client.send / AsyncClient.send.

    `send` is the single choke point every convenience wrapper routes
    through, so a call is caught exactly once however it was made.
    """
    try:
        httpx = importlib.import_module(module_name)
    except ImportError:
        yield
        return

    real_send = httpx.Client.send
    real_asend = httpx.AsyncClient.send

    def _capture_request(request: Any) -> Capture | None:
        host = request.url.host or ""
        if not is_provider_host(host):
            return None
        return Capture(
            host=host,
            method=request.method,
            url=str(request.url),
            payload=_body_to_text(getattr(request, "content", b"")),
            library=module_name,
            stack=_stack(),
        )

    def _response(request: Any) -> Any:
        return httpx.Response(
            200,
            json=_canned_body(request.url.host or ""),
            request=request,
            headers={"content-type": "application/json"},
        )

    def send(self: Any, request: Any, **kwargs: Any) -> Any:
        capture = _capture_request(request)
        if capture is None:
            return real_send(self, request, **kwargs)
        store.add(capture)
        return _response(request)

    async def asend(self: Any, request: Any, **kwargs: Any) -> Any:
        capture = _capture_request(request)
        if capture is None:
            return await real_asend(self, request, **kwargs)
        store.add(capture)
        return _response(request)

    httpx.Client.send = send  # type: ignore[method-assign]
    httpx.AsyncClient.send = asend  # type: ignore[method-assign]
    try:
        yield
    finally:
        httpx.Client.send = real_send  # type: ignore[method-assign]
        httpx.AsyncClient.send = real_asend  # type: ignore[method-assign]


@contextlib.contextmanager
def _patch_requests(store: CaptureStore) -> Iterator[None]:
    """requests: patch Session.request, which every helper routes through."""
    try:
        import requests
    except ImportError:
        yield
        return

    real_request = requests.Session.request

    def request(self: Any, method: str, url: str, **kwargs: Any) -> Any:
        host = urlparse(str(url)).hostname or ""
        if not is_provider_host(host):
            return real_request(self, method, url, **kwargs)

        payload = kwargs.get("json")
        if payload is None:
            payload = kwargs.get("data")
        store.add(
            Capture(
                host=host,
                method=str(method).upper(),
                url=str(url),
                payload=_body_to_text(payload),
                library="requests",
                stack=_stack(),
            )
        )

        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(_canned_body(host)).encode()
        response.headers["content-type"] = "application/json"
        response.url = str(url)
        response.request = None  # type: ignore[assignment]
        return response

    # requests' stub types `Session.request` with its full 20-parameter
    # signature; our patch takes (method, url, **kwargs), which is what every
    # caller actually uses. Casting is honest here -- the alternative is
    # restating a signature we deliberately do not depend on.
    requests.Session.request = cast(Any, request)  # type: ignore[method-assign]
    try:
        yield
    finally:
        requests.Session.request = real_request  # type: ignore[method-assign]


@contextlib.contextmanager
def _patch_aiohttp(store: CaptureStore) -> Iterator[None]:
    """aiohttp: patch ClientSession._request.

    Private, but it is the one place every public verb converges, and
    patching the verbs individually would double-count a call that goes
    through `session.request("POST", ...)`.
    """
    try:
        import aiohttp
    except ImportError:
        yield
        return

    real_request = aiohttp.ClientSession._request

    async def _request(self: Any, method: str, str_or_url: Any, **kwargs: Any) -> Any:
        host = urlparse(str(str_or_url)).hostname or ""
        if not is_provider_host(host):
            return await real_request(self, method, str_or_url, **kwargs)

        payload = kwargs.get("json")
        if payload is None:
            payload = kwargs.get("data")
        store.add(
            Capture(
                host=host,
                method=str(method).upper(),
                url=str(str_or_url),
                payload=_body_to_text(payload),
                library="aiohttp",
                stack=_stack(),
            )
        )
        raise _InterceptedRequest(
            "maskflow audit intercepted this request; it was not sent. "
            "aiohttp has no constructible offline response, so the call raises "
            "rather than silently returning something the application would "
            "misread as a real answer."
        )

    aiohttp.ClientSession._request = cast(Any, _request)
    try:
        yield
    finally:
        aiohttp.ClientSession._request = real_request


class _InterceptedRequest(RuntimeError):
    """Raised for libraries we cannot hand a canned response to.

    Carries no payload -- only the explanation. The audit records the
    capture first, so the finding survives even though the call fails.
    """


@contextlib.contextmanager
def intercept(store: CaptureStore | None = None) -> Iterator[CaptureStore]:
    """Capture every provider-bound request made inside this block.

    Nothing is sent. Each library absent from the environment is skipped,
    so this works in a project that uses only one of them.
    """
    collected = store if store is not None else CaptureStore()
    with contextlib.ExitStack() as stack:
        stack.enter_context(_patch_httpx(collected))
        stack.enter_context(_patch_requests(collected))
        stack.enter_context(_patch_aiohttp(collected))
        yield collected
