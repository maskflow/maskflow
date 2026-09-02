"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import Settings, get_settings
from .errors import GatewayError
from .observability.logging import configure_logging
from .ratelimit import RateLimiter
from .routes import ROUTERS
from .sessions import SessionManager, build_snapshot_store
from .upstream import Upstream

logger = logging.getLogger("maskflow_gateway")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(json_logs=settings.json_logs, level=settings.log_level)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = build_snapshot_store(settings)
        app.state.settings = settings
        app.state.snapshot_store = store
        app.state.session_manager = SessionManager(store, settings)
        app.state.upstream = Upstream(settings)
        app.state.rate_limiter = RateLimiter(settings, store.redis)
        logger.info(
            "gateway starting",
            extra={
                "version": __version__,
                "ner": settings.ner,
                "sessions": "redis" if settings.redis_url else "in-process",
                "rate_limit_per_minute": settings.rate_limit_per_minute,
            },
        )
        try:
            yield
        finally:
            await app.state.upstream.aclose()
            await app.state.session_manager.aclose()

    app = FastAPI(title="MaskFlow Gateway", version=__version__, lifespan=lifespan)

    if settings.cors_allow_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_allow_origins,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.exception_handler(GatewayError)
    async def _gateway_error_handler(_request: Request, exc: GatewayError) -> JSONResponse:
        headers = {}
        retry_after = getattr(exc, "retry_after_seconds", None)
        if retry_after is not None:
            headers["Retry-After"] = str(int(retry_after) + 1)
        return JSONResponse(exc.to_body(), status_code=exc.status_code, headers=headers)

    for router in ROUTERS:
        app.include_router(router)

    return app
