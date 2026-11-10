"""One error schema for every API error response."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id


class ErrorDetail(BaseModel):
    loc: list[str | int] | None = None
    msg: str
    type: str


class ErrorBody(BaseModel):
    code: str
    message: str
    request_id: str | None = None
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class AppError(Exception):
    status_code = 400
    code = "bad_request"
    message = "Bad request."

    def __init__(self, message: str | None = None, *, headers: dict[str, str] | None = None):
        super().__init__(message or self.message)
        self.message = message or self.message
        self.headers = headers


class NotAuthenticatedError(AppError):
    status_code = 401
    code = "not_authenticated"
    message = "Authentication required."


class InvalidCredentialsError(AppError):
    status_code = 401
    code = "invalid_credentials"
    message = "Invalid email or password."


class CsrfRejectedError(AppError):
    status_code = 403
    code = "csrf_rejected"
    message = "Request rejected by cross-site request protection."


class ConsentRequiredError(AppError):
    status_code = 403
    code = "consent_required"
    message = "Active consent to the current notice is required."


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Resource not found."


class PayloadTooLargeError(AppError):
    status_code = 413
    code = "file_too_large"
    message = "The file exceeds the upload size limit."


class UnsupportedFileTypeError(AppError):
    status_code = 415
    code = "unsupported_file_type"
    message = "Only PDF files are accepted."


class ConflictError(AppError):
    status_code = 409
    code = "conflict"
    message = "Resource already exists."


class ConsentNoticeOutdatedError(AppError):
    status_code = 409
    code = "consent_notice_outdated"
    message = "The consent notice has changed. Review the current notice and try again."


class RateLimitedError(AppError):
    status_code = 429
    code = "rate_limited"
    message = "Too many attempts. Try again later."


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"
    message = "Service temporarily unavailable."


_HTTP_CODES = {404: "not_found", 405: "method_not_allowed", 401: "not_authenticated"}


def error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    details: list[ErrorDetail] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(code=code, message=message, request_id=get_request_id(), details=details)
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(exclude_none=True), headers=headers
    )


async def _app_error(_request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, headers=exc.headers)


async def _http_error(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_response(exc.status_code, code, message, headers=getattr(exc, "headers", None))


async def _validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Never echo submitted input (it may contain passwords or PHI): keep loc/msg/type only.
    details = [
        ErrorDetail(loc=list(err.get("loc", ())), msg=str(err.get("msg", "")), type=err["type"])
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", "Request validation failed.", details=details)


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, _app_error)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, _http_error)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, _validation_error)  # type: ignore[arg-type]


def internal_error_body() -> dict[str, Any]:
    body = ErrorBody(
        code="internal_error", message="Internal server error.", request_id=get_request_id()
    )
    return ErrorResponse(error=body).model_dump(exclude_none=True)
