"""Unit tests for services/auth_flows — provision_user_flow, get_jwt_secret, issue_jwt."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth_flows import (
    _fallback_jwt_secret,
    get_jwt_secret,
    issue_jwt,
    provision_user_flow,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _ScalarResult:
    def __init__(self, *, one: object | None = None, many: list[object] | None = None) -> None:
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self) -> object | None:
        return self._one

    def scalar_one(self) -> object:
        assert self._one is not None
        return self._one

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[object]:
        return self._many


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _user(workos_id: str = "wos_123") -> HostedUser:
    return HostedUser(
        id=uuid.uuid4(),
        email="user@example.com",
        name="Test User",
        workos_user_id=workos_id,
        created_at=_now(),
        updated_at=_now(),
    )


def _tenant() -> Tenant:
    ts = _now()
    return Tenant(id=uuid.uuid4(), name="Acme", plan="free", is_active=True, created_at=ts, updated_at=ts)


def _membership(tenant_id: uuid.UUID, user_id: uuid.UUID, role: str = MemberRole.OWNER) -> HostedMembership:
    return HostedMembership(
        id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, role=role, created_at=_now()
    )


def _settings(secret: str = "mysecret_long_enough_for_hs256_signing", ttl: int = 3600) -> object:
    return SimpleNamespace(jwt_secret=secret, jwt_ttl_seconds=ttl)


# ---------------------------------------------------------------------------
# get_jwt_secret
# ---------------------------------------------------------------------------


def test_get_jwt_secret_uses_configured_value() -> None:
    settings = _settings(secret="configured_secret")
    assert get_jwt_secret(settings) == "configured_secret"


def test_get_jwt_secret_fallback_is_stable() -> None:
    import omnidapter_hosted.services.auth_flows as mod

    original = mod._fallback_jwt_secret
    try:
        mod._fallback_jwt_secret = None
        settings = _settings(secret="")
        secret1 = get_jwt_secret(settings)
        secret2 = get_jwt_secret(settings)
        assert secret1 == secret2
        assert len(secret1) > 0
    finally:
        mod._fallback_jwt_secret = original


def test_get_jwt_secret_configured_overrides_fallback() -> None:
    import omnidapter_hosted.services.auth_flows as mod

    original = mod._fallback_jwt_secret
    try:
        mod._fallback_jwt_secret = "old_fallback"
        settings = _settings(secret="explicit")
        assert get_jwt_secret(settings) == "explicit"
    finally:
        mod._fallback_jwt_secret = original


# ---------------------------------------------------------------------------
# issue_jwt
# ---------------------------------------------------------------------------


def test_issue_jwt_returns_string() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    token = issue_jwt(user_id, tenant_id, MemberRole.OWNER, _settings())
    assert isinstance(token, str)
    assert len(token) > 0


def test_issue_jwt_payload_fields() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    settings = _settings(secret="testsecret_long_enough_for_hs256_signing", ttl=1800)
    token = issue_jwt(user_id, tenant_id, MemberRole.ADMIN, settings)

    payload = jwt.decode(token, "testsecret_long_enough_for_hs256_signing", algorithms=["HS256"])
    assert payload["sub"] == str(user_id)
    assert payload["tenant_id"] == str(tenant_id)
    assert payload["role"] == MemberRole.ADMIN


def test_issue_jwt_expiry_is_in_future() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    settings = _settings(secret="testsecret_long_enough_for_hs256_signing", ttl=3600)
    token = issue_jwt(user_id, tenant_id, MemberRole.OWNER, settings)

    payload = jwt.decode(token, "testsecret_long_enough_for_hs256_signing", algorithms=["HS256"])
    assert payload["exp"] > int(time.time())


def test_issue_jwt_respects_ttl() -> None:
    user_id = uuid.uuid4()
    tenant_id = uuid.uuid4()
    before = int(time.time())
    secret = "s" * 32  # pad to meet HS256 minimum key length
    token = issue_jwt(user_id, tenant_id, MemberRole.OWNER, _settings(secret=secret, ttl=600))

    payload = jwt.decode(token, secret, algorithms=["HS256"])
    assert payload["exp"] - payload["iat"] == 600
    assert payload["iat"] >= before


# ---------------------------------------------------------------------------
# provision_user_flow — existing user paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_existing_user_by_workos_id() -> None:
    user = _user(workos_id="wos_abc")
    tenant = _tenant()
    membership = _membership(tenant.id, user.id)

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(one=user),       # lookup by workos_user_id
            _ScalarResult(one=membership), # owner membership
            _ScalarResult(one=tenant),     # tenant lookup
        ]
    )

    result_user, result_tenant, result_membership, initial_key = await provision_user_flow(
        workos_user_id="wos_abc",
        email="user@example.com",
        first_name="Test",
        last_name="User",
        session=session,
    )

    assert result_user is user
    assert result_tenant is tenant
    assert result_membership is membership
    assert initial_key is None  # no key on existing user


@pytest.mark.asyncio
async def test_provision_existing_user_falls_back_to_email() -> None:
    """User exists but was created before WorkOS — matched by email, workos_id set."""
    user = _user(workos_id=None)  # type: ignore[arg-type]
    user.workos_user_id = None
    tenant = _tenant()
    membership = _membership(tenant.id, user.id)

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(one=None),       # no match by workos_user_id
            _ScalarResult(one=user),       # match by email
            _ScalarResult(one=membership), # owner membership
            _ScalarResult(one=tenant),     # tenant lookup
        ]
    )
    session.flush = AsyncMock()

    result_user, _, _, initial_key = await provision_user_flow(
        workos_user_id="wos_new",
        email="user@example.com",
        first_name=None,
        last_name=None,
        session=session,
    )

    assert result_user.workos_user_id == "wos_new"
    assert initial_key is None
    session.flush.assert_awaited()


@pytest.mark.asyncio
async def test_provision_existing_user_falls_back_to_any_membership() -> None:
    """If no owner membership found, any membership is returned."""
    user = _user()
    tenant = _tenant()
    membership = _membership(tenant.id, user.id, role=MemberRole.ADMIN)

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(one=user),       # lookup by workos_user_id
            _ScalarResult(one=None),       # no owner membership
            _ScalarResult(one=membership), # fallback: any membership
            _ScalarResult(one=tenant),     # tenant lookup
        ]
    )

    _, _, result_membership, _ = await provision_user_flow(
        workos_user_id="wos_abc",
        email="user@example.com",
        first_name=None,
        last_name=None,
        session=session,
    )

    assert result_membership.role == MemberRole.ADMIN


@pytest.mark.asyncio
async def test_provision_existing_user_no_membership_raises_500() -> None:
    user = _user()

    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(one=user),  # lookup by workos_user_id
            _ScalarResult(one=None),  # no owner membership
            _ScalarResult(one=None),  # no membership at all
        ]
    )

    with pytest.raises(HTTPException) as exc_info:
        await provision_user_flow(
            workos_user_id="wos_abc",
            email="user@example.com",
            first_name=None,
            last_name=None,
            session=session,
        )

    assert exc_info.value.status_code == 500
    assert exc_info.value.detail["code"] == "no_membership"  # type: ignore[index]


# ---------------------------------------------------------------------------
# provision_user_flow — new user (first signup)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_provision_new_user_creates_all_entities() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(
        side_effect=[
            _ScalarResult(one=None),  # no match by workos_user_id
            _ScalarResult(one=None),  # no match by email
        ]
    )
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with patch(
        "omnidapter_hosted.services.auth_flows.generate_hosted_api_key",
        return_value=("omni_rawkey", "hashed", "omni_rawkey_12"),
    ):
        result_user, result_tenant, result_membership, initial_key = await provision_user_flow(
            workos_user_id="wos_new",
            email="new@example.com",
            first_name="Alice",
            last_name="Smith",
            session=session,
        )

    # Four adds: user, tenant, membership, api_key
    assert session.add.call_count == 4
    session.commit.assert_awaited_once()

    assert result_user.email == "new@example.com"
    assert result_user.workos_user_id == "wos_new"
    assert result_tenant.is_active is True
    assert result_membership.role == MemberRole.OWNER
    assert initial_key is not None
    assert getattr(initial_key, "raw_key") == "omni_rawkey"


@pytest.mark.asyncio
async def test_provision_new_user_name_from_full_name() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=None), _ScalarResult(one=None)])
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with patch("omnidapter_hosted.services.auth_flows.generate_hosted_api_key",
               return_value=("omni_r", "h", "omni_r00000")):
        result_user, result_tenant, _, _ = await provision_user_flow(
            workos_user_id="wos_1",
            email="a@b.com",
            first_name="Alice",
            last_name="Smith",
            session=session,
        )

    assert result_user.name == "Alice Smith"
    assert result_tenant.name == "Alice Smith"


@pytest.mark.asyncio
async def test_provision_new_user_name_fallback_to_email_prefix() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=None), _ScalarResult(one=None)])
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    with patch("omnidapter_hosted.services.auth_flows.generate_hosted_api_key",
               return_value=("omni_r", "h", "omni_r00000")):
        result_user, _, _, _ = await provision_user_flow(
            workos_user_id="wos_1",
            email="alice@example.com",
            first_name=None,
            last_name=None,
            session=session,
        )

    assert result_user.name == "alice"
