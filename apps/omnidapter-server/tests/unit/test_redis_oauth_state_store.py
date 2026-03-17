"""Unit tests for Redis OAuth state store."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from omnidapter_server.stores.redis_oauth_state_store import RedisOAuthStateStore


@pytest.mark.asyncio
async def test_save_state_encrypts_pkce_and_sets_ttl() -> None:
    redis_client = AsyncMock()
    encryption = MagicMock()
    encryption.encrypt.return_value = "encrypted-pkce"

    with patch("redis.asyncio.from_url", return_value=redis_client):
        store = RedisOAuthStateStore("redis://localhost:6379/0", encryption)

    await store.save_state(
        state_id="state_1",
        payload={"connection_id": "conn", "code_verifier": "plain-pkce"},
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
    )

    args = redis_client.setex.await_args.args
    assert args[0].endswith("state_1")
    assert args[1] > 0
    payload = json.loads(args[2])
    assert payload["code_verifier"] == "encrypted-pkce"
    assert payload["_pkce_encrypted"] is True


@pytest.mark.asyncio
async def test_load_state_returns_none_when_missing() -> None:
    redis_client = AsyncMock()
    redis_client.get.return_value = None

    with patch("redis.asyncio.from_url", return_value=redis_client):
        store = RedisOAuthStateStore("redis://localhost:6379/0", MagicMock())

    assert await store.load_state("missing") is None


@pytest.mark.asyncio
async def test_load_state_decrypts_pkce_when_marked() -> None:
    redis_client = AsyncMock()
    redis_client.get.return_value = json.dumps(
        {
            "connection_id": "conn",
            "code_verifier": "encrypted-pkce",
            "_pkce_encrypted": True,
        }
    )
    encryption = MagicMock()
    encryption.decrypt.return_value = "plain-pkce"

    with patch("redis.asyncio.from_url", return_value=redis_client):
        store = RedisOAuthStateStore("redis://localhost:6379/0", encryption)

    payload = await store.load_state("state_2")

    assert payload is not None
    assert payload["code_verifier"] == "plain-pkce"
    assert "_pkce_encrypted" not in payload


@pytest.mark.asyncio
async def test_delete_state_calls_redis_delete() -> None:
    redis_client = AsyncMock()

    with patch("redis.asyncio.from_url", return_value=redis_client):
        store = RedisOAuthStateStore("redis://localhost:6379/0", MagicMock())

    await store.delete_state("state_3")

    redis_client.delete.assert_awaited_once()
