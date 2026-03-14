"""API-level error handling and library exception mapping."""

from __future__ import annotations

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

from omnidapter_api.models.connection import ConnectionStatus


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    body = {
        "error": {"code": code, "message": message},
        "meta": {"request_id": request_id},
    }
    if details:
        body["error"]["details"] = details  # type: ignore[index]
    return JSONResponse(status_code=status_code, content=body)


def map_library_exception(
    exc: Exception,
    request: Request,
) -> JSONResponse:
    """Map Omnidapter library exceptions to HTTP responses."""
    if isinstance(exc, RateLimitError):
        details = {"provider_key": exc.provider_key}
        if exc.status_code:
            details["status_code"] = str(exc.status_code)
        if exc.provider_request_id:
            details["provider_request_id"] = exc.provider_request_id
        return _error_response(request, 429, "provider_rate_limited", str(exc), details)

    if isinstance(exc, ProviderAPIError):
        details = {"provider_key": exc.provider_key}
        if exc.status_code:
            details["status_code"] = str(exc.status_code)
        if exc.provider_request_id:
            details["provider_request_id"] = exc.provider_request_id
        return _error_response(request, 502, "provider_error", str(exc), details)

    if isinstance(exc, ConnectionNotFoundError):
        return _error_response(request, 404, "connection_not_found", str(exc))

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
        )

    if isinstance(exc, UnsupportedCapabilityError):
        return _error_response(
            request,
            422,
            "unsupported_capability",
            str(exc),
            {"provider_key": exc.provider_key, "capability": str(exc.capability)},
        )

    if isinstance(exc, InvalidCredentialFormatError):
        return _error_response(request, 500, "internal_credential_error", str(exc))

    if isinstance(exc, TransportError):
        return _error_response(request, 502, "provider_unavailable", str(exc))

    if isinstance(exc, AuthError):
        return _error_response(request, 401, "auth_error", str(exc))

    return _error_response(request, 500, "internal_error", "An unexpected error occurred")


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
