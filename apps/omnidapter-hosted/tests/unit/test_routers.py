"""Unit tests for hosted router handlers."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from omnidapter_hosted.dependencies import HostedAuthContext
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.routers.api_keys import (
    CreateAPIKeyRequest,
    create_api_key,
    list_api_keys,
    revoke_api_key,
)
from omnidapter_hosted.routers.memberships import (
    CreateMembershipRequest,
    create_membership,
    delete_membership,
    list_memberships,
)
from omnidapter_hosted.routers.tenants import (
    CreateTenantRequest,
    create_tenant,
    get_current_tenant,
)
from omnidapter_hosted.routers.users import (
    CreateUserRequest,
    create_user,
    get_user,
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
        name="main",
        key_hash="hash",
        key_prefix="omni_live_ab",
        is_active=True,
        is_test=False,
        created_at=_now(),
        last_used_at=None,
    )


def _auth() -> HostedAuthContext:
    tenant = _tenant()
    return HostedAuthContext(api_key=_api_key(tenant.id), tenant=tenant)


@pytest.mark.asyncio
async def test_list_api_keys() -> None:
    auth = _auth()
    key = _api_key(auth.tenant_id)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[key]))

    response = await list_api_keys(auth=auth, session=session, request_id="req_1")

    assert response["meta"]["request_id"] == "req_1"
    assert response["data"][0].name == "main"


@pytest.mark.asyncio
async def test_create_api_key() -> None:
    auth = _auth()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        obj.created_at = _now()  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)

    with patch(
        "omnidapter_hosted.routers.api_keys.generate_hosted_api_key",
        return_value=("omni_live_raw", "hashed", "omni_live_ra"),
    ):
        response = await create_api_key(
            body=CreateAPIKeyRequest(name="prod", is_test=False),
            auth=auth,
            session=session,
            request_id="req_2",
        )

    assert response["meta"]["request_id"] == "req_2"
    assert response["data"]["raw_key"] == "omni_live_raw"
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_revoke_api_key_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await revoke_api_key(
            key_id="not-a-uuid",
            auth=_auth(),
            session=AsyncMock(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await revoke_api_key(
            key_id=str(uuid.uuid4()),
            auth=_auth(),
            session=session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_revoke_api_key_success() -> None:
    auth = _auth()
    key = _api_key(auth.tenant_id)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=key), MagicMock()])
    session.commit = AsyncMock()

    await revoke_api_key(key_id=str(key.id), auth=auth, session=session)

    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_list_memberships() -> None:
    auth = _auth()
    membership = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=auth.tenant_id,
        user_id=uuid.uuid4(),
        role="member",
        created_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[membership]))

    response = await list_memberships(auth=auth, session=session, request_id="req_3")

    assert response["meta"]["request_id"] == "req_3"
    assert response["data"][0].role == "member"


@pytest.mark.asyncio
async def test_create_membership_invalid_user_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await create_membership(
            body=CreateMembershipRequest(user_id="invalid", role="member"),
            auth=_auth(),
            session=AsyncMock(),
            request_id="req_4",
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_create_membership_duplicate() -> None:
    auth = _auth()
    existing = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=auth.tenant_id,
        user_id=uuid.uuid4(),
        role="member",
        created_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=existing))

    with pytest.raises(HTTPException) as exc_info:
        await create_membership(
            body=CreateMembershipRequest(user_id=str(existing.user_id), role="admin"),
            auth=auth,
            session=session,
            request_id="req_5",
        )

    assert exc_info.value.status_code == 409


@pytest.mark.asyncio
async def test_create_membership_success() -> None:
    auth = _auth()
    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        obj.created_at = _now()  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)

    response = await create_membership(
        body=CreateMembershipRequest(user_id=str(uuid.uuid4()), role="owner"),
        auth=auth,
        session=session,
        request_id="req_6",
    )

    assert response["meta"]["request_id"] == "req_6"
    assert response["data"].tenant_id == str(auth.tenant_id)
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_membership_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await delete_membership(
            membership_id="invalid",
            auth=_auth(),
            session=AsyncMock(),
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_membership_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await delete_membership(
            membership_id=str(uuid.uuid4()),
            auth=_auth(),
            session=session,
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_delete_membership_success() -> None:
    auth = _auth()
    membership = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=auth.tenant_id,
        user_id=uuid.uuid4(),
        role="member",
        created_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(one=membership), MagicMock()])
    session.commit = AsyncMock()

    await delete_membership(
        membership_id=str(membership.id),
        auth=auth,
        session=session,
    )

    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_current_tenant_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await get_current_tenant(auth=_auth(), session=session, request_id="req_7")

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_current_tenant_success() -> None:
    auth = _auth()
    tenant = _tenant()
    tenant.id = auth.tenant_id
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=tenant))

    response = await get_current_tenant(auth=auth, session=session, request_id="req_8")

    assert response["meta"]["request_id"] == "req_8"
    assert response["data"].id == str(auth.tenant_id)


@pytest.mark.asyncio
async def test_create_tenant() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        obj.created_at = _now()  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)

    response = await create_tenant(
        body=CreateTenantRequest(name="Acme", plan="free"),
        session=session,
        request_id="req_9",
    )

    assert response["meta"]["request_id"] == "req_9"
    assert response["data"].name == "Acme"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_user_email_taken() -> None:
    existing = HostedUser(
        id=uuid.uuid4(),
        email="taken@example.com",
        name="Taken",
        workos_user_id=None,
        created_at=_now(),
        updated_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=existing))

    with pytest.raises(HTTPException) as exc_info:
        await create_user(
            body=CreateUserRequest(email="taken@example.com", name="New"),
            session=session,
            request_id="req_10",
        )

    assert exc_info.value.status_code == 409
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "email_taken"


@pytest.mark.asyncio
async def test_create_user_success() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        obj.created_at = _now()  # type: ignore[attr-defined]

    session.refresh = AsyncMock(side_effect=_refresh)

    response = await create_user(
        body=CreateUserRequest(email="ok@example.com", name="OK"),
        session=session,
        request_id="req_11",
    )

    assert response["meta"]["request_id"] == "req_11"
    assert response["data"].email == "ok@example.com"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_user_invalid_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_user(
            user_id="invalid",
            auth=_auth(),
            session=AsyncMock(),
            request_id="req_12",
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_user_not_found() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=None))

    with pytest.raises(HTTPException) as exc_info:
        await get_user(
            user_id=str(uuid.uuid4()),
            auth=_auth(),
            session=session,
            request_id="req_13",
        )

    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_user_success() -> None:
    user = HostedUser(
        id=uuid.uuid4(),
        email="u@example.com",
        name="User",
        workos_user_id="workos_1",
        created_at=_now(),
        updated_at=_now(),
    )
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(one=user))

    response = await get_user(
        user_id=str(user.id),
        auth=_auth(),
        session=session,
        request_id="req_14",
    )

    assert response["meta"]["request_id"] == "req_14"
    assert response["data"].id == str(user.id)
