"""Unit tests for Hosted Dashboard service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.services.dashboard import (
    delete_provider_config_flow,
    remove_member,
    revoke_connection_flow,
    upsert_provider_config_flow,
)


@pytest.mark.asyncio
async def test_remove_member_owner_forbidden():
    """Fail if trying to remove a tenant owner."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_membership = HostedMembership(role=MemberRole.OWNER)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_membership
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await remove_member(
            tenant_id=tenant_id,
            target_user_id=user_id,
            requesting_role=MemberRole.OWNER,
            requesting_user_id=uuid.uuid4(),
            session=mock_session,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "cannot_remove_owner"


@pytest.mark.asyncio
async def test_remove_member_self_forbidden():
    """Fail if trying to remove yourself."""
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_membership = HostedMembership(role=MemberRole.ADMIN)

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_membership
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await remove_member(
            tenant_id=tenant_id,
            target_user_id=user_id,
            requesting_role=MemberRole.OWNER,
            requesting_user_id=user_id,  # Self
            session=mock_session,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail["code"] == "cannot_remove_self"


@pytest.mark.asyncio
async def test_revoke_connection_not_found():
    """Fail if revoking a connection that does not belong to the tenant."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await revoke_connection_flow(
            connection_id=uuid.uuid4(),
            tenant_id=uuid.uuid4(),
            role=MemberRole.ADMIN,
            session=mock_session,
        )
    assert exc.value.status_code == 404
    assert exc.value.detail["code"] == "not_found"


@pytest.mark.asyncio
async def test_delete_provider_config_not_found():
    """Fail if deleting a non-existent provider config."""
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute.return_value = mock_result

    with pytest.raises(HTTPException) as exc:
        await delete_provider_config_flow(
            tenant_id=uuid.uuid4(),
            provider_key="google",
            role=MemberRole.ADMIN,
            session=mock_session,
        )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_upsert_provider_config_update_path():
    """Verify that upserting an existing config updates the values."""
    tenant_id = uuid.uuid4()
    provider_key = "google"
    existing_config = HostedProviderConfig(
        tenant_id=tenant_id,
        provider_key=provider_key,
        client_id_encrypted=b"old_id",
        client_secret_encrypted=b"old_secret",
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_config
    mock_session.execute.return_value = mock_result

    mock_encryption = MagicMock()
    mock_encryption.encrypt.side_effect = [b"new_id", b"new_secret"]

    updated = await upsert_provider_config_flow(
        tenant_id=tenant_id,
        provider_key=provider_key,
        client_id="new_client",
        client_secret="new_secret",
        scopes=["email"],
        role=MemberRole.ADMIN,
        encryption=mock_encryption,
        session=mock_session,
    )

    assert updated.client_id_encrypted == b"new_id"
    assert updated.client_secret_encrypted == b"new_secret"
    assert updated.scopes == ["email"]
    mock_session.commit.assert_awaited_once()
