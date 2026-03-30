"""Coverage tests for hosted config and app bootstrap."""

from __future__ import annotations

import json
from unittest.mock import patch

import omnidapter_hosted.config as hosted_config
import pytest
from httpx import ASGITransport, AsyncClient
from omnidapter_hosted.dependencies import get_hosted_auth_context
from omnidapter_hosted.main import (
    app,
    health,
    run,
    unhandled_exception_handler,
)
from omnidapter_server.config import Settings as ServerSettings
from omnidapter_server.config import get_settings as server_get_settings
from omnidapter_server.dependencies import get_auth_context as server_get_auth_context
from starlette.requests import Request


def test_get_hosted_settings_is_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOSTED_RATE_LIMIT_FREE", "123")
    hosted_config._settings = None

    first = hosted_config.get_hosted_settings()
    second = hosted_config.get_hosted_settings()

    assert first is second
    assert first.hosted_rate_limit_free == 123

    hosted_config._settings = None


def test_hosted_settings_extends_server_settings() -> None:
    assert issubclass(hosted_config.HostedSettings, ServerSettings)


def test_server_auth_dependency_is_overridden() -> None:
    assert app.dependency_overrides[server_get_auth_context] is get_hosted_auth_context


def test_server_settings_dependency_is_overridden() -> None:
    assert app.dependency_overrides[server_get_settings] is hosted_config.get_hosted_settings


def test_openapi_exposes_bearer_auth_scheme() -> None:
    schema = app.openapi()

    security_schemes = schema["components"]["securitySchemes"]
    assert "HostedAPIKeyAuth" in security_schemes
    assert "DashboardJWTAuth" in security_schemes
    assert "LinkTokenAuth" in security_schemes

    bearer = security_schemes["HostedAPIKeyAuth"]
    assert bearer["type"] == "http"
    assert bearer["scheme"] == "bearer"


def test_openapi_protected_hosted_endpoint_uses_bearer_auth() -> None:
    schema = app.openapi()

    connections_get = schema["paths"]["/v1/connections"]["get"]
    assert {"HostedAPIKeyAuth": []} in connections_get["security"]


@pytest.mark.asyncio
async def test_hosted_health_endpoint() -> None:
    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "omnidapter-hosted"}


@pytest.mark.asyncio
async def test_unhandled_exception_handler_formats_error() -> None:
    request = Request({"type": "http", "method": "GET", "path": "/", "headers": []})
    request.state.request_id = "req_123"

    response = await unhandled_exception_handler(request, RuntimeError("boom"))
    body = json.loads(bytes(response.body))

    assert response.status_code == 500
    assert body["error"]["code"] == "internal_error"
    assert body["meta"]["request_id"] == "req_123"


@pytest.mark.asyncio
async def test_health_function() -> None:
    assert await health() == {"status": "ok", "service": "omnidapter-hosted"}


def test_run_invokes_uvicorn() -> None:
    with patch("uvicorn.run") as run_mock:
        run()

    run_mock.assert_called_once_with(
        "omnidapter_hosted.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )
