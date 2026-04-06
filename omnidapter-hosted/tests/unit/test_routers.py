"""Unit tests for hosted dashboard service flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.dashboard import (
    create_api_key_flow,
    list_api_keys_flow,
    list_members,
    remove_member,
    revoke_api_key_flow,
    update_tenant_name,
    update_user_name,
)


class _ScalarResult:
    def __init__(self, *, one: object | None = None, many: list[object] | None = None) -> None:
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self) -> object | None:
        return self._one

    def scalars(self) -> _ScalarResult:
        return self

    def all(self) -> list[object]:
        return self._many


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _tenant() -> Tenant:
    ts = _now()
    return Tenant(
        id=uuid.uuid4(), name="Acme", plan="free", is_active=True, created_at=ts, updated_at=ts
    )


def _api_key(tenant_id: uuid.UUID) -> HostedAPIKey:
    return HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="main",
        key_hash="hash",
        key_prefix="omni_key_abcd",
        created_at=_now(),
        last_used_at=None,
    )


def _membership(tenant_id: uuid.UUID, user_id: uuid.UUID, role: str = "member") -> HostedMembership:
    return HostedMembership(
        id=uuid.uuid4(), tenant_id=tenant_id, user_id=user_id, role=role, created_at=_now()
    )


def _user() -> HostedUser:
    return HostedUser(
        id=uuid.uuid4(),
        email="u@example.com",
        name="User",
        workos_user_id="workos_1",
        created_at=_now(),
        updated_at=_now(),
    )


# ---------------------------------------------------------------------------
# API key flows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_api_keys_flow() -> None:
    tenant_id = uuid.uuid4()
    key = _api_key(tenant_id)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[key]))

    result = await list_api_keys_flow(tenant_id, session)

    assert result == [key]


@pytest.mark.asyncio
async def test_create_api_key_flow_requires_admin() -> None:
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await create_api_key_flow(uuid.uuid4(), "prod", MemberRole.MEMBER, session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_create_api_key_flow_success() -> None:
    tenant_id = uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        obj.created_at = _now()  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)

    with patch(
        "omnidapter_hosted.services.dashboard.generate_hosted_api_key",
        return_value=("omni_raw", "hashed", "omni_raw__12"),
    ):
        raw_key, api_key = await create_api_key_flow(tenant_id, "prod", MemberRole.OWNER, session)

    assert raw_key == "omni_raw"
    assert api_key.name == "prod"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_api_key_flow_requires_admin() -> None:
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await revoke_api_key_flow(uuid.uuid4(), uuid.uuid4(), MemberRole.MEMBER, session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_revoke_api_key_flow_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await revoke_api_key_flow(uuid.uuid4(), uuid.uuid4(), MemberRole.OWNER, session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key_flow_success() -> None:
    tenant_id = uuid.uuid4()
    key = _api_key(tenant_id)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=key), MagicMock()])
    session.commit = AsyncMock()

    await revoke_api_key_flow(key.id, tenant_id, MemberRole.OWNER, session)

    assert session.execute.await_count == 1
    session.delete.assert_called_once_with(key)
    session.commit.assert_awaited_once()


# ---------------------------------------------------------------------------
# Member flows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_members() -> None:
    tenant_id = uuid.uuid4()
    user = _user()
    membership = _membership(tenant_id, user.id)
    session = AsyncMock()

    class _PairResult:
        def all(self) -> list[object]:
            return [(membership, user)]

    session.execute = AsyncMock(return_value=_PairResult())

    rows = await list_members(tenant_id, session)

    assert len(rows) == 1
    m, u = rows[0]
    assert m is membership
    assert u is user


@pytest.mark.asyncio
async def test_remove_member_requires_admin() -> None:
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await remove_member(uuid.uuid4(), uuid.uuid4(), MemberRole.MEMBER, uuid.uuid4(), session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_remove_member_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await remove_member(uuid.uuid4(), uuid.uuid4(), MemberRole.OWNER, uuid.uuid4(), session)
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_remove_member_cannot_remove_owner() -> None:
    tenant_id = uuid.uuid4()
    target_id = uuid.uuid4()
    membership = _membership(tenant_id, target_id, role=MemberRole.OWNER)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=membership))

    with pytest.raises(HTTPException) as exc_info:
        await remove_member(tenant_id, target_id, MemberRole.OWNER, uuid.uuid4(), session)
    assert exc_info.value.status_code == 400
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "cannot_remove_owner"


@pytest.mark.asyncio
async def test_remove_member_cannot_remove_self() -> None:
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    membership = _membership(tenant_id, user_id, role=MemberRole.ADMIN)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=membership))

    with pytest.raises(HTTPException) as exc_info:
        await remove_member(tenant_id, user_id, MemberRole.OWNER, user_id, session)
    assert exc_info.value.status_code == 400
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "cannot_remove_self"


# ---------------------------------------------------------------------------
# Profile / tenant name flows
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_user_name() -> None:
    user = _user()
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await update_user_name(user, "New Name", session)

    assert result.name == "New Name"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_tenant_name_requires_admin() -> None:
    tenant = _tenant()
    session = AsyncMock()
    with pytest.raises(HTTPException) as exc_info:
        await update_tenant_name(tenant, "New", MemberRole.MEMBER, session)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_update_tenant_name_success() -> None:
    tenant = _tenant()
    session = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    result = await update_tenant_name(tenant, "New Corp", MemberRole.OWNER, session)

    assert result.name == "New Corp"
    session.commit.assert_awaited_once()
