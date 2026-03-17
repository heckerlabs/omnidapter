"""Unit tests for OAuth state store factory selection."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


def _make_settings(**kwargs):
    s = MagicMock()
    s.omnidapter_oauth_state_redis_url = kwargs.get("redis_url", "")
    s.omnidapter_database_url = kwargs.get("db_url", "postgresql+asyncpg://localhost/omnidapter")
    return s


def _make_session():
    return MagicMock()


def _make_encryption():
    return MagicMock()


def test_factory_prefers_redis_when_configured():
    from omnidapter_server.stores.factory import build_oauth_state_store
    from omnidapter_server.stores.redis_oauth_state_store import RedisOAuthStateStore

    settings = _make_settings(redis_url="redis://localhost:6379")
    with patch("redis.asyncio.from_url", return_value=MagicMock()):
        store = build_oauth_state_store(settings, _make_session(), _make_encryption())
    assert isinstance(store, RedisOAuthStateStore)


def test_factory_uses_db_when_no_redis():
    from omnidapter_server.stores.factory import build_oauth_state_store
    from omnidapter_server.stores.oauth_state_store import DatabaseOAuthStateStore

    settings = _make_settings(redis_url="", db_url="postgresql+asyncpg://localhost/omnidapter")
    store = build_oauth_state_store(settings, _make_session(), _make_encryption())
    assert isinstance(store, DatabaseOAuthStateStore)


def test_factory_uses_inmemory_when_no_db_no_redis(caplog):
    import logging

    from omnidapter.stores.memory import InMemoryOAuthStateStore
    from omnidapter_server.stores import factory
    from omnidapter_server.stores.factory import build_oauth_state_store

    # Reset the warning flag so we get a fresh warning
    factory._warned_inmemory = False
    settings = _make_settings(redis_url="", db_url="")

    with caplog.at_level(logging.WARNING, logger="omnidapter_server.stores.factory"):
        store = build_oauth_state_store(settings, _make_session(), _make_encryption())

    assert isinstance(store, InMemoryOAuthStateStore)
    assert "in-memory" in caplog.text.lower()

    factory._warned_inmemory = False  # reset after test
