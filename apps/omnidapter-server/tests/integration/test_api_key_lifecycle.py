"""Integration tests for API key lifecycle."""

from __future__ import annotations

import uuid

import pytest
from omnidapter_server.models.api_key import APIKey
from omnidapter_server.services.auth import authenticate_api_key, generate_api_key, verify_api_key
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_api_key_created_with_hash(session: AsyncSession):
    """API key is stored hashed; raw key is not stored."""
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
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
async def test_api_key_prefix_uses_live_prefix(session: AsyncSession):
    """Live API keys use omni_live_ prefix."""
    raw_key, key_hash, key_prefix = generate_api_key(is_test=False)
    assert raw_key.startswith("omni_live_")
    assert key_prefix.startswith("omni_live_")


@pytest.mark.asyncio
async def test_api_key_prefix_uses_test_prefix(session: AsyncSession):
    """Test API keys use omni_test_ prefix."""
    raw_key, key_hash, key_prefix = generate_api_key(is_test=True)
    assert raw_key.startswith("omni_test_")
    assert key_prefix.startswith("omni_test_")


@pytest.mark.asyncio
async def test_authenticate_valid_api_key(session: AsyncSession):
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
        name="test-key",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(key)
    await session.flush()

    result = await authenticate_api_key(raw_key, session)
    assert result is not None
    assert str(result.id) == str(key.id)


@pytest.mark.asyncio
async def test_authenticate_inactive_key_returns_none(session: AsyncSession):
    raw_key, key_hash, key_prefix = generate_api_key()
    key = APIKey(
        id=uuid.uuid4(),
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
    result = await authenticate_api_key("omni_live_invalidkeyabcde12345678", session)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_wrong_prefix_returns_none(session: AsyncSession):
    result = await authenticate_api_key("wrong_prefix_key", session)
    assert result is None


@pytest.mark.asyncio
async def test_multiple_keys_work_independently(session: AsyncSession):
    """Two API keys both authenticate correctly and are independent."""
    raw_key1, key_hash1, key_prefix1 = generate_api_key()
    raw_key2, key_hash2, key_prefix2 = generate_api_key()

    key1 = APIKey(
        id=uuid.uuid4(),
        name="key1",
        key_hash=key_hash1,
        key_prefix=key_prefix1,
        is_active=True,
    )
    key2 = APIKey(
        id=uuid.uuid4(),
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
    assert str(result1.id) == str(key1.id)
    assert str(result2.id) == str(key2.id)
