"""API-level error handling and library exception mapping."""

from __future__ import annotations

import io
import traceback as tb

from fastapi import Request
from fastapi.responses import JSONResponse
from omnidapter import (
    AuthError,
    ConnectionNotFoundError,
    InvalidCredentialFormatError,
    ProviderAPIError,
    RateLimitError,
    ScopeInsufficientError,
    TransportError,
    UnsupportedCapabilityError,
)

from omnidapter_server.models.connection import ConnectionStatus


def _format_exception_traceback(exc: Exception) -> str:
    """Format exception traceback as a string."""
    buf = io.StringIO()
    tb.print_exception(type(exc), exc, exc.__traceback__, file=buf)
    return buf.getvalue()


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
    exc: Exception | None = None,
    env: str = "PROD",
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    body = {
        "error": {"code": code, "message": message},
        "meta": {"request_id": request_id},
    }
    if details:
        body["error"]["details"] = details  # type: ignore[index]

    # Include exception details in LOCAL/DEV for debugging
    if exc and env in ("LOCAL", "DEV"):
        if "details" not in body["error"]:  # type: ignore[operator]
            body["error"]["details"] = {}  # type: ignore[index]
        body["error"]["details"].update(
            {  # type: ignore[index]
                "exception_type": type(exc).__name__,
                "exception": str(exc),
                "traceback": _format_exception_traceback(exc),
            }
        )

    return JSONResponse(status_code=status_code, content=body)


def map_library_exception(
    exc: Exception,
    request: Request,
) -> JSONResponse:
    """Map Omnidapter library exceptions to HTTP responses."""
    # Read environment from app state; default to PROD for safety
    env = getattr(request.app.state, "omnidapter_env", "PROD")

    if isinstance(exc, RateLimitError):
        details = {"provider_key": exc.provider_key}
        if exc.status_code:
            details["status_code"] = str(exc.status_code)
        if exc.provider_request_id:
            details["provider_request_id"] = exc.provider_request_id
        return _error_response(request, 429, "provider_rate_limited", str(exc), details, env=env)

    if isinstance(exc, ProviderAPIError):
        details = {"provider_key": exc.provider_key}
        if exc.status_code:
            details["status_code"] = str(exc.status_code)
        if exc.provider_request_id:
            details["provider_request_id"] = exc.provider_request_id
        return _error_response(request, 502, "provider_error", str(exc), details, env=env)

    if isinstance(exc, ConnectionNotFoundError):
        return _error_response(request, 404, "connection_not_found", str(exc), env=env)

    if isinstance(exc, ScopeInsufficientError):
        return _error_response(
            request,
            403,
            "scope_insufficient",
            str(exc),
            {
                "required_scopes": exc.required_scopes,
                "granted_scopes": exc.granted_scopes,
            },
            env=env,
        )

    if isinstance(exc, UnsupportedCapabilityError):
        return _error_response(
            request,
            422,
            "unsupported_capability",
            str(exc),
            {"provider_key": exc.provider_key, "capability": str(exc.capability)},
            env=env,
        )

    if isinstance(exc, InvalidCredentialFormatError):
        return _error_response(request, 500, "internal_credential_error", str(exc), env=env)

    if isinstance(exc, TransportError):
        return _error_response(request, 502, "provider_unavailable", str(exc), env=env)

    if isinstance(exc, AuthError):
        return _error_response(request, 401, "auth_error", str(exc), env=env)

    # Catch-all for unexpected exceptions — include details in LOCAL/DEV
    return _error_response(
        request, 500, "internal_error", "An unexpected error occurred", exc=exc, env=env
    )


def make_unhandled_exception_handler(env: str):
    """Factory for creating an unhandled exception handler with environment awareness.

    In LOCAL/DEV environments, includes exception details (type, message, traceback) for debugging.
    In PROD, returns a generic error message.
    """

    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="An unexpected error occurred",
            exc=exc,
            env=env,
        )

    return unhandled_exception_handler


def check_connection_status(status: str, request: Request) -> JSONResponse | None:
    """Check connection status and return an error response if not active.

    Returns None if the connection is active (no error).
    """
    if status == ConnectionStatus.NEEDS_REAUTH:
        return _error_response(
            request,
            403,
            "connection_needs_reauth",
            "This connection's credentials have expired. Initiate a reauthorization flow.",
        )
    if status == ConnectionStatus.REVOKED:
        return _error_response(
            request,
            410,
            "connection_revoked",
            "This connection has been revoked.",
        )
    if status == ConnectionStatus.PENDING:
        return _error_response(
            request,
            409,
            "connection_pending",
            "This connection's OAuth flow has not been completed yet.",
        )
    return None
