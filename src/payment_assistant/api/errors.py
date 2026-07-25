"""Error rendering for the HTTP API.

Every failure leaves this module in the same envelope (:class:`ErrorResponse`), so a
client has exactly one error shape to handle regardless of which layer failed.

SECURITY: no handler here may echo request content back to the caller or into a log
line. That is not a style preference — see :func:`validation_exception_handler` for the
specific leak this prevents.
"""

from __future__ import annotations

import logging

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..observability import API_REQUESTS, get_trace_id, has_trace_id
from .schemas import ErrorBody, ErrorResponse

logger = logging.getLogger(__name__)

# Status codes that carry a specific machine-readable code when the raiser didn't set one.
_CODE_BY_STATUS = {
    404: "not_found",
    405: "method_not_allowed",
}

_MESSAGE_BY_STATUS = {
    404: "Sayfa bulunamadı.",
    405: "Bu adres için geçersiz istek yöntemi.",
}


def trace_id_of(request: Request) -> str:
    """The request's trace id, preferring the one stashed on the scope.

    The context var is correct while the request is in flight, but an unhandled
    exception is rendered outside the scope that bound it (see ``TraceIdMiddleware``),
    where the var reads as unbound. The scope survives, so it is the reliable source.
    """

    if has_trace_id():
        return get_trace_id()
    state = request.scope.get("state") or {}
    return state.get("trace_id") or get_trace_id()


def endpoint_of(request: Request) -> str:
    """Resolve the matched route *template* for metric labelling.

    Never the raw request path: that is unbounded cardinality, and a path can carry
    user-supplied content.
    """

    route = request.scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unknown"


def record_outcome(request: Request, outcome: str) -> None:
    """Count one request against a fixed outcome word."""

    API_REQUESTS.labels(endpoint=endpoint_of(request), outcome=outcome).inc()


def error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    fields: list[str] | None = None,
    trace_id: str | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Build the one and only error envelope."""

    payload = ErrorResponse(
        error=ErrorBody(code=code, message=message, fields=fields),
        trace_id=trace_id or get_trace_id(),
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(),
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Render a 422 without echoing what the client sent.

    FastAPI's default handler returns each error's ``input`` — the offending value — in
    the response body. For this API that value is raw, unsanitized user content (a query
    or a log excerpt), so the default would hand it straight back out and, if the errors
    were ever logged, write it to disk. Only the dotted field paths leave this function;
    ``exc.errors()`` is never passed to a logger.
    """

    fields = sorted({".".join(str(part) for part in err["loc"]) for err in exc.errors()})
    record_outcome(request, "validation_error")
    logger.warning(
        "request validation failed",
        extra={"step": "api.validate", "status": "error", "status_code": 422},
    )
    return error_response(
        status_code=422,
        code="validation_error",
        message="İstek geçersiz: gönderilen alanlar beklenen biçimde değil.",
        fields=fields,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Render deliberate ``HTTPException``s (413, 429, 404, ...) in the shared envelope.

    A handler that raises passes ``detail`` as a ``{"code", "message"}`` dict; anything
    else (Starlette's own 404/405) falls back to a status-derived pair.
    """

    if isinstance(exc.detail, dict):
        code = str(exc.detail.get("code", "http_error"))
        message = str(exc.detail.get("message", ""))
    else:
        code = _CODE_BY_STATUS.get(exc.status_code, "http_error")
        message = _MESSAGE_BY_STATUS.get(exc.status_code, "İstek işlenemedi.")

    record_outcome(request, code)
    # `exc.headers` carries Retry-After on a 429 — dropping it here would strip the one
    # piece of information that tells a client when to come back.
    return error_response(
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=dict(exc.headers) if exc.headers else None,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Turn any uncaught exception into a 500 that leaks nothing.

    The exception text can name internal hosts, ports, and file paths, so it goes to the
    logs (with a stack trace) and never to the client. The trace id is the bridge: the
    user is told to quote it, and it matches the log line.
    """

    trace_id = trace_id_of(request)
    record_outcome(request, "internal_error")
    logger.exception(
        "unhandled error while serving request",
        # Stamped explicitly rather than left to TraceIdFilter: this runs outside the
        # binding, so the filter would fill in "-" and orphan the line.
        extra={
            "step": "api.request",
            "status": "error",
            "status_code": 500,
            "trace_id": trace_id,
        },
    )
    return error_response(
        status_code=500,
        code="internal_error",
        message=(
            "Beklenmeyen bir hata oluştu. Destek ekibine şu izleme kimliğini iletin: "
            f"{trace_id}"
        ),
        trace_id=trace_id,
    )
