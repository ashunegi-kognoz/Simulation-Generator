"""FastAPI application factory.

Wires the authoring/runtime/group routers, maps service errors to HTTP status
codes, and (outside the test environment) starts the in-process background job
worker, cancelling it cleanly on shutdown.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.middleware.base import BaseHTTPMiddleware

from app.api import auth, authoring, groups, runtime
from app.config import get_settings
from app.db import dispose_engine
from app.jobs.runner import worker_loop
from app.services.errors import ConflictError, NotFoundError, StateError


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Fixed-window per-client rate limit (in-process; no Redis).

    Bounds abuse on a single worker. Disabled in the test environment so the suite
    stays deterministic. For multi-worker production, front with a shared limiter.
    """

    def __init__(self, app, limit_per_minute: int) -> None:
        super().__init__(app)
        self._limit = limit_per_minute
        self._window: dict[str, tuple[int, int]] = defaultdict(lambda: (0, 0))

    async def dispatch(self, request: Request, call_next):
        client = request.client.host if request.client else "anon"
        minute = int(time.time() // 60)
        window_minute, count = self._window[client]
        if window_minute != minute:
            window_minute, count = minute, 0
        count += 1
        self._window[client] = (window_minute, count)
        if count > self._limit:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Slow down and retry shortly."},
            )
        return await call_next(request)


def _register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(NotFoundError)
    async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(StateError)
    async def _state(_: Request, exc: StateError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def _conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=409, content={"detail": str(exc)})

    @app.exception_handler(ValidationError)
    async def _validation(_: Request, exc: ValidationError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": exc.errors()})

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        # Never leak internals to the client; details are logged server-side.
        return JSONResponse(status_code=500, content={"detail": "Internal server error."})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    worker: asyncio.Task | None = None
    if settings.app_env != "test":
        worker = asyncio.create_task(worker_loop())
    try:
        yield
    finally:
        if worker is not None:
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
        await dispose_engine()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="The Allocation Room Platform",
        version="0.3.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "env": settings.app_env, "provider": settings.llm_provider}

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    if settings.app_env != "test":
        app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute)

    app.include_router(auth.router)
    app.include_router(authoring.router)
    app.include_router(runtime.router)
    app.include_router(groups.router)
    _register_exception_handlers(app)
    return app


app = create_app()
