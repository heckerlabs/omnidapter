"""Unit tests for the server connect router."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter_server.dependencies import LinkTokenContext
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.routers.connect import (
    ConnectCreateConnectionRequest,
    create_connection,
    list_providers,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _link_token(
    *,
    allowed_providers: list[str] | None = None,
    locked_provider_key: str | None = None,
    end_user_id: str | None = "user_1",
    redirect_uri: str | None = "https://app.example.com/done",
    connection_id: uuid.UUID | None = None,
) -> LinkTokenContext:
    return LinkTokenContext(
        end_user_id=end_user_id,
        allowed_providers=allowed_providers,
        redirect_uri=redirect_uri,
        connection_id=connection_id,
        locked_provider_key=locked_provider_key,
    )


# ---------------------------------------------------------------------------
# GET /connect/providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_providers_returns_available() -> None:
    session = AsyncMock()
    settings = MagicMock()

    with patch(
        "omnidapter_server.routers.connect.list_available_providers",
        new=AsyncMock(
            return_value=[
                {
                    "key": "google",
                    "name": "Google",
                    "auth_kind": "oauth2",
                    "credential_schema": None,
                }
            ]
        ),
    ):
        resp = await list_providers(
            link_token=_link_token(),
            settings=settings,
            request_id="req_1",
            session=session,
        )

    assert len(resp["providers"]) == 1
    assert resp["providers"][0]["key"] == "google"


@pytest.mark.asyncio
async def test_list_providers_passes_allowed_providers() -> None:
    session = AsyncMock()
    settings = MagicMock()

    call_kwargs: list[dict] = []

    async def _mock_list(**kwargs):  # type: ignore[override]
        call_kwargs.append(kwargs)
        return []

    with patch(
        "omnidapter_server.routers.connect.list_available_providers",
        new=_mock_list,
    ):
        await list_providers(
            link_token=_link_token(allowed_providers=["caldav"]),
            settings=settings,
            request_id="req_1",
            session=session,
        )

    assert call_kwargs[0]["allowed_providers"] == ["caldav"]


# ---------------------------------------------------------------------------
# POST /connect/connections
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_connection_oauth_returns_authorization_url() -> None:
    from dataclasses import dataclass

    @dataclass
    class _FlowResult:
        connection_id: str = str(uuid.uuid4())
        status: str = "pending"
        authorization_url: str = "https://accounts.google.com/o/oauth2/auth?..."

    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    encryption = MagicMock()
    settings = MagicMock(omnidapter_allowed_origin_domains="*", omnidapter_env="LOCAL")
    request = MagicMock()

    with (
        patch(
            "omnidapter_server.routers.connect._metadata_omni",
            return_value=MagicMock(
                describe_provider=MagicMock(
                    return_value=MagicMock(
                        auth_kinds=[MagicMock(value="oauth2")],
                    )
                )
            ),
        ),
        patch(
            "omnidapter_server.routers.connect.is_provider_available",
            return_value=True,
        ),
        patch(
            "omnidapter_server.routers.connect.create_connection_flow",
            new=AsyncMock(return_value=_FlowResult()),
        ),
    ):
        resp = await create_connection(
            body=ConnectCreateConnectionRequest(
                provider_key="google",
                redirect_uri="https://app.example.com/callback",
            ),
            request=request,
            link_token=_link_token(redirect_uri="https://app.example.com/callback"),
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert resp["data"].authorization_url is not None
    assert resp["data"].status == "pending"


@pytest.mark.asyncio
async def test_create_connection_unknown_provider_raises_422() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    encryption = MagicMock()
    settings = MagicMock()
    request = MagicMock()

    with (
        patch(
            "omnidapter_server.routers.connect._metadata_omni",
            return_value=MagicMock(describe_provider=MagicMock(side_effect=KeyError("unknown"))),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_connection(
            body=ConnectCreateConnectionRequest(provider_key="unknown_provider"),
            request=request,
            link_token=_link_token(),
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert exc_info.value.status_code == 422
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "provider_not_found"


@pytest.mark.asyncio
async def test_create_connection_provider_not_in_allowed_list_raises_422() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    encryption = MagicMock()
    settings = MagicMock()
    request = MagicMock()

    with (
        patch(
            "omnidapter_server.routers.connect._metadata_omni",
            return_value=MagicMock(
                describe_provider=MagicMock(
                    return_value=MagicMock(
                        auth_kinds=[MagicMock(value="oauth2")],
                    )
                )
            ),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_connection(
            body=ConnectCreateConnectionRequest(provider_key="microsoft"),
            request=request,
            link_token=_link_token(allowed_providers=["google"]),
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert exc_info.value.status_code == 422
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "provider_not_allowed"


@pytest.mark.asyncio
async def test_create_connection_credential_returns_active() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    encryption = MagicMock()
    settings = MagicMock()
    request = MagicMock()

    conn = Connection(
        id=uuid.uuid4(),
        provider_key="caldav",
        status=ConnectionStatus.ACTIVE,
        external_id="user_1",
        refresh_failure_count=0,
        created_at=_now(),
        updated_at=_now(),
    )

    with (
        patch(
            "omnidapter_server.routers.connect._metadata_omni",
            return_value=MagicMock(
                describe_provider=MagicMock(
                    return_value=MagicMock(
                        auth_kinds=[MagicMock(value="basic")],
                    )
                )
            ),
        ),
        patch(
            "omnidapter_server.routers.connect.is_provider_available",
            return_value=True,
        ),
        patch(
            "omnidapter_server.routers.connect.create_credential_connection",
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
            link_token=_link_token(),
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert resp["data"].status == ConnectionStatus.ACTIVE
    assert resp["data"].authorization_url is None


@pytest.mark.asyncio
async def test_create_connection_reconnect_oauth() -> None:
    from dataclasses import dataclass

    @dataclass
    class _FlowResult:
        connection_id: str = str(uuid.uuid4())
        status: str = "pending"
        authorization_url: str = "https://accounts.google.com/o/oauth2/auth?..."

    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    encryption = MagicMock()
    settings = MagicMock(omnidapter_allowed_origin_domains="*", omnidapter_env="LOCAL")
    request = MagicMock()

    with (
        patch(
            "omnidapter_server.routers.connect._metadata_omni",
            return_value=MagicMock(
                describe_provider=MagicMock(
                    return_value=MagicMock(
                        auth_kinds=[MagicMock(value="oauth2")],
                    )
                )
            ),
        ),
        patch(
            "omnidapter_server.routers.connect.is_provider_available",
            return_value=True,
        ),
        patch(
            "omnidapter_server.routers.connect.reauthorize_connection_flow",
            new=AsyncMock(return_value=_FlowResult()),
        ),
    ):
        resp = await create_connection(
            body=ConnectCreateConnectionRequest(
                provider_key="google",
                redirect_uri="https://app.example.com/callback",
            ),
            request=request,
            link_token=_link_token(
                connection_id=conn_id,
                locked_provider_key="google",
                redirect_uri="https://app.example.com/callback",
            ),
            encryption=encryption,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert resp["data"].authorization_url is not None


# ---------------------------------------------------------------------------
# POST /connect/session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_session_success() -> None:
    """Valid bootstrap token returns a cs_ session token."""
    from omnidapter_server.models.link_token import LinkToken
    from omnidapter_server.routers.connect import ConnectSessionRequest, create_session

    fake_lt = MagicMock(spec=LinkToken)
    session = AsyncMock()

    with patch(
        "omnidapter_server.routers.connect.create_connect_session",
        new=AsyncMock(return_value=("cs_fakesessiontoken12345678901234", fake_lt)),
    ):
        resp = await create_session(
            body=ConnectSessionRequest(token="lt_validtoken12345678901234567890"),
            request_id="req_sess_1",
            session=session,
        )

    assert resp["data"].session_token.startswith("cs_")
    assert resp["data"].expires_in == 900


@pytest.mark.asyncio
async def test_create_session_invalid_token_returns_401() -> None:
    """Invalid/expired bootstrap token raises 401 with session_expired."""
    from omnidapter_server.routers.connect import ConnectSessionRequest, create_session

    session = AsyncMock()

    with (
        patch(
            "omnidapter_server.routers.connect.create_connect_session",
            new=AsyncMock(side_effect=ValueError("invalid_token")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_session(
            body=ConnectSessionRequest(token="lt_badtoken1234567890123456789"),
            request_id="req_sess_2",
            session=session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "session_expired"  # type: ignore[index]


@pytest.mark.asyncio
async def test_create_session_already_used_token_returns_token_already_used() -> None:
    """Consumed bootstrap token raises 401 with token_already_used."""
    from omnidapter_server.routers.connect import ConnectSessionRequest, create_session

    session = AsyncMock()

    with (
        patch(
            "omnidapter_server.routers.connect.create_connect_session",
            new=AsyncMock(side_effect=ValueError("token_already_used")),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_session(
            body=ConnectSessionRequest(token="lt_usedtoken123456789012345678"),
            request_id="req_sess_3",
            session=session,
        )

    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["code"] == "token_already_used"  # type: ignore[index]
