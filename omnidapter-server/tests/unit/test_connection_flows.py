"""Unit tests for shared connection flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter_server.config import Settings
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.schemas.connection import (
    CreateConnectionRequest,
    ReauthorizeConnectionRequest,
)
from omnidapter_server.services.connection_flows import (
    create_connection_flow,
    get_connection_or_404,
    list_connections_flow,
    reauthorize_connection_flow,
    validate_redirect_url_or_422,
)
from starlette.requests import Request


def _request() -> Request:
    return Request({"type": "http", "method": "POST", "path": "/", "headers": []})


def _conn(status: str = ConnectionStatus.ACTIVE) -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=status,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_get_connection_or_404_invalid_uuid() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_connection_or_404(
            connection_id="invalid",
            session=AsyncMock(),
            load_connection_by_uuid=AsyncMock(),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_connection_or_404_not_found() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_connection_or_404(
            connection_id=str(uuid.uuid4()),
            session=AsyncMock(),
            load_connection_by_uuid=AsyncMock(return_value=None),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_create_connection_flow_success_calls_persist_hook() -> None:
    body = CreateConnectionRequest(provider="google", redirect_url="https://app/cb")
    session = AsyncMock()
    session.add = MagicMock()
    provider_cfg = SimpleNamespace(is_fallback=False, scopes=["calendar.read"])
    oauth_begin = AsyncMock(
        return_value=SimpleNamespace(state="state_1", authorization_url="https://auth")
    )
    omni = SimpleNamespace(oauth=SimpleNamespace(begin=oauth_begin))
    persist = AsyncMock()

    with patch(
        "omnidapter_server.services.connection_flows.validate_redirect_url", return_value=None
    ):
        result = await create_connection_flow(
            body=body,
            request=_request(),
            session=session,
            settings=Settings(),
            load_provider_config=AsyncMock(return_value=provider_cfg),
            count_active_connections=AsyncMock(return_value=0),
            build_omni=AsyncMock(return_value=omni),
            persist_post_create=persist,
        )

    assert result.authorization_url == "https://auth"
    persist.assert_awaited_once()
    session.commit.assert_awaited()


@pytest.mark.asyncio
async def test_create_connection_flow_oauth_begin_failure_rolls_back() -> None:
    body = CreateConnectionRequest(provider="google", redirect_url="https://app/cb")
    session = AsyncMock()
    session.add = MagicMock()
    oauth_begin = AsyncMock(side_effect=RuntimeError("bad oauth"))
    omni = SimpleNamespace(oauth=SimpleNamespace(begin=oauth_begin))

    with (
        patch(
            "omnidapter_server.services.connection_flows.validate_redirect_url", return_value=None
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_connection_flow(
            body=body,
            request=_request(),
            session=session,
            settings=Settings(),
            load_provider_config=AsyncMock(
                return_value=SimpleNamespace(is_fallback=False, scopes=None)
            ),
            count_active_connections=AsyncMock(return_value=0),
            build_omni=AsyncMock(return_value=omni),
        )

    assert exc_info.value.status_code == 422
    session.delete.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_connections_flow_passthrough() -> None:
    loader = AsyncMock(return_value=(2, [_conn(), _conn()]))
    total, rows = await list_connections_flow(
        session=AsyncMock(),
        status=None,
        provider=None,
        limit=50,
        offset=0,
        load_paginated_connections=loader,
    )
    assert total == 2
    assert len(rows) == 2


@pytest.mark.asyncio
async def test_reauthorize_connection_flow_rejects_revoked() -> None:
    with (
        patch(
            "omnidapter_server.services.connection_flows.validate_redirect_url", return_value=None
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await reauthorize_connection_flow(
            connection_id=str(uuid.uuid4()),
            body=ReauthorizeConnectionRequest(redirect_url="https://app/cb"),
            request=_request(),
            session=AsyncMock(),
            settings=Settings(),
            load_connection=AsyncMock(return_value=_conn(ConnectionStatus.REVOKED)),
            load_provider_config=AsyncMock(return_value=None),
            build_omni=AsyncMock(),
        )
    assert exc_info.value.status_code == 410


@pytest.mark.asyncio
async def test_reauthorize_connection_flow_unions_scopes() -> None:
    conn = _conn(ConnectionStatus.ACTIVE)
    conn.granted_scopes = ["a", "b"]
    conn.provider_config = {"x": "y"}
    oauth_begin = AsyncMock(
        return_value=SimpleNamespace(state="state2", authorization_url="https://auth2")
    )
    omni = SimpleNamespace(oauth=SimpleNamespace(begin=oauth_begin))
    session = AsyncMock()

    with patch(
        "omnidapter_server.services.connection_flows.validate_redirect_url", return_value=None
    ):
        result = await reauthorize_connection_flow(
            connection_id=str(conn.id),
            body=ReauthorizeConnectionRequest(redirect_url="https://app/cb"),
            request=_request(),
            session=session,
            settings=Settings(),
            load_connection=AsyncMock(return_value=conn),
            load_provider_config=AsyncMock(return_value=SimpleNamespace(scopes=["b", "c"])),
            build_omni=AsyncMock(return_value=omni),
        )

    assert result.authorization_url == "https://auth2"
    assert oauth_begin.await_args is not None
    scopes = set(oauth_begin.await_args.kwargs["scopes"])
    assert scopes == {"a", "b", "c"}
    session.execute.assert_awaited_once()


def test_validate_redirect_url_or_422_maps_value_error() -> None:
    with (
        patch(
            "omnidapter_server.services.connection_flows.parse_allowed_origin_domains",
            return_value=[],
        ),
        patch(
            "omnidapter_server.services.connection_flows.validate_redirect_url",
            side_effect=ValueError("bad redirect"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        validate_redirect_url_or_422(
            redirect_url="https://bad",
            request=_request(),
            settings=Settings(),
        )
    assert exc_info.value.status_code == 422
