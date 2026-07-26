"""HTTP routes.

A thin controller: it validates the envelope, enforces transport limits, calls
:class:`AssistantService`, and maps the result onto the wire format. No retrieval,
prompting, sanitization, or citation logic lives here — that is all behind the service,
and duplicating any of it here would give the three clients a second, divergent copy of
the pipeline's behavior.
"""

from __future__ import annotations

import logging
import math

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile

from ..config import Settings
from ..observability import API_REQUEST_DURATION, get_trace_id, log_step
from ..rag import EmptyContent, UnsupportedFileType, extract_text
from ..service import AssistantService
from .errors import record_outcome
from .middleware import RateLimiter, client_key
from .schemas import AnalyzeRequest, AnalyzeResponse, HealthResponse, IngestResponse

logger = logging.getLogger(__name__)

_ANALYZE_ENDPOINT = "/api/analyze"
_INGEST_ENDPOINT = "/api/ingest"


def build_router(
    service: AssistantService,
    settings: Settings,
    limiter: RateLimiter | None,
    upload_limiter: RateLimiter | None = None,
) -> APIRouter:
    """Build the ``/api`` router around an already-constructed service."""

    async def enforce_rate_limit(request: Request) -> None:
        """Reject callers over their budget.

        Declared ``async`` deliberately: it therefore runs on the event loop, where the
        limiter's non-thread-safe deques cannot interleave. A plain ``def`` dependency
        would be handed to the threadpool and race.

        Attached to this router rather than installed as middleware so it covers
        ``/api/*`` only — as middleware it would also count the page's own stylesheet and
        script, and a single page load would rate-limit itself.
        """

        if limiter is None:
            return
        wait_seconds = limiter.check(client_key(request, settings.api_trusted_proxy_hops))
        if wait_seconds is None:
            return

        retry_after = max(1, math.ceil(wait_seconds))
        logger.warning(
            "request rate limited",
            extra={"step": "api.rate_limit", "status": "rejected", "status_code": 429},
        )
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": (
                    f"Çok fazla istek gönderdiniz. Lütfen {retry_after} saniye sonra "
                    "tekrar deneyin."
                ),
            },
            headers={"Retry-After": str(retry_after)},
        )

    async def enforce_upload_rate_limit(request: Request) -> None:
        """A second, much tighter budget layered on top of ``enforce_rate_limit``.

        Ingesting a file costs far more than answering a question (embedding + chunking
        + a Chroma write, on top of everything ``/api/analyze`` already does) and, unlike
        an answer, permanently adds to what every future query can retrieve — so this is
        deliberately a separate, smaller bucket rather than a share of the general one.
        """

        if upload_limiter is None:
            return
        wait_seconds = upload_limiter.check(client_key(request, settings.api_trusted_proxy_hops))
        if wait_seconds is None:
            return

        retry_after = max(1, math.ceil(wait_seconds))
        logger.warning(
            "upload rate limited",
            extra={"step": "api.upload_rate_limit", "status": "rejected", "status_code": 429},
        )
        raise HTTPException(
            status_code=429,
            detail={
                "code": "rate_limited",
                "message": (
                    f"Çok fazla belge yükleme isteği gönderdiniz. Lütfen {retry_after} "
                    "saniye sonra tekrar deneyin."
                ),
            },
            headers={"Retry-After": str(retry_after)},
        )

    router = APIRouter(prefix="/api", dependencies=[Depends(enforce_rate_limit)])

    @router.post(
        "/analyze",
        response_model=AnalyzeResponse,
        summary="Bir soruyu ve/veya log içeriğini analiz et",
    )
    def analyze(payload: AnalyzeRequest, request: Request) -> AnalyzeResponse:
        """Answer a question, optionally grounded by log text.

        Declared ``def``, not ``async def``: the service blocks for seconds (embedding,
        cross-encoder re-ranking, then the LLM call). On the event loop that would
        serialize every other request — including the UI's own static assets. A sync
        handler is dispatched to the threadpool instead, and the bound trace id follows
        it there because anyio copies the context into the worker.
        """

        _reject_oversized_log(payload.file_content, settings)

        with API_REQUEST_DURATION.labels(endpoint=_ANALYZE_ENDPOINT).time():
            with log_step("api.analyze", logger) as rec:
                answer = service.ask(payload.query, payload.file_content)
                # No trace id set here: the engine inherits the one bound by
                # TraceIdMiddleware, so this line and the pipeline's own
                # sanitize/retrieve/generate/cite lines already share it — including
                # when the pipeline raises and this step logs an error instead.
                rec.set(
                    status_code=200,
                    citation_count=len(answer.citations),
                    redaction_count=len(answer.redactions),
                )

        record_outcome(request, "ok")
        # The engine normally supplies its own id; fall back to the request-scoped one
        # bound by TraceIdMiddleware so a response is never left without something the
        # user can quote back.
        return AnalyzeResponse.from_answer(answer, fallback_trace_id=get_trace_id())

    @router.post(
        "/ingest",
        response_model=IngestResponse,
        summary="Bilgi tabanına yeni bir belge ekle",
        dependencies=[Depends(enforce_upload_rate_limit)],
    )
    # File(...) as a default is FastAPI's own required idiom for a file parameter.
    def ingest_document(request: Request, file: UploadFile = File(...)) -> IngestResponse:  # noqa: B008
        """Add one uploaded document (PDF or plain text) to the knowledge base.

        Declared ``def`` for the same reason as ``analyze``: extracting a PDF, embedding,
        and writing to Chroma all block. Reads via the underlying ``SpooledTemporaryFile``
        rather than ``await file.read()`` — this handler already runs off the event loop,
        so there is nothing to gain from the async form and it would not type-check inside
        a plain ``def`` function.

        Never resets the collection: ``AssistantService.ingest_document`` only appends, so
        the corpus loaded at startup is untouched and the new chunks are searchable by the
        very next query.
        """

        filename = file.filename or "upload"
        content = file.file.read()
        _reject_oversized_upload(len(content), settings)

        try:
            text = extract_text(filename, content)
        except EmptyContent as exc:
            raise HTTPException(
                status_code=400, detail={"code": "empty_file", "message": str(exc)}
            ) from exc
        except UnsupportedFileType as exc:
            raise HTTPException(
                status_code=415, detail={"code": "unsupported_file_type", "message": str(exc)}
            ) from exc

        with API_REQUEST_DURATION.labels(endpoint=_INGEST_ENDPOINT).time():
            with log_step(
                "api.ingest", logger, upload_filename=filename, file_size_bytes=len(content)
            ) as rec:
                chunks_added, redactions = service.ingest_document(text, filename)
                rec.set(chunk_count=chunks_added, redaction_count=len(redactions))

        record_outcome(request, "ok")
        return IngestResponse.build(
            filename=filename,
            chunks_added=chunks_added,
            redactions=redactions,
            trace_id=get_trace_id(),
        )

    @router.get("/health", response_model=HealthResponse, summary="Servis durumu")
    def health(request: Request) -> HealthResponse:
        """Liveness plus the limits a client needs before it submits anything.

        Limits are served rather than hardcoded in each client so the web UI and the
        Visual Studio extension check against the values this process actually enforces,
        instead of a copy that drifts out of step with ``config.py``.
        """

        record_outcome(request, "ok")
        return HealthResponse(
            status="ok",
            knowledge_base_size=service.knowledge_base_size(),
            max_upload_bytes=settings.max_upload_bytes,
            max_document_upload_bytes=settings.api_max_upload_bytes,
        )

    return router


def _reject_oversized_log(file_content: str | None, settings: Settings) -> None:
    """Apply the existing upload cap to log text arriving over HTTP.

    ``AssistantService.ask_with_log_file`` enforces ``MAX_UPLOAD_BYTES`` by stat-ing a
    file before reading it. This API never sees a file — only text — so that gate cannot
    be reused and is re-derived here against the encoded byte length. Without it, the
    upload limit would silently stop applying the moment the interface changed.
    """

    if file_content is None:
        return
    if len(file_content.encode("utf-8")) <= settings.max_upload_bytes:
        return

    limit_mb = settings.max_upload_bytes // 1_000_000
    raise HTTPException(
        status_code=413,
        detail={
            "code": "payload_too_large",
            "message": f"Log içeriği çok büyük (limit: {limit_mb} MB).",
        },
    )


def _reject_oversized_upload(size_bytes: int, settings: Settings) -> None:
    """Re-derive the upload cap against the file's exact decoded size.

    ``BodySizeLimitMiddleware`` already bounds the whole multipart envelope to this same
    ``api_max_upload_bytes`` limit before this handler runs, and the envelope can only be
    larger than the file it carries — so in practice this can never fire over real HTTP
    while that middleware is wired up as it is today. It stays as an explicit, named
    check anyway: the same belt-and-suspenders shape as ``_reject_oversized_log`` for
    ``/api/analyze``, so this route does not silently depend on transport-layer wiring it
    does not control for something as basic as its own size limit.
    """

    if size_bytes <= settings.api_max_upload_bytes:
        return

    limit_mb = settings.api_max_upload_bytes // 1_000_000
    raise HTTPException(
        status_code=413,
        detail={
            "code": "payload_too_large",
            "message": f"Dosya çok büyük (limit: {limit_mb} MB).",
        },
    )
