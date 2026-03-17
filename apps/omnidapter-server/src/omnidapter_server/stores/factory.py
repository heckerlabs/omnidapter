"""OAuth state store factory — selects implementation based on settings priority."""

from __future__ import annotations

import logging

from omnidapter.stores.memory import InMemoryOAuthStateStore
from omnidapter.stores.oauth_state import OAuthStateStore
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.encryption import EncryptionService

logger = logging.getLogger(__name__)

_warned_inmemory = False


def build_oauth_state_store(
    settings,
    session: AsyncSession,
    encryption: EncryptionService,
) -> OAuthStateStore:
    """Build the appropriate OAuth state store based on settings priority:

    1. OMNIDAPTER_OAUTH_STATE_REDIS_URL  -> RedisOAuthStateStore
    2. OMNIDAPTER_OAUTH_STATE_DB_URL     -> DatabaseOAuthStateStore (uses db url)
    3. omnidapter_database_url set       -> DatabaseOAuthStateStore (uses main db url)
    4. fallback                          -> InMemoryOAuthStateStore (warns)
    """
    global _warned_inmemory

    if settings.omnidapter_oauth_state_redis_url:
        from omnidapter_server.stores.redis_oauth_state_store import RedisOAuthStateStore

        return RedisOAuthStateStore(
            redis_url=settings.omnidapter_oauth_state_redis_url,
            encryption=encryption,
        )

    if settings.omnidapter_database_url:
        from omnidapter_server.stores.oauth_state_store import DatabaseOAuthStateStore

        return DatabaseOAuthStateStore(session=session, encryption=encryption)

    if not _warned_inmemory:
        logger.warning(
            "Using in-memory OAuth state store. "
            "This is NOT suitable for multi-worker or production deployments. "
            "Set OMNIDAPTER_OAUTH_STATE_REDIS_URL or OMNIDAPTER_DATABASE_URL."
        )
        _warned_inmemory = True

    return InMemoryOAuthStateStore()
