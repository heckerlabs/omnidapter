"""Unit tests for library exception → HTTP response mapping."""

from __future__ import annotations

from unittest.mock import MagicMock

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
from omnidapter_server.errors import map_library_exception


def _make_request(request_id: str = "req_test") -> MagicMock:
    req = MagicMock()
    req.state.request_id = request_id
    return req


def test_connection_not_found_maps_to_404():
    exc = ConnectionNotFoundError("conn_abc")
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 404
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "connection_not_found"
    assert body["meta"]["request_id"] == "req_test"


def test_auth_error_maps_to_401():
    exc = AuthError("auth failed")
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 401
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "auth_error"


def test_scope_insufficient_maps_to_403():
    exc = ScopeInsufficientError(
        "Missing scopes",
        required_scopes=["calendar.read"],
        granted_scopes=["profile"],
    )
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 403
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "scope_insufficient"
    assert body["error"]["details"]["required_scopes"] == ["calendar.read"]


def test_unsupported_capability_maps_to_422():
    exc = UnsupportedCapabilityError(
        "Not supported",
        provider_key="google",
        capability="some_cap",
    )
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 422
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "unsupported_capability"


def test_provider_api_error_maps_to_502():
    exc = ProviderAPIError(
        "Provider error",
        provider_key="google",
        status_code=500,
        provider_request_id="goog-123",
        correlation_id="corr-abc",
    )
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 502
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "provider_error"
    assert body["error"]["details"]["provider_key"] == "google"
    assert body["error"]["details"]["provider_request_id"] == "goog-123"


def test_rate_limit_error_maps_to_429():
    exc = RateLimitError(
        "Rate limited",
        provider_key="google",
        status_code=429,
        correlation_id="corr-abc",
    )
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 429
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "provider_rate_limited"


def test_transport_error_maps_to_502():
    exc = TransportError("Connection timeout")
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 502
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "provider_unavailable"


def test_invalid_credential_format_maps_to_500():
    exc = InvalidCredentialFormatError("Bad format", provider_key="google")
    req = _make_request()
    response = map_library_exception(exc, req)
    assert response.status_code == 500
    import json

    body = json.loads(bytes(response.body))
    assert body["error"]["code"] == "internal_credential_error"


def test_all_errors_include_request_id():
    exceptions = [
        ConnectionNotFoundError("conn"),
        AuthError("auth"),
        ScopeInsufficientError("scope", required_scopes=[], granted_scopes=None),
        TransportError("transport"),
    ]
    for exc in exceptions:
        req = _make_request("req_custom_123")
        response = map_library_exception(exc, req)
        import json

        body = json.loads(bytes(response.body))
        assert body["meta"]["request_id"] == "req_custom_123"
