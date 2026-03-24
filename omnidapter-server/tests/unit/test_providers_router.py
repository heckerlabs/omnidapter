"""Unit tests for provider metadata router handlers."""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter.core.metadata import AuthKind, ConnectionConfigField, ProviderMetadata, ServiceKind
from omnidapter_server.config import Settings
from omnidapter_server.dependencies import AuthContext
from omnidapter_server.routers.providers import get_provider, list_providers
from starlette.requests import Request


class _FakeOmni:
    def __init__(self, metadata_by_key: dict[str, ProviderMetadata]) -> None:
        self._metadata_by_key = metadata_by_key

    def list_providers(self) -> list[str]:
        return list(self._metadata_by_key.keys())

    def describe_provider(self, provider_key: str) -> ProviderMetadata:
        if provider_key not in self._metadata_by_key:
            raise KeyError(provider_key)
        return self._metadata_by_key[provider_key]


def _meta(provider_key: str = "google") -> ProviderMetadata:
    return ProviderMetadata(
        provider_key=provider_key,
        display_name="Google",
        services=[ServiceKind.CALENDAR],
        auth_kinds=[AuthKind.OAUTH2],
        capabilities={"calendar": ["list_events"]},
        connection_config_fields=[
            ConnectionConfigField(name="timezone", description="Timezone", required=False)
        ],
    )


def _auth() -> AuthContext:
    return AuthContext(api_key=MagicMock())


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


@pytest.mark.asyncio
async def test_list_providers() -> None:
    fake_omni = _FakeOmni({"google": _meta("google")})
    with patch("omnidapter_server.routers.providers._build_omni", return_value=fake_omni):
        response = await list_providers(
            request=_request(),
            auth=_auth(),
            settings=Settings(),
            request_id="req_1",
        )

    assert response["meta"]["request_id"] == "req_1"
    assert response["data"][0]["provider_key"] == "google"


@pytest.mark.asyncio
async def test_get_provider_not_found() -> None:
    fake_omni = _FakeOmni({})
    with (
        patch("omnidapter_server.routers.providers._build_omni", return_value=fake_omni),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_provider(
            provider_key="unknown",
            request=_request(),
            auth=_auth(),
            settings=Settings(),
            request_id="req_2",
        )

    assert exc_info.value.status_code == 404
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "provider_not_found"


@pytest.mark.asyncio
async def test_get_provider_success() -> None:
    fake_omni = _FakeOmni({"google": _meta("google")})
    with patch("omnidapter_server.routers.providers._build_omni", return_value=fake_omni):
        response = await get_provider(
            provider_key="google",
            request=_request(),
            auth=_auth(),
            settings=Settings(),
            request_id="req_3",
        )

    assert response["meta"]["request_id"] == "req_3"
    assert response["data"]["provider_key"] == "google"
