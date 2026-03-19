"""Unit tests for shared OAuth callback flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.responses import RedirectResponse
from omnidapter import OAuthStateError
from omnidapter_server.config import Settings
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.models.oauth_state import OAuthState
from omnidapter_server.services.oauth_flows import (
    OAuthCallbackParams,
    append_query_params,
    oauth_callback_flow,
    validate_redirect_url_or_400,
)
from starlette.requests import Request


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": []})


def _state(connection_id: uuid.UUID) -> OAuthState:
    return OAuthState(
        id=uuid.uuid4(),
        state_token="st_1",
        connection_id=connection_id,
        provider_key="google",
        expires_at=datetime.now(timezone.utc),
    )


def _connection() -> Connection:
    return Connection(
        id=uuid.uuid4(),
        provider_key="google",
        status=ConnectionStatus.PENDING,
        provider_config={"redirect_url": "https://app/cb"},
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def test_append_query_params_merges_query() -> None:
    out = append_query_params("https://app/cb?x=1", connection_id="abc")
    assert "x=1" in out
    assert "connection_id=abc" in out


def test_validate_redirect_url_or_400_maps_value_error() -> None:
    with (
        patch(
            "omnidapter_server.services.oauth_flows.parse_allowed_origin_domains", return_value=[]
        ),
        patch(
            "omnidapter_server.services.oauth_flows.validate_redirect_url",
            side_effect=ValueError("bad"),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        validate_redirect_url_or_400(
            redirect_url="https://bad",
            request=_request(),
            settings=Settings(),
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_flow_error_with_redirect_returns_redirect_response() -> None:
    conn = _connection()
    state = _state(conn.id)

    with patch("omnidapter_server.services.oauth_flows.validate_redirect_url", return_value=None):
        response = await oauth_callback_flow(
            params=OAuthCallbackParams(
                provider_key="google",
                code=None,
                state=state.state_token,
                error="access_denied",
                error_description="denied",
            ),
            request=_request(),
            session=AsyncMock(),
            settings=Settings(),
            load_oauth_state=AsyncMock(return_value=state),
            load_connection_for_state=AsyncMock(return_value=conn),
            build_omni=AsyncMock(),
        )

    assert isinstance(response, RedirectResponse)
    assert "error=access_denied" in response.headers["location"]


@pytest.mark.asyncio
async def test_oauth_callback_flow_missing_code_or_state() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await oauth_callback_flow(
            params=OAuthCallbackParams(
                provider_key="google",
                code=None,
                state=None,
                error=None,
                error_description=None,
            ),
            request=_request(),
            session=AsyncMock(),
            settings=Settings(),
            load_oauth_state=AsyncMock(),
            load_connection_for_state=AsyncMock(),
            build_omni=AsyncMock(),
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_flow_oauth_state_error() -> None:
    conn = _connection()
    state = _state(conn.id)
    omni = SimpleNamespace(
        oauth=SimpleNamespace(complete=AsyncMock(side_effect=OAuthStateError("bad-state")))
    )
    with pytest.raises(HTTPException) as exc_info:
        await oauth_callback_flow(
            params=OAuthCallbackParams(
                provider_key="google",
                code="code",
                state=state.state_token,
                error=None,
                error_description=None,
            ),
            request=_request(),
            session=AsyncMock(),
            settings=Settings(),
            load_oauth_state=AsyncMock(return_value=state),
            load_connection_for_state=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
        )
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_oauth_callback_flow_generic_error_revokes_connection() -> None:
    conn = _connection()
    state = _state(conn.id)
    session = AsyncMock()
    omni = SimpleNamespace(
        oauth=SimpleNamespace(complete=AsyncMock(side_effect=RuntimeError("boom")))
    )

    with pytest.raises(HTTPException):
        await oauth_callback_flow(
            params=OAuthCallbackParams(
                provider_key="google",
                code="code",
                state=state.state_token,
                error=None,
                error_description=None,
            ),
            request=_request(),
            session=session,
            settings=Settings(),
            load_oauth_state=AsyncMock(return_value=state),
            load_connection_for_state=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
        )

    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_oauth_callback_flow_success_without_redirect() -> None:
    conn = _connection()
    conn.provider_config = {}
    state = _state(conn.id)
    stored = SimpleNamespace(granted_scopes=["a"], provider_account_id="acct_1")
    omni = SimpleNamespace(oauth=SimpleNamespace(complete=AsyncMock(return_value=stored)))

    with patch("omnidapter_server.services.oauth_flows.transition_to_active", new=AsyncMock()):
        response = await oauth_callback_flow(
            params=OAuthCallbackParams(
                provider_key="google",
                code="code",
                state=state.state_token,
                error=None,
                error_description=None,
            ),
            request=_request(),
            session=AsyncMock(),
            settings=Settings(),
            load_oauth_state=AsyncMock(return_value=state),
            load_connection_for_state=AsyncMock(return_value=conn),
            build_omni=AsyncMock(return_value=omni),
        )

    payload = cast(dict[str, Any], response)
    assert payload["status"] == "connected"
