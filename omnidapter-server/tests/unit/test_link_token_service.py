"""Unit tests for the server link token service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter_server.models.link_token import LinkToken
from omnidapter_server.services.link_tokens import (
    create_link_token,
    generate_link_token,
    verify_link_token,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# generate_link_token
# ---------------------------------------------------------------------------


def test_generate_link_token_format() -> None:
    raw, hashed, prefix = generate_link_token()
    assert raw.startswith("lt_")
    assert len(raw) == 35  # "lt_" + 32 chars
    assert prefix == raw[:16]
    assert hashed != raw


def test_generate_link_token_hash_is_one_way() -> None:
    import bcrypt

    raw, hashed, _ = generate_link_token()
    assert bcrypt.checkpw(raw.encode(), hashed.encode())
    assert raw != hashed


def test_generate_link_token_is_random() -> None:
    token1, _, _ = generate_link_token()
    token2, _, _ = generate_link_token()
    assert token1 != token2


# ---------------------------------------------------------------------------
# create_link_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_link_token_basic() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    async def _refresh(obj: object) -> None:
        pass

    session.refresh = AsyncMock(side_effect=_refresh)

    # Capture what gets added to the session
    added: list[object] = []
    session.add = MagicMock(side_effect=lambda obj: added.append(obj))

    raw, model = await create_link_token(
        end_user_id="u1",
        allowed_providers=["google"],
        redirect_uri="https://app.example.com",
        ttl_seconds=1800,
        session=session,
    )

    assert raw.startswith("lt_")
    assert len(added) == 1
    assert isinstance(added[0], LinkToken)
    session.flush.assert_awaited_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_link_token_with_reconnect_fields() -> None:
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    captured: list[LinkToken] = []

    def _add(obj: object) -> None:
        if isinstance(obj, LinkToken):
            captured.append(obj)

    session.add = MagicMock(side_effect=_add)

    async def _refresh(obj: object) -> None:
        pass

    session.refresh = AsyncMock(side_effect=_refresh)

    raw, model = await create_link_token(
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri=None,
        ttl_seconds=600,
        session=session,
        connection_id=conn_id,
        locked_provider_key="google",
    )

    assert raw.startswith("lt_")
    assert len(captured) == 1
    assert captured[0].connection_id == conn_id
    assert captured[0].locked_provider_key == "google"


@pytest.mark.asyncio
async def test_create_link_token_calls_persist_callback() -> None:
    """persist_post_create callback must be invoked after flush with (model, session)."""
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    callback_args: list[tuple[object, object]] = []

    async def _persist(lt: LinkToken, s: object) -> None:
        callback_args.append((lt, s))

    async def _refresh(obj: object) -> None:
        pass

    session.refresh = AsyncMock(side_effect=_refresh)

    await create_link_token(
        end_user_id=None,
        allowed_providers=None,
        redirect_uri=None,
        ttl_seconds=300,
        session=session,
        persist_post_create=_persist,
    )

    assert len(callback_args) == 1
    lt, s = callback_args[0]
    assert isinstance(lt, LinkToken)
    assert s is session


# ---------------------------------------------------------------------------
# verify_link_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_link_token_invalid_prefix() -> None:
    session = AsyncMock()
    result = await verify_link_token("sk_notavalidtoken", session)
    assert result is None


@pytest.mark.asyncio
async def test_verify_link_token_expired() -> None:
    import bcrypt

    raw = "lt_expiredtoken1234567890abcdefgh"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    expired_model = LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id=None,
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() - timedelta(seconds=1),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )

    class _ScalarResult:
        def scalars(self) -> _ScalarResult:
            return self

        def all(self) -> list[LinkToken]:
            return [expired_model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult())

    result = await verify_link_token(raw, session)
    assert result is None


@pytest.mark.asyncio
async def test_verify_link_token_valid() -> None:
    import bcrypt

    raw = "lt_validtokenhere12345678901234"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    valid_model = LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri="https://app.example.com",
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )

    class _ScalarResult:
        def scalars(self) -> _ScalarResult:
            return self

        def all(self) -> list[LinkToken]:
            return [valid_model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult())

    result = await verify_link_token(raw, session)
    assert result is valid_model


@pytest.mark.asyncio
async def test_verify_link_token_wrong_token_fails() -> None:
    import bcrypt

    raw = "lt_correcttoken12345678901234567"
    wrong = "lt_wrongtoken123456789012345678"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=wrong[:16],
        end_user_id=None,
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )

    class _ScalarResult:
        def scalars(self) -> _ScalarResult:
            return self

        def all(self) -> list[LinkToken]:
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult())

    result = await verify_link_token(wrong, session)
    assert result is None
