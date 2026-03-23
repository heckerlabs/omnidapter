"""OAuth state store factory — selects implementation based on settings priority."""

from __future__ import annotations

import logging

from omnidapter.stores.memory import InMemoryOAuthStateStore
from omnidapter.stores.oauth_state import OAuthStateStore
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.encryption import EncryptionService

logger = logging.getLogger(__name__)

_warned_inmemory = False
_inmemory_store: InMemoryOAuthStateStore | None = None


def build_oauth_state_store(
    settings,
    session: AsyncSession,
    encryption: EncryptionService,
) -> OAuthStateStore:
    """Build OAuth state store.

    Redis is preferred when configured. Otherwise fall back to in-memory and warn.
    """
    global _warned_inmemory, _inmemory_store

    if settings.omnidapter_oauth_state_redis_url:
        from omnidapter_server.stores.redis_oauth_state_store import RedisOAuthStateStore

        return RedisOAuthStateStore(
            redis_url=settings.omnidapter_oauth_state_redis_url,
            encryption=encryption,
        )

    if not _warned_inmemory:
        logger.warning(
            "Using in-memory OAuth state store. "
            "This is NOT suitable for multi-worker deployments. "
            "Set OMNIDAPTER_OAUTH_STATE_REDIS_URL for shared state."
        )
        _warned_inmemory = True

    if _inmemory_store is None:
        _inmemory_store = InMemoryOAuthStateStore()
    return _inmemory_store
