"""Transport-level protections: request body cap and per-client rate limiting.

Both exist to bound what a single client can cost the process. Neither knows anything
about the RAG pipeline — they run before the service is ever called.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable

from fastapi import HTTPException
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..observability import API_REQUESTS, bind_trace_id
from .errors import error_response

# Upper bound on distinct clients tracked at once. Without a cap, a source rotating its
# address would grow the bucket dict without limit — turning a denial-of-service defense
# into a memory exhaustion vector.
_MAX_TRACKED_CLIENTS = 10_000


class RateLimiter:
    """Sliding-window request limiter, keyed by client.

    A sliding window rather than a fixed one: a fixed window lets a client spend its
    whole budget at the end of one window and again at the start of the next, so a
    "30 per minute" limit permits 60 requests in a couple of seconds across the boundary
    — precisely the burst the limit exists to prevent.

    NOT thread-safe, by design. Call it only from the event loop (i.e. from an
    ``async def`` dependency), where the deque mutations cannot interleave. A plain
    ``def`` dependency would run in the threadpool and race.

    Per-process only: restarting the app clears every budget, and a second replica keeps
    its own. See DECISIONS.md D23 for why that is acceptable here and what would replace
    it in a real multi-replica deployment.
    """

    def __init__(
        self,
        max_requests: int,
        window_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._clock = clock
        self._buckets: dict[str, deque[float]] = {}

    def check(self, key: str) -> float | None:
        """Record a hit and return ``None``, or return seconds until budget frees up.

        A return value means the request was **rejected** — no hit is recorded for it, so
        a client hammering a closed door doesn't extend its own penalty.
        """

        now = self._clock()
        cutoff = now - self._window
        hits = self._buckets.setdefault(key, deque())
        while hits and hits[0] <= cutoff:
            hits.popleft()

        if len(hits) >= self._max:
            return hits[0] + self._window - now

        hits.append(now)
        self._prune(now)
        return None

    def _prune(self, now: float) -> None:
        """Drop clients whose whole window has expired, once the dict grows too large."""

        if len(self._buckets) <= _MAX_TRACKED_CLIENTS:
            return
        cutoff = now - self._window
        stale = [key for key, hits in self._buckets.items() if not hits or hits[-1] <= cutoff]
        for key in stale:
            del self._buckets[key]


def client_key(request: Request, trusted_proxy_hops: int) -> str:
    """Identify the caller for rate-limiting purposes.

    ``X-Forwarded-For`` is read **from the right**: the rightmost entries were appended
    by proxies we control, while anything further left was supplied by the client and can
    be forged. Trusting the leftmost entry — the common mistake — would let any caller
    evade the limit with one header. With ``trusted_proxy_hops=0`` the header is ignored
    entirely and the socket peer is used, which is correct when nothing sits in front.
    """

    if trusted_proxy_hops > 0:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            hops = [part.strip() for part in forwarded.split(",") if part.strip()]
            if len(hops) >= trusted_proxy_hops:
                return hops[-trusted_proxy_hops]
    return request.client.host if request.client else "unknown"


class TraceIdMiddleware:
    """Bind a trace id for the whole request, error handlers included.

    Without this, a request rejected before the pipeline runs (413, 422, 429) would have
    no id at all — and those are exactly the responses a user is most likely to report.
    The RAG engine mints and binds its own id once it starts work, shadowing this one for
    the pipeline's own log lines; the route handler re-stamps its completion line with
    that inner id so the two views join up. See DECISIONS.md D22.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        with bind_trace_id() as trace_id:
            # Also recorded on the scope, because the context var is not enough on its
            # own: Starlette's ServerErrorMiddleware — which renders unhandled
            # exceptions — sits *outside* every user middleware, so by the time the 500
            # handler runs this `with` block has already unwound and the context var is
            # back to unbound. The scope dict is passed by reference the whole way out,
            # so it still carries the id. Without this a 500 tells the user to quote
            # trace id "-", and its own log line cannot be joined to the request.
            scope.setdefault("state", {})["trace_id"] = trace_id
            await self.app(scope, receive, send)


class _BodyTooLarge(HTTPException):
    """Raised from the wrapped receive channel when a streamed body exceeds the cap.

    An ``HTTPException`` specifically, and FastAPI's rather than Starlette's: FastAPI
    wraps *any* other exception raised while parsing a request body into a generic
    400 ("There was an error parsing the body"), which would mask this as a client
    syntax error. HTTPException is the one type it re-raises, so this reaches the shared
    error handler and comes out as a 413 like the declared-length path does.
    """

    def __init__(self, message: str) -> None:
        super().__init__(
            status_code=413,
            detail={"code": "payload_too_large", "message": message},
        )


class BodySizeLimitMiddleware:
    """Reject request bodies above ``max_bytes``.

    Written as pure ASGI rather than ``BaseHTTPMiddleware`` on purpose: the latter runs
    the downstream app in a separate anyio task, which makes an exception raised from a
    wrapped ``receive`` unreliable to catch — exactly the mechanism this needs.

    Two paths: a declared ``Content-Length`` is rejected before a single body byte is
    read; a chunked body with no declared length is counted as it streams and aborted as
    soon as it crosses the limit.

    ``route_overrides`` lets one path use a different (larger) cap than the general one —
    ``/api/ingest`` accepts a real file, which is bigger than any JSON request this API
    otherwise takes. Matched by exact path, checked before the general limit applies, so
    every other route is unaffected.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_bytes: int,
        message: str,
        route_overrides: dict[str, tuple[int, str]] | None = None,
    ) -> None:
        self.app = app
        self.max_bytes = max_bytes
        self.message = message
        self.route_overrides = route_overrides or {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        max_bytes, message = self.route_overrides.get(
            scope.get("path", ""), (self.max_bytes, self.message)
        )

        declared = Headers(scope=scope).get("content-length")
        if declared and declared.isdigit() and int(declared) > max_bytes:
            await self._reject(scope, receive, send, message)
            return

        seen = 0

        async def counting_receive() -> Message:
            nonlocal seen
            message_in = await receive()
            if message_in["type"] == "http.request":
                seen += len(message_in.get("body", b""))
                if seen > max_bytes:
                    raise _BodyTooLarge(message)
            return message_in

        await self.app(scope, counting_receive, send)

    async def _reject(
        self, scope: Scope, receive: Receive, send: Send, message: str
    ) -> None:
        """Answer a declared-oversize request without invoking the app at all.

        This runs before routing, so there is no matched route to label the metric with
        — hence ``endpoint="unknown"``, which is still a fixed, low-cardinality value.
        """

        API_REQUESTS.labels(endpoint="unknown", outcome="payload_too_large").inc()
        response = error_response(
            status_code=413,
            code="payload_too_large",
            message=message,
        )
        await response(scope, receive, send)
