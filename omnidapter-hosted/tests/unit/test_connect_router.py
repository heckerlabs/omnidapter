"""Unit tests for the Connect UI router endpoints."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter.core.metadata import AuthKind, ConnectionConfigField, ProviderMetadata, ServiceKind
from omnidapter_hosted.dependencies import LinkTokenContext
from omnidapter_hosted.routers.connect import (
    ConnectCreateConnectionRequest,
    create_connection,
    list_providers,
)
from omnidapter_server.models.connection import Connection, ConnectionStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _link_token(
    *,
    tenant_id: uuid.UUID | None = None,
    allowed_providers: list[str] | None = None,
    redirect_uri: str | None = "https://app.example.com/done",
    connection_id: uuid.UUID | None = None,
    locked_provider_key: str | None = None,
) -> LinkTokenContext:
    return LinkTokenContext(
        tenant_id=tenant_id or uuid.uuid4(),
        end_user_id="user_1",
        allowed_providers=allowed_providers,
        redirect_uri=redirect_uri,
        connection_id=connection_id,
        locked_provider_key=locked_provider_key,
    )


def _settings() -> MagicMock:
    s = MagicMock()
    s.omnidapter_google_client_id = ""
    s.omnidapter_google_client_secret = ""
    s.omnidapter_microsoft_client_id = ""
    s.omnidapter_microsoft_client_secret = ""
    s.omnidapter_zoho_client_id = ""
    s.omnidapter_zoho_client_secret = ""
    s.omnidapter_allowed_origin_domains = "*"
    s.omnidapter_env = "DEV"
    s.omnidapter_base_url = "http://localhost:8000"
    s.omnidapter_fallback_connection_limit = 5
    return s


def _oauth_meta(key: str) -> ProviderMetadata:
    return ProviderMetadata(
        provider_key=key,
        display_name=key.title(),
        services=[ServiceKind.CALENDAR],
        auth_kinds=[AuthKind.OAUTH2],
    )


def _basic_meta(key: str) -> ProviderMetadata:
    return ProviderMetadata(
        provider_key=key,
        display_name=key.title(),
        services=[ServiceKind.CALENDAR],
        auth_kinds=[AuthKind.BASIC],
        connection_config_fields=[
            ConnectionConfigField(
                name="server_url",
                label="Server URL",
                description="",
                type="url",
                required=True,
            ),
            ConnectionConfigField(
                name="username",
                label="Username",
                description="",
                type="text",
                required=True,
            ),
            ConnectionConfigField(
                name="password",
                label="Password",
                description="",
                type="password",
                required=True,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# GET /connect/providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_providers_returns_available() -> None:
    session = AsyncMock()
    link_token = _link_token()
    settings = _settings()

    providers_data = [
        {"key": "google", "name": "Google", "auth_kind": "oauth2", "credential_schema": None}
    ]

    with (
        patch(
            "omnidapter_hosted.routers.connect.list_available_providers",
            new=AsyncMock(return_value=providers_data),
        ),
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=MagicMock()),
    ):
        resp = await list_providers(
            link_token=link_token,
            settings=settings,
            request_id="req_1",
            session=session,
        )

    assert resp["providers"] == providers_data


@pytest.mark.asyncio
async def test_list_providers_reconnect_single_provider() -> None:
    """Reconnect tokens show only the locked provider (already handled in service layer)."""
    session = AsyncMock()
    link_token = _link_token(locked_provider_key="caldav")
    settings = _settings()

    locked_provider = [
        {
            "key": "caldav",
            "name": "CalDAV",
            "auth_kind": "basic",
            "credential_schema": {"fields": []},
        }
    ]

    with (
        patch(
            "omnidapter_hosted.routers.connect.list_available_providers",
            new=AsyncMock(return_value=locked_provider),
        ),
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=MagicMock()),
    ):
        resp = await list_providers(
            link_token=link_token,
            settings=settings,
            request_id="req_2",
            session=session,
        )

    assert len(resp["providers"]) == 1
    assert resp["providers"][0]["key"] == "caldav"


# ---------------------------------------------------------------------------
# POST /connect/connections — OAuth flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_connection_oauth_returns_auth_url() -> None:
    link_token = _link_token()
    session = AsyncMock()
    encryption = MagicMock()
    settings = _settings()
    request = MagicMock()
    request.url = MagicMock()

    omni = MagicMock()
    omni.describe_provider.return_value = _oauth_meta("google")

    flow_result = MagicMock()
    flow_result.connection_id = str(uuid.uuid4())
    flow_result.status = "pending"
    flow_result.authorization_url = "https://accounts.google.com/o/oauth2/auth?..."

    with (
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=omni),
        patch(
            "omnidapter_hosted.routers.connect.get_tenant_provider_config",
            new=AsyncMock(return_value=None),
        ),
        patch("omnidapter_hosted.routers.connect.is_provider_available", return_value=True),
        patch(
            "omnidapter_hosted.routers.connect.create_connection_flow",
            new=AsyncMock(return_value=flow_result),
        ),
    ):
        resp = await create_connection(
            body=ConnectCreateConnectionRequest(
                provider_key="google",
                redirect_uri="https://app.example.com/done",
            ),
            request=request,
            link_token=link_token,
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert resp["data"].status == "pending"
    assert "accounts.google.com" in resp["data"].authorization_url


# ---------------------------------------------------------------------------
# POST /connect/connections — non-OAuth (credential) flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_connection_non_oauth_success() -> None:
    link_token = _link_token()
    session = AsyncMock()
    encryption = MagicMock()
    settings = _settings()
    request = MagicMock()

    conn_id = uuid.uuid4()
    mock_conn = Connection(
        id=conn_id,
        provider_key="caldav",
        status=ConnectionStatus.ACTIVE,
        external_id="user_1",
        refresh_failure_count=0,
        created_at=_now(),
        updated_at=_now(),
    )

    omni = MagicMock()
    omni.describe_provider.return_value = _basic_meta("caldav")

    with (
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=omni),
        patch(
            "omnidapter_hosted.routers.connect.get_tenant_provider_config",
            new=AsyncMock(return_value=None),
        ),
        patch("omnidapter_hosted.routers.connect.is_provider_available", return_value=True),
        patch(
            "omnidapter_hosted.routers.connect.create_credential_connection",
            new=AsyncMock(return_value=mock_conn),
        ),
    ):
        resp = await create_connection(
            body=ConnectCreateConnectionRequest(
                provider_key="caldav",
                credentials={
                    "server_url": "https://caldav.example.com/",
                    "username": "u",
                    "password": "p",
                },
            ),
            request=request,
            link_token=link_token,
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_2",
        )

    assert resp["data"].status == ConnectionStatus.ACTIVE
    assert resp["data"].authorization_url is None


@pytest.mark.asyncio
async def test_create_connection_non_oauth_missing_credentials() -> None:
    link_token = _link_token()
    session = AsyncMock()
    encryption = MagicMock()
    settings = _settings()
    request = MagicMock()

    omni = MagicMock()
    omni.describe_provider.return_value = _basic_meta("caldav")

    with (
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=omni),
        patch(
            "omnidapter_hosted.routers.connect.get_tenant_provider_config",
            new=AsyncMock(return_value=None),
        ),
        patch("omnidapter_hosted.routers.connect.is_provider_available", return_value=True),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_connection(
            body=ConnectCreateConnectionRequest(provider_key="caldav"),
            request=request,
            link_token=link_token,
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_3",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "credentials_required"  # type: ignore[index]


# ---------------------------------------------------------------------------
# POST /connect/connections — reconnect flow
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_connection_reconnect_wrong_provider() -> None:
    conn_id = uuid.uuid4()
    link_token = _link_token(connection_id=conn_id, locked_provider_key="google")
    session = AsyncMock()
    encryption = MagicMock()
    settings = _settings()
    request = MagicMock()

    omni = MagicMock()
    omni.describe_provider.return_value = _oauth_meta("microsoft")

    with (
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=omni),
        patch(
            "omnidapter_hosted.routers.connect.get_tenant_provider_config",
            new=AsyncMock(return_value=None),
        ),
        patch("omnidapter_hosted.routers.connect.is_provider_available", return_value=True),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_connection(
            body=ConnectCreateConnectionRequest(
                provider_key="microsoft",
                redirect_uri="https://app.example.com/done",
            ),
            request=request,
            link_token=link_token,
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_4",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "provider_mismatch"  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_connection_reconnect_non_oauth_success() -> None:
    conn_id = uuid.uuid4()
    link_token = _link_token(connection_id=conn_id, locked_provider_key="caldav")
    session = AsyncMock()
    encryption = MagicMock()
    settings = _settings()
    request = MagicMock()

    conn = Connection(
        id=conn_id,
        provider_key="caldav",
        status=ConnectionStatus.ACTIVE,
        external_id="user_1",
        refresh_failure_count=0,
        created_at=_now(),
        updated_at=_now(),
    )

    omni = MagicMock()
    omni.describe_provider.return_value = _basic_meta("caldav")

    with (
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=omni),
        patch(
            "omnidapter_hosted.routers.connect.get_tenant_provider_config",
            new=AsyncMock(return_value=None),
        ),
        patch("omnidapter_hosted.routers.connect.is_provider_available", return_value=True),
        patch(
            "omnidapter_hosted.routers.connect.update_credential_connection",
            new=AsyncMock(return_value=conn),
        ),
    ):
        resp = await create_connection(
            body=ConnectCreateConnectionRequest(
                provider_key="caldav",
                credentials={
                    "server_url": "https://caldav.example.com/",
                    "username": "u",
                    "password": "p",
                },
            ),
            request=request,
            link_token=link_token,
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_5",
        )

    assert resp["data"].status == ConnectionStatus.ACTIVE
    assert str(resp["data"].connection_id) == str(conn_id)


@pytest.mark.asyncio
async def test_create_connection_unknown_provider_raises_422() -> None:
    link_token = _link_token()
    session = AsyncMock()
    encryption = MagicMock()
    settings = _settings()
    request = MagicMock()

    omni = MagicMock()
    omni.describe_provider.side_effect = KeyError("unknown")

    with (
        patch(
            "omnidapter_hosted.routers.connect.build_provider_registry", return_value=MagicMock()
        ),
        patch("omnidapter_hosted.routers.connect.Omnidapter", return_value=omni),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_connection(
            body=ConnectCreateConnectionRequest(provider_key="unknown"),
            request=request,
            link_token=link_token,
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_6",
        )

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail["code"] == "provider_not_found"  # type: ignore[index]
