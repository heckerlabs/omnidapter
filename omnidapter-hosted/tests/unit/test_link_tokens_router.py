"""Unit tests for the link tokens router — including reconnect (connection_id) support."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter_hosted.dependencies import HostedAuthContext
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.routers.link_tokens import (
    CreateLinkTokenRequest,
    _resolve_reconnect_provider,
    create_link_token_endpoint,
)
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.models.link_token import LinkToken


class _ScalarResult:
    def __init__(self, *, one: object | None = None) -> None:
        self._one = one

    def scalar_one_or_none(self) -> object | None:
        return self._one


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _auth() -> HostedAuthContext:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Acme",
        plan="free",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="key",
        key_hash="hash",
        key_prefix="omni_key_abcd",
        created_at=_now(),
        last_used_at=None,
    )
    return HostedAuthContext(api_key=api_key, tenant=tenant)


def _link_token_model(tenant_id: uuid.UUID) -> LinkToken:
    return LinkToken(
        id=uuid.uuid4(),
        token_hash="hash",
        token_prefix="lt_abc123456789",
        end_user_id="user_1",
        allowed_providers=None,
        redirect_uri="https://app.example.com/done",
        expires_at=_now(),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )


# ---------------------------------------------------------------------------
# _resolve_reconnect_provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_resolve_reconnect_provider_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_reconnect_provider(uuid.uuid4(), uuid.uuid4(), session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_reconnect_provider_connection_missing() -> None:
    """Owner exists but the connection row is gone (data inconsistency)."""
    owner = HostedConnectionOwner(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        connection_id=uuid.uuid4(),
        created_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=owner), _ScalarResult(one=None)])

    with pytest.raises(HTTPException) as exc_info:
        await _resolve_reconnect_provider(uuid.uuid4(), uuid.uuid4(), session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_resolve_reconnect_provider_success() -> None:
    tenant_id = uuid.uuid4()
    conn_id = uuid.uuid4()
    owner = HostedConnectionOwner(
        id=uuid.uuid4(), tenant_id=tenant_id, connection_id=conn_id, created_at=_now()
    )
    conn = Connection(
        id=conn_id,
        provider_key="google",
        status=ConnectionStatus.ACTIVE,
        external_id="u1",
        refresh_failure_count=0,
        created_at=_now(),
        updated_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=owner), _ScalarResult(one=conn)])

    provider_key = await _resolve_reconnect_provider(conn_id, tenant_id, session)
    assert provider_key == "google"


# ---------------------------------------------------------------------------
# create_link_token_endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_link_token_no_connection_id() -> None:
    auth = _auth()
    token_model = _link_token_model(auth.tenant_id)
    session = AsyncMock()

    with patch(
        "omnidapter_hosted.routers.link_tokens.create_link_token",
        new=AsyncMock(return_value=("lt_rawtoken", token_model)),
    ):
        resp = await create_link_token_endpoint(
            body=CreateLinkTokenRequest(end_user_id="u1", redirect_uri="https://app.example.com"),
            auth=auth,
            session=session,
            settings=MagicMock(link_token_ttl_seconds=1800),
            request_id="req_1",
        )

    assert resp["data"]["token"] == "lt_rawtoken"
    assert "expires_at" in resp["data"]


@pytest.mark.asyncio
async def test_create_link_token_with_valid_connection_id() -> None:
    auth = _auth()
    conn_id = uuid.uuid4()
    token_model = _link_token_model(auth.tenant_id)
    token_model.connection_id = conn_id
    token_model.locked_provider_key = "google"
    session = AsyncMock()

    with (
        patch(
            "omnidapter_hosted.routers.link_tokens._resolve_reconnect_provider",
            new=AsyncMock(return_value="google"),
        ),
        patch(
            "omnidapter_hosted.routers.link_tokens.create_link_token",
            new=AsyncMock(return_value=("lt_reconnect", token_model)),
        ),
    ):
        resp = await create_link_token_endpoint(
            body=CreateLinkTokenRequest(connection_id=conn_id),
            auth=auth,
            session=session,
            settings=MagicMock(link_token_ttl_seconds=1800),
            request_id="req_2",
        )

    assert resp["data"]["token"] == "lt_reconnect"


@pytest.mark.asyncio
async def test_create_link_token_connection_not_found() -> None:
    """Creating a token with a connection_id that doesn't belong to the tenant raises 404."""
    auth = _auth()
    session = AsyncMock()

    with (
        patch(
            "omnidapter_hosted.routers.link_tokens._resolve_reconnect_provider",
            new=AsyncMock(side_effect=HTTPException(status_code=404, detail={})),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await create_link_token_endpoint(
            body=CreateLinkTokenRequest(connection_id=uuid.uuid4()),
            auth=auth,
            session=session,
            settings=MagicMock(link_token_ttl_seconds=1800),
            request_id="req_3",
        )
    assert exc_info.value.status_code == 404
