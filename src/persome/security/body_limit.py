"""Pure-ASGI request-body limits shared by REST and HTTP MCP."""

from __future__ import annotations

import threading
from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

DEFAULT_MAX_REQUEST_BODY_BYTES = 12 * 1024 * 1024
DEFAULT_MAX_CONCURRENT_REQUESTS = 16


class RequestBodyLimitMiddleware:
    """Reject oversized fixed-length and chunked requests before route parsing.

    The middleware buffers at most ``max_bytes`` so it can return a deterministic
    413 before FastAPI or FastMCP starts a response.  This is appropriate for the
    Runtime's JSON request protocols, which already require a complete request
    before doing useful work.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int = DEFAULT_MAX_REQUEST_BODY_BYTES) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = int(max_bytes)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        content_lengths = headers.getlist("content-length")
        if len(content_lengths) > 1:
            await self._reject(scope, receive, send, 400, "ambiguous Content-Length")
            return
        content_length = content_lengths[0] if content_lengths else None
        if content_length is not None:
            try:
                declared = int(content_length)
            except ValueError:
                await self._reject(scope, receive, send, 400, "invalid Content-Length")
                return
            if declared < 0:
                await self._reject(scope, receive, send, 400, "invalid Content-Length")
                return
            if declared > self.max_bytes:
                await self._reject(scope, receive, send, 413, "request body too large")
                return

        buffered: list[Message] = []
        total = 0
        while True:
            message = await receive()
            buffered.append(message)
            if message["type"] == "http.disconnect":
                return
            if message["type"] != "http.request":
                continue
            total += len(message.get("body", b""))
            if total > self.max_bytes:
                await self._reject(scope, receive, send, 413, "request body too large")
                return
            if not message.get("more_body", False):
                break

        replay = _ReplayReceive(buffered, receive)
        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(
        scope: Scope,
        receive: Receive,
        send: Send,
        status_code: int,
        detail: str,
    ) -> None:
        await JSONResponse(
            {"success": False, "error": detail},
            status_code=status_code,
            headers={"Connection": "close", "Cache-Control": "no-store"},
        )(scope, receive, send)


class _ReplayReceive:
    def __init__(self, messages: Sequence[Message], fallback: Receive) -> None:
        self._messages = iter(messages)
        self._fallback = fallback

    async def __call__(self) -> Message:
        try:
            return next(self._messages)
        except StopIteration:
            # Streaming responses (notably SSE) keep listening for the real
            # client disconnect after the request body has been consumed.  An
            # immediate synthetic empty request here would create a hot loop
            # and starve the response producer.
            return await self._fallback()


class RequestConcurrencyLimitMiddleware:
    """Fail fast when too many HTTP requests are already in flight.

    A short, synchronous lock protects the counter without binding the
    middleware to one asyncio event loop.  This matters for in-process tests,
    which may exercise the same app through more than one TestClient loop.
    Streaming responses keep their slot until the stream actually closes.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        max_concurrent: int = DEFAULT_MAX_CONCURRENT_REQUESTS,
    ) -> None:
        if max_concurrent <= 0:
            raise ValueError("max_concurrent must be positive")
        self.app = app
        self.max_concurrent = int(max_concurrent)
        self._active = 0
        self._lock = threading.Lock()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        with self._lock:
            if self._active >= self.max_concurrent:
                accepted = False
            else:
                self._active += 1
                accepted = True
        if not accepted:
            await JSONResponse(
                {"success": False, "error": "too many concurrent requests"},
                status_code=503,
                headers={
                    "Retry-After": "1",
                    "Cache-Control": "no-store",
                    "Connection": "close",
                },
            )(scope, receive, send)
            return

        try:
            await self.app(scope, receive, send)
        finally:
            with self._lock:
                self._active -= 1
