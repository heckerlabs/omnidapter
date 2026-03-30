"""Unit tests for hosted API key generation and verification."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.services.auth import (
    authenticate_hosted_key,
    generate_hosted_api_key,
    update_key_last_used,
    verify_hosted_api_key,
)


class _ScalarResult:
    def __init__(self, one=None, many=None):
        self._one = one
        self._many = many or []

    def scalar_one_or_none(self):
        return self._one

    def scalars(self):
        return self

    def all(self):
        return self._many


def _tenant(active: bool = True) -> Tenant:
    return Tenant(
        id=uuid.uuid4(),
        name="Acme",
        plan="free",
        is_active=active,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


def _api_key(tenant_id: uuid.UUID, key_hash: str = "hash") -> HostedAPIKey:
    return HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="key",
        key_hash=key_hash,
        key_prefix="omni_key_abcd",
        created_at=datetime.now(timezone.utc),
        last_used_at=None,
    )


def test_generate_key_format():
    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    assert raw_key.startswith("omni_")
    assert len(raw_key) > 10


def test_key_prefix_length():
    raw_key, _, key_prefix = generate_hosted_api_key()
    assert len(key_prefix) == 12
    assert raw_key.startswith(key_prefix)


def test_verify_correct_key():
    raw_key, key_hash, _ = generate_hosted_api_key()
    assert verify_hosted_api_key(raw_key, key_hash) is True


def test_verify_wrong_key():
    _, key_hash, _ = generate_hosted_api_key()
    assert verify_hosted_api_key("omni_wrongkeyvalue12345678901", key_hash) is False


def test_verify_tampered_hash():
    raw_key, key_hash, _ = generate_hosted_api_key()
    assert verify_hosted_api_key(raw_key, "tampered" + key_hash) is False


def test_verify_invalid_hash():
    assert verify_hosted_api_key("omni_anything", "not_a_valid_hash") is False


def test_verify_empty():
    assert verify_hosted_api_key("", "") is False


def test_unique_keys():
    keys = {generate_hosted_api_key()[0] for _ in range(20)}
    assert len(keys) == 20


def test_hash_differs_per_key():
    _, hash1, _ = generate_hosted_api_key()
    _, hash2, _ = generate_hosted_api_key()
    assert hash1 != hash2


def test_default_prefix():
    raw_key, _, _ = generate_hosted_api_key()
    assert raw_key.startswith("omni_")


@pytest.mark.asyncio
async def test_authenticate_hosted_key_invalid_prefix_returns_none() -> None:
    result = await authenticate_hosted_key("not-valid", AsyncMock())
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_hosted_key_no_matching_candidate_returns_none() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult(many=[]))

    result = await authenticate_hosted_key("omni_abcdefghijklmnopqrstuvwxyz123456", session)
    assert result is None


@pytest.mark.asyncio
async def test_authenticate_hosted_key_valid_returns_key_and_tenant() -> None:
    tenant = _tenant(active=True)
    raw_key, key_hash, _ = generate_hosted_api_key()
    key = _api_key(tenant.id, key_hash=key_hash)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(many=[key]), _ScalarResult(one=tenant)])

    result = await authenticate_hosted_key(raw_key, session)
    assert result is not None
    resolved_key, resolved_tenant = result
    assert resolved_key.id == key.id
    assert resolved_tenant.id == tenant.id


@pytest.mark.asyncio
async def test_authenticate_hosted_key_inactive_tenant_returns_none() -> None:
    tenant = _tenant(active=False)
    raw_key, key_hash, _ = generate_hosted_api_key()
    key = _api_key(tenant.id, key_hash=key_hash)
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_ScalarResult(many=[key]), _ScalarResult(one=tenant)])

    result = await authenticate_hosted_key(raw_key, session)
    assert result is None


@pytest.mark.asyncio
async def test_update_key_last_used_commits() -> None:
    session = AsyncMock()
    key_id = uuid.uuid4()
    await update_key_last_used(key_id, session)
    session.execute.assert_awaited_once()
    session.commit.assert_awaited_once()
