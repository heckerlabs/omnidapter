"""
Omnidapter exception hierarchy.

All public exceptions are importable from `omnidapter.core.errors`.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any


class OmnidapterError(Exception):
    """Base exception for all Omnidapter errors."""


class AuthError(OmnidapterError):
    """General authentication failure."""


class OAuthStateError(AuthError):
    """OAuth state validation failure (missing, expired, or tampered state)."""


class TokenRefreshError(AuthError):
    """Token refresh attempt failed."""

    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        cause: Exception | None = None,
    ) -> None:
        super().__init__(message)
        self.provider_key = provider_key
        self.cause = cause


class UnsupportedCapabilityError(OmnidapterError):
    """The requested capability is not supported by this provider."""

    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        capability: Any,
    ) -> None:
        super().__init__(message)
        self.provider_key = provider_key
        self.capability = capability


class ConnectionNotFoundError(OmnidapterError):
    """No credentials found for the given connection_id."""

    def __init__(self, connection_id: str) -> None:
        super().__init__(f"No credentials found for connection_id={connection_id!r}")
        self.connection_id = connection_id


class InvalidCredentialFormatError(OmnidapterError):
    """Stored credentials do not match the expected format."""

    def __init__(self, message: str, *, provider_key: str) -> None:
        super().__init__(message)
        self.provider_key = provider_key


class ScopeInsufficientError(AuthError):
    """The connection lacks required scopes for the requested operation."""

    def __init__(
        self,
        message: str,
        *,
        required_scopes: list[str],
        granted_scopes: list[str] | None,
    ) -> None:
        super().__init__(message)
        self.required_scopes = required_scopes
        self.granted_scopes = granted_scopes


class TransportError(OmnidapterError):
    """Network-level transport failure."""

    def __init__(self, message: str, *, cause: Exception | None = None) -> None:
        super().__init__(message)
        self.cause = cause


class ProviderAPIError(OmnidapterError):
    """Provider returned an error response.

    Carries full provider response context for debugging.
    """

    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        status_code: int | None = None,
        response_body: str | None = None,
        provider_request_id: str | None = None,
        correlation_id: str,
    ) -> None:
        super().__init__(message)
        self.provider_key = provider_key
        self.status_code = status_code
        # Truncate very large response bodies
        if response_body and len(response_body) > 4096:
            response_body = response_body[:4096] + "... [truncated]"
        self.response_body = response_body
        self.provider_request_id = provider_request_id
        self.correlation_id = correlation_id

    def __str__(self) -> str:
        parts = [super().__str__()]
        parts.append(f"provider={self.provider_key!r}")
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        if self.provider_request_id:
            parts.append(f"provider_request_id={self.provider_request_id!r}")
        parts.append(f"correlation_id={self.correlation_id!r}")
        return " | ".join(parts)


class RateLimitError(ProviderAPIError):
    """Provider rate-limited the request.

    Extends ProviderAPIError with rate-limit-specific context.
    """

    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        status_code: int | None = 429,
        response_body: str | None = None,
        provider_request_id: str | None = None,
        correlation_id: str,
        retry_after: float | None = None,
        rate_limit_remaining: int | None = None,
        rate_limit_reset: datetime | None = None,
    ) -> None:
        super().__init__(
            message,
            provider_key=provider_key,
            status_code=status_code,
            response_body=response_body,
            provider_request_id=provider_request_id,
            correlation_id=correlation_id,
        )
        self.retry_after = retry_after
        self.rate_limit_remaining = rate_limit_remaining
        self.rate_limit_reset = rate_limit_reset
