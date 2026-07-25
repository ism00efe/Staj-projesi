"""Application factory and launch glue.

``create_app`` takes an already-built service rather than constructing one, which keeps
``service.build_service`` the single composition root (see CLAUDE.md) and means importing
this module never loads an embedding model. Tests hand it a fake in one line.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..config import Settings, configure_logging, get_settings
from ..service import AssistantService, build_service
from .errors import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from .middleware import BodySizeLimitMiddleware, RateLimiter, TraceIdMiddleware
from .routes import build_router

logger = logging.getLogger(__name__)

_STATIC_DIR = Path(__file__).resolve().parent.parent / "ui" / "static"

_DESCRIPTION = """
Ödeme sistemleri bilgi tabanı üzerinde soru yanıtlama ve log analizi.

Tüm istemciler (web arayüzü, Visual Studio eklentisi) aynı `POST /api/analyze`
uç noktasını kullanır. Girdilerdeki hassas veriler (kart numarası, TCKN, e-posta,
IP, telefon, token) sunucu tarafında **maskelendikten sonra** işlenir.
""".strip()


def create_app(service: AssistantService, settings: Settings) -> FastAPI:
    """Build the ASGI application around an existing service."""

    app = FastAPI(
        title="Ödeme Sistemleri Asistanı",
        description=_DESCRIPTION,
        version="0.1.0",
    )

    limiter = (
        RateLimiter(
            max_requests=settings.api_rate_limit_requests,
            window_seconds=settings.api_rate_limit_window_seconds,
        )
        if settings.api_rate_limit_enabled
        else None
    )

    # Order matters: the last middleware added is the outermost. TraceIdMiddleware must
    # wrap the body-size check so that a rejected oversized request still carries an id.
    limit_mb = settings.api_max_body_bytes // 1_000_000
    app.add_middleware(
        BodySizeLimitMiddleware,
        max_bytes=settings.api_max_body_bytes,
        message=f"İstek çok büyük (limit: {limit_mb} MB).",
    )
    app.add_middleware(TraceIdMiddleware)

    # `add_exception_handler` is typed to take a handler for the base `Exception`,
    # because the registry it writes into is heterogeneous. Every real handler narrows to
    # the type it registered for, so the parameter is contravariant in a way the stub
    # cannot express — narrow, deliberate suppressions rather than widening the handlers
    # to `Exception` and casting inside them.
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    app.include_router(build_router(service, settings, limiter))

    # Constructed eagerly: if the package was installed without its static assets, this
    # raises at startup instead of serving mysterious 404s later.
    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

    @app.get("/", include_in_schema=False)
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    return app


def main() -> None:  # pragma: no cover - launch glue, exercised manually
    """Launch the API + web UI."""

    import uvicorn

    configure_logging()
    settings = get_settings()
    service = build_service(settings)
    logger.info("Knowledge base contains %d chunks.", service.knowledge_base_size())
    app = create_app(service, settings)

    # The app object is passed directly rather than as an import string. An import string
    # is only needed for `reload` or `workers > 1`, and both are wrong here: the rate
    # limiter's state is per-process, Chroma runs in-process, and every extra worker
    # would load its own copy of the embedding and re-ranking models.
    #
    # log_config=None stops uvicorn installing its own handlers, so its lines propagate
    # to the root JSON handler configure_logging() just installed. access_log=False
    # because uvicorn's access formatter renders the client IP into every line — an
    # address is one of the categories sanitization.py exists to mask.
    uvicorn.run(
        app,
        host=settings.app_host,
        port=settings.app_port,
        log_config=None,
        access_log=False,
    )
