"""Integration tests for API key lifecycle."""

from __future__ import annotations

import uuid

import pytest
from omnidapter_api.models.api_key import APIKey
from omnidapter_api.models.organization import Organization
from omnidapter_api.services.auth import authenticate_api_key, generate_api_key, verify_api_key
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_api_key_created_with_hash(session: AsyncSession, org: Organization):
    """API key is stored hashed; raw key is not stored."""
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="integration-test",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(key)
    await session.flush()

    # Raw key is not stored
    assert raw_key not in key.key_hash
    # Key prefix matches
    assert raw_key.startswith(key.key_prefix)
    # Hash verifies correctly
    assert verify_api_key(raw_key, key.key_hash)


@pytest.mark.asyncio
async def test_authenticate_valid_api_key(session: AsyncSession, org: Organization):
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="test-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(key)
    await session.flush()

    result = await authenticate_api_key(raw_key, session)
    assert result is not None
    api_key, found_org = result
    assert str(api_key.id) == str(key.id)
    assert str(found_org.id) == str(org.id)


@pytest.mark.asyncio
async def test_authenticate_inactive_key_returns_none(session: AsyncSession, org: Organization):
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="inactive",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=False,  # Deactivated
    )
    session.add(key)
    await session.flush()

    result = await authenticate_api_key(raw_key, session)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_invalid_key_returns_none(session: AsyncSession):
    result = await authenticate_api_key("omni_sk_invalidkeyabcde12345678", session)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_wrong_prefix_returns_none(session: AsyncSession):
    result = await authenticate_api_key("wrong_prefix_key", session)
    assert result is None


@pytest.mark.asyncio
async def test_multiple_keys_for_same_org(session: AsyncSession, org: Organization):
    """Two keys for the same org both work independently."""
    raw_key1, key_hash1, key_prefix1 = generate_api_key()
    raw_key2, key_hash2, key_prefix2 = generate_api_key()

    key1 = APIKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="key1",
        key_hash=key_hash1,
        key_prefix=key_prefix1,
        is_active=True,
    )
    key2 = APIKey(
        id=uuid.uuid4(),
        organization_id=org.id,
        name="key2",
        key_hash=key_hash2,
        key_prefix=key_prefix2,
        is_active=True,
    )
    session.add(key1)
    session.add(key2)
    await session.flush()

    result1 = await authenticate_api_key(raw_key1, session)
    result2 = await authenticate_api_key(raw_key2, session)

    assert result1 is not None
    assert result2 is not None
    assert str(result1[0].id) == str(key1.id)
    assert str(result2[0].id) == str(key2.id)
