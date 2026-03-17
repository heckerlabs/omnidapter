"""Redis-backed OAuthStateStore for the Omnidapter library."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from omnidapter.stores.oauth_state import OAuthStateStore

from omnidapter_server.encryption import EncryptionService

_KEY_PREFIX = "omnidapter:oauth_state:"


class RedisOAuthStateStore(OAuthStateStore):
    """Persists OAuth state in Redis with PKCE verifier encryption.

    Requires redis-py with asyncio support (redis[asyncio]).
    """

    def __init__(self, redis_url: str, encryption: EncryptionService) -> None:
        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(redis_url, decode_responses=True)
        self._encryption = encryption

    async def save_state(
        self,
        state_id: str,
        payload: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        stored = dict(payload)
        if stored.get("code_verifier"):
            stored["code_verifier"] = self._encryption.encrypt(stored["code_verifier"])
            stored["_pkce_encrypted"] = True

        now = datetime.now(timezone.utc)
        ttl_seconds = max(1, int((expires_at - now).total_seconds()))

        key = f"{_KEY_PREFIX}{state_id}"
        await self._redis.setex(key, ttl_seconds, json.dumps(stored))

    async def load_state(self, state_id: str) -> dict[str, Any] | None:
        key = f"{_KEY_PREFIX}{state_id}"
        raw = await self._redis.get(key)
        if raw is None:
            return None

        stored: dict[str, Any] = json.loads(raw)
        if stored.pop("_pkce_encrypted", False) and stored.get("code_verifier"):
            stored["code_verifier"] = self._encryption.decrypt(stored["code_verifier"])

        return stored

    async def delete_state(self, state_id: str) -> None:
        key = f"{_KEY_PREFIX}{state_id}"
        await self._redis.delete(key)
