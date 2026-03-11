"""
Unit tests for the error hierarchy.
"""

from datetime import datetime, timezone

from omnidapter.core.errors import (
    AuthError,
    ConnectionNotFoundError,
    OAuthStateError,
    OmnidapterError,
    ProviderAPIError,
    ProviderNotConfiguredError,
    RateLimitError,
    ScopeInsufficientError,
    TokenRefreshError,
    TransportError,
    UnsupportedCapabilityError,
)
from omnidapter.services.calendar.capabilities import CalendarCapability


class TestErrorHierarchy:
    def test_omnidapter_error_is_base(self):
        assert issubclass(AuthError, OmnidapterError)
        assert issubclass(TransportError, OmnidapterError)
        assert issubclass(ProviderAPIError, OmnidapterError)
        assert issubclass(ConnectionNotFoundError, OmnidapterError)
        assert issubclass(UnsupportedCapabilityError, OmnidapterError)

    def test_auth_error_hierarchy(self):
        assert issubclass(OAuthStateError, AuthError)
        assert issubclass(TokenRefreshError, AuthError)
        assert issubclass(ProviderNotConfiguredError, AuthError)
        assert issubclass(ScopeInsufficientError, AuthError)

    def test_rate_limit_error_hierarchy(self):
        assert issubclass(RateLimitError, ProviderAPIError)

    def test_connection_not_found_error(self):
        err = ConnectionNotFoundError("conn_test_123")
        assert "conn_test_123" in str(err)
        assert err.connection_id == "conn_test_123"

    def test_provider_api_error_fields(self):
        err = ProviderAPIError(
            "Test error",
            provider_key="google",
            status_code=500,
            response_body="Internal Server Error",
            provider_request_id="req-abc",
            correlation_id="corr-xyz",
        )
        assert err.provider_key == "google"
        assert err.status_code == 500
        assert err.response_body == "Internal Server Error"
        assert err.provider_request_id == "req-abc"
        assert err.correlation_id == "corr-xyz"

    def test_provider_api_error_truncates_body(self):
        long_body = "x" * 10000
        err = ProviderAPIError(
            "Test",
            provider_key="google",
            correlation_id="corr",
            response_body=long_body,
        )
        assert len(err.response_body) <= 4096 + 20  # truncation marker

    def test_rate_limit_error_fields(self):
        reset = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
        err = RateLimitError(
            "Rate limited",
            provider_key="google",
            correlation_id="corr",
            retry_after=30.0,
            rate_limit_remaining=0,
            rate_limit_reset=reset,
        )
        assert err.retry_after == 30.0
        assert err.rate_limit_remaining == 0
        assert err.rate_limit_reset == reset
        assert err.provider_key == "google"

    def test_token_refresh_error(self):
        cause = ValueError("network failure")
        err = TokenRefreshError("Refresh failed", provider_key="google", cause=cause)
        assert err.provider_key == "google"
        assert err.cause is cause

    def test_provider_not_configured_error(self):
        err = ProviderNotConfiguredError(
            "Provider not configured",
            provider_key="google",
            missing_fields=["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"],
        )
        assert err.provider_key == "google"
        assert err.missing_fields == ["GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"]

    def test_unsupported_capability_error(self):
        err = UnsupportedCapabilityError(
            "Not supported",
            provider_key="caldav",
            capability=CalendarCapability.GET_AVAILABILITY,
        )
        assert err.provider_key == "caldav"
        assert err.capability == CalendarCapability.GET_AVAILABILITY

    def test_scope_insufficient_error(self):
        err = ScopeInsufficientError(
            "Missing scopes",
            required_scopes=["calendar.write"],
            granted_scopes=["calendar.read"],
        )
        assert err.required_scopes == ["calendar.write"]
        assert err.granted_scopes == ["calendar.read"]

    def test_provider_api_error_str(self):
        err = ProviderAPIError(
            "Error message",
            provider_key="google",
            status_code=503,
            correlation_id="test-corr-id",
        )
        err_str = str(err)
        assert "google" in err_str
        assert "503" in err_str
        assert "test-corr-id" in err_str
