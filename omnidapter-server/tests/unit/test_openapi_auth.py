"""OpenAPI auth schema tests."""

from __future__ import annotations

from omnidapter_server.main import app


def test_openapi_exposes_bearer_auth_scheme() -> None:
    schema = app.openapi()

    security_schemes = schema["components"]["securitySchemes"]
    bearer = security_schemes["BearerAuth"]

    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"


def test_protected_provider_endpoint_uses_bearer_auth() -> None:
    schema = app.openapi()

    providers_get = schema["paths"]["/v1/providers"]["get"]
    assert {"BearerAuth": []} in providers_get["security"]
