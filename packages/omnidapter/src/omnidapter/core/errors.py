from __future__ import annotations

from datetime import datetime


class OmnidapterError(Exception):
    pass


class AuthError(OmnidapterError):
    pass


class OAuthStateError(AuthError):
    pass


class TokenRefreshError(AuthError):
    pass


class UnsupportedCapabilityError(OmnidapterError):
    pass


class ConnectionNotFoundError(OmnidapterError):
    def __init__(self, connection_id: str):
        super().__init__(f"Connection not found: {connection_id}")
        self.connection_id = connection_id


class InvalidCredentialFormatError(AuthError):
    pass


class ScopeInsufficientError(AuthError):
    def __init__(self, required_scopes: list[str], granted_scopes: list[str] | None):
        super().__init__("Insufficient scopes for operation")
        self.required_scopes = required_scopes
        self.granted_scopes = granted_scopes or []


class TransportError(OmnidapterError):
    pass


class ProviderAPIError(OmnidapterError):
    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        correlation_id: str,
        status_code: int | None = None,
        response_body: str | None = None,
        provider_request_id: str | None = None,
    ):
        super().__init__(message)
        self.provider_key = provider_key
        self.status_code = status_code
        self.response_body = response_body
        self.provider_request_id = provider_request_id
        self.correlation_id = correlation_id


class RateLimitError(ProviderAPIError):
    def __init__(
        self,
        message: str,
        *,
        provider_key: str,
        correlation_id: str,
        retry_after: float | None = None,
        rate_limit_remaining: int | None = None,
        rate_limit_reset: datetime | None = None,
        status_code: int | None = 429,
        response_body: str | None = None,
        provider_request_id: str | None = None,
    ):
        super().__init__(
            message,
            provider_key=provider_key,
            correlation_id=correlation_id,
            status_code=status_code,
            response_body=response_body,
            provider_request_id=provider_request_id,
        )
        self.retry_after = retry_after
        self.rate_limit_remaining = rate_limit_remaining
        self.rate_limit_reset = rate_limit_reset
