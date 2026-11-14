"""Request-ID propagation, path-only access logging and last-resort error handling (pure ASGI)."""

import json
import re
import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

log = structlog.get_logger("app.http")


def get_request_id() -> str | None:
    return _request_id.get()


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, header_name: str = "X-Request-ID") -> None:
        self.app = app
        self.header_name = header_name

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(self.header_name, "")
        request_id = incoming if _VALID_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        token = _request_id.set(request_id)
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        started = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                headers = MutableHeaders(scope=message)
                headers[self.header_name] = request_id
                headers.setdefault("X-Content-Type-Options", "nosniff")
                headers.setdefault("Referrer-Policy", "no-referrer")
                headers.setdefault("X-Frame-Options", "DENY")
                if scope["path"].startswith("/api/"):
                    headers.setdefault("Cache-Control", "no-store")
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("http.unhandled_error")
            if response_started:
                raise
            from app.core.errors import internal_error_body  # local import avoids a cycle

            payload = json.dumps(internal_error_body()).encode()
            await send_wrapper(
                {
                    "type": "http.response.start",
                    "status": 500,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"content-length", str(len(payload)).encode()),
                    ],
                }
            )
            await send_wrapper({"type": "http.response.body", "body": payload})
        finally:
            log.info(
                "http.request",
                method=scope["method"],
                path=scope["path"],  # path only: query strings are never logged
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
            _request_id.reset(token)
            structlog.contextvars.clear_contextvars()
