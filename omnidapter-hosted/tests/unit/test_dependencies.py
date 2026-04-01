"""Unit tests for hosted dependency helpers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.dependencies import (
    HostedAuthContext,
    get_encryption_service,
    get_hosted_auth_context,
    get_request_id,
)
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_server.config import Settings as ServerSettings
from starlette.requests import Request


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tenant() -> Tenant:
    ts = _now()
    return Tenant(
        id=uuid.uuid4(),
        name="Acme",
        plan="free",
        is_active=True,
        created_at=ts,
        updated_at=ts,
    )


def _api_key(tenant_id: uuid.UUID) -> HostedAPIKey:
    return HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="primary",
        key_hash="hash",
        key_prefix="omni_key_abcd",
        created_at=_now(),
        last_used_at=None,
    )


def _request(authorization: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if authorization is not None:
        headers.append((b"authorization", authorization.encode()))
    return Request({"type": "http", "method": "GET", "path": "/", "headers": headers})


def test_hosted_auth_context_properties() -> None:
    tenant = _tenant()
    api_key = _api_key(tenant.id)
    ctx = HostedAuthContext(api_key=api_key, tenant=tenant)

    assert ctx.tenant_id == tenant.id
    assert ctx.plan == tenant.plan


def test_get_encryption_service_from_server_settings() -> None:
    settings = ServerSettings(
        omnidapter_encryption_key="current-key",
        omnidapter_encryption_key_previous="previous-key",
    )
    service = get_encryption_service(settings)
    assert service._current_key == "current-key"
    assert service._previous_key == "previous-key"


def test_get_request_id_fallback() -> None:
    req = _request()
    assert get_request_id(req) == "req_unknown"
    req.state.request_id = "req_abc"
    assert get_request_id(req) == "req_abc"


@pytest.mark.asyncio
async def test_get_hosted_auth_context_missing_authorization() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_hosted_auth_context(
            request=_request(),
            bearer_credentials=None,
            session=AsyncMock(),
            hosted_settings=HostedSettings(),
        )

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "invalid_api_key"


@pytest.mark.asyncio
async def test_get_hosted_auth_context_invalid_authorization_scheme() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_hosted_auth_context(
            request=_request("Token abc"),
            bearer_credentials=None,
            session=AsyncMock(),
            hosted_settings=HostedSettings(),
        )

    assert exc_info.value.status_code == 401
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert "Bearer" in detail["message"]


@pytest.mark.asyncio
async def test_get_hosted_auth_context_invalid_key() -> None:
    with (
        patch(
            "omnidapter_hosted.dependencies.authenticate_hosted_key",
            new=AsyncMock(return_value=None),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_hosted_auth_context(
            request=_request("Bearer omni_invalid"),
            bearer_credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="omni_invalid",
            ),
            session=AsyncMock(),
            hosted_settings=HostedSettings(),
        )

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_hosted_auth_context_rate_limited() -> None:
    req = _request("Bearer omni_valid")
    tenant = _tenant()
    api_key = _api_key(tenant.id)

    with (
        patch(
            "omnidapter_hosted.dependencies.authenticate_hosted_key",
            new=AsyncMock(return_value=(api_key, tenant)),
        ),
        patch(
            "omnidapter_hosted.dependencies.check_rate_limit",
            new=AsyncMock(return_value=(False, 60, 0, 1_700_000_000.0)),
        ),
        patch(
            "omnidapter_hosted.dependencies.update_key_last_used",
            new=AsyncMock(),
        ),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_hosted_auth_context(
            request=req,
            bearer_credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="omni_valid",
            ),
            session=AsyncMock(),
            hosted_settings=HostedSettings(hosted_rate_limit_free=60, hosted_rate_limit_paid=600),
        )

    assert exc_info.value.status_code == 429
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["X-RateLimit-Limit"] == "60"
    assert req.state.rate_limit["remaining"] == 0


@pytest.mark.asyncio
async def test_get_hosted_auth_context_success() -> None:
    req = _request("Bearer omni_valid")
    tenant = _tenant()
    api_key = _api_key(tenant.id)
    update_last_used = AsyncMock()

    with (
        patch(
            "omnidapter_hosted.dependencies.authenticate_hosted_key",
            new=AsyncMock(return_value=(api_key, tenant)),
        ),
        patch(
            "omnidapter_hosted.dependencies.check_rate_limit",
            new=AsyncMock(return_value=(True, 60, 59, 1_700_000_000.0)),
        ),
        patch(
            "omnidapter_hosted.dependencies.update_key_last_used",
            new=update_last_used,
        ),
    ):
        ctx = await get_hosted_auth_context(
            request=req,
            bearer_credentials=HTTPAuthorizationCredentials(
                scheme="Bearer",
                credentials="omni_valid",
            ),
            session=AsyncMock(),
            hosted_settings=HostedSettings(hosted_rate_limit_free=60, hosted_rate_limit_paid=600),
        )

    assert isinstance(ctx, HostedAuthContext)
    assert ctx.tenant_id == tenant.id
    assert req.state.rate_limit["limit"] == 60
    update_last_used.assert_awaited_once_with(api_key.id, ANY)


@pytest.mark.asyncio
async def test_get_dashboard_auth_context_expired_token() -> None:
    import jwt
    from omnidapter_hosted.dependencies import get_dashboard_auth_context

    token = jwt.encode({"exp": 0, "sub": str(uuid.uuid4())}, "a" * 32, algorithm="HS256")

    with pytest.raises(HTTPException) as exc_info:
        await get_dashboard_auth_context(
            bearer_credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            session=AsyncMock(),
            settings=HostedSettings(jwt_secret="a" * 32),
        )

    assert exc_info.value.status_code == 401
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "token_expired"


@pytest.mark.asyncio
async def test_get_dashboard_auth_context_invalid_token() -> None:
    from omnidapter_hosted.dependencies import get_dashboard_auth_context

    with pytest.raises(HTTPException) as exc_info:
        await get_dashboard_auth_context(
            bearer_credentials=HTTPAuthorizationCredentials(
                scheme="Bearer", credentials="not-a-jwt"
            ),
            session=AsyncMock(),
            settings=HostedSettings(jwt_secret="a" * 32),
        )

    assert exc_info.value.status_code == 401
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "invalid_token"


@pytest.mark.asyncio
async def test_get_dashboard_auth_context_user_not_found() -> None:
    import jwt
    from omnidapter_hosted.dependencies import get_dashboard_auth_context

    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "tenant_id": str(uuid.uuid4())}, "a" * 32, algorithm="HS256"
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()  # Sync result object
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc_info:
        await get_dashboard_auth_context(
            bearer_credentials=HTTPAuthorizationCredentials(scheme="Bearer", credentials=token),
            session=mock_session,
            settings=HostedSettings(jwt_secret="a" * 32),
        )

    assert exc_info.value.status_code == 401
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "user_not_found"
