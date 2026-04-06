"""OpenAPI auth schema tests."""

from __future__ import annotations

from omnidapter_server.main import app


def test_openapi_exposes_bearer_auth_scheme() -> None:
    schema = app.openapi()

    security_schemes = schema["components"]["securitySchemes"]
    assert "APIKeyAuth" in security_schemes
    assert "LinkTokenAuth" in security_schemes

    bearer = security_schemes["APIKeyAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"


def test_protected_provider_endpoint_uses_bearer_auth() -> None:
    schema = app.openapi()

    providers_get = schema["paths"]["/v1/providers"]["get"]
    assert {"APIKeyAuth": []} in providers_get["security"]
