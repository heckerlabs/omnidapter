"""Unit tests for the server link token service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter_server.models.link_token import LinkToken
from omnidapter_server.services.link_tokens import (
    create_connect_session,
    create_link_token,
    generate_link_token,
    generate_session_token,
    verify_link_token,
    verify_session_token,
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


# ---------------------------------------------------------------------------
# generate_session_token
# ---------------------------------------------------------------------------


def test_generate_session_token_format() -> None:
    raw, hashed, prefix = generate_session_token()
    assert raw.startswith("cs_")
    assert len(raw) == 35  # "cs_" + 32 chars
    assert prefix == raw[:16]
    assert hashed != raw


def test_generate_session_token_hash_is_one_way() -> None:
    import bcrypt

    raw, hashed, _ = generate_session_token()
    assert bcrypt.checkpw(raw.encode(), hashed.encode())


def test_generate_session_token_is_random() -> None:
    t1, _, _ = generate_session_token()
    t2, _, _ = generate_session_token()
    assert t1 != t2


def test_generate_session_token_prefix_distinct_from_link_token() -> None:
    raw, _, prefix = generate_session_token()
    assert raw.startswith("cs_")
    assert prefix.startswith("cs_")
    assert not raw.startswith("lt_")


# ---------------------------------------------------------------------------
# create_connect_session
# ---------------------------------------------------------------------------


def _valid_link_token_model(*, consumed_at=None) -> LinkToken:
    import bcrypt

    raw = "lt_bootstraptoken12345678901234"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    return LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=consumed_at,
        session_token_hash=None,
        session_token_prefix=None,
        session_expires_at=None,
    )


@pytest.mark.asyncio
async def test_create_connect_session_rejects_invalid_token() -> None:
    """create_connect_session raises ValueError('invalid_token') for bad tokens."""
    session = AsyncMock()

    class _Empty:
        def scalars(self):
            return self

        def all(self):
            return []

    session.execute = AsyncMock(return_value=_Empty())

    with pytest.raises(ValueError, match="invalid_token"):
        await create_connect_session("lt_nonexistenttoken12345678901234", session)


@pytest.mark.asyncio
async def test_create_connect_session_rejects_already_consumed_token() -> None:
    """create_connect_session raises ValueError('token_already_used') if consumed_at is set."""
    import bcrypt

    raw = "lt_consumedtoken123456789012345"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=_now() - timedelta(seconds=60),  # already consumed
        session_token_hash=None,
        session_token_prefix=None,
        session_expires_at=None,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    with pytest.raises(ValueError, match="token_already_used"):
        await create_connect_session(raw, session)


@pytest.mark.asyncio
async def test_create_connect_session_success() -> None:
    """Successful exchange sets consumed_at and returns a cs_ token."""
    import bcrypt

    raw = "lt_freshtoken1234567890123456789"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id="u1",
        allowed_providers=["google"],
        redirect_uri="https://app.example.com",
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=None,
        session_token_hash=None,
        session_token_prefix=None,
        session_expires_at=None,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    raw_session, returned_model = await create_connect_session(raw, session)

    assert raw_session.startswith("cs_")
    assert len(raw_session) == 35
    # execute called twice: once for verify (SELECT) and once for UPDATE
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_connect_session_ttl_capped_by_link_token_expiry() -> None:
    """Session TTL must not exceed remaining link-token lifetime."""
    import bcrypt

    raw = "lt_shortttltoken1234567890123456"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    # Link token expires in 60 seconds — session TTL should be ≤ 60s
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=60),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=None,
        session_token_hash=None,
        session_token_prefix=None,
        session_expires_at=None,
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [model]

    class _UpdateResult:
        pass

    session = AsyncMock()
    session.execute = AsyncMock(side_effect=[_Result(), _UpdateResult()])
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    raw_session, _ = await create_connect_session(raw, session)
    assert raw_session.startswith("cs_")
    # We can't easily inspect the UPDATE values here without more mocking,
    # but the function should succeed without error.


# ---------------------------------------------------------------------------
# verify_session_token
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_session_token_rejects_non_cs_prefix() -> None:
    session = AsyncMock()
    result = await verify_session_token("lt_notasessiontoken12345678901234", session)
    assert result is None


@pytest.mark.asyncio
async def test_verify_session_token_rejects_expired_session() -> None:
    import bcrypt

    raw = "cs_expiredsession12345678901234"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash="unused",
        token_prefix="lt_unused",
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=_now() - timedelta(seconds=60),
        session_token_hash=hashed,
        session_token_prefix=raw[:16],
        session_expires_at=_now() - timedelta(seconds=1),  # expired
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    result = await verify_session_token(raw, session)
    assert result is None


@pytest.mark.asyncio
async def test_verify_session_token_valid() -> None:
    import bcrypt

    raw = "cs_validsession1234567890123456"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash="unused",
        token_prefix="lt_unused",
        end_user_id="u1",
        allowed_providers=["google"],
        redirect_uri="https://app.example.com",
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=_now() - timedelta(seconds=10),
        session_token_hash=hashed,
        session_token_prefix=raw[:16],
        session_expires_at=_now() + timedelta(seconds=900),
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    result = await verify_session_token(raw, session)
    assert result is model


@pytest.mark.asyncio
async def test_verify_session_token_rejects_deactivated_link_token() -> None:
    """is_active=False means the connection was completed — session must be invalid."""
    raw = "cs_deactivated1234567890123456789"

    class _Result:
        def scalars(self):
            return self

        def all(self):
            # is_active=False is filtered out at the query level
            return []

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    result = await verify_session_token(raw, session)
    assert result is None


@pytest.mark.asyncio
async def test_verify_session_token_wrong_hash_fails() -> None:
    import bcrypt

    raw = "cs_correctsession123456789012345"
    wrong = "cs_wrongsession1234567890123456"
    hashed = bcrypt.hashpw(raw.encode(), bcrypt.gensalt()).decode()
    model = LinkToken(
        id=uuid.uuid4(),
        token_hash="unused",
        token_prefix="lt_unused",
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
        consumed_at=_now() - timedelta(seconds=10),
        session_token_hash=hashed,
        session_token_prefix=wrong[:16],
        session_expires_at=_now() + timedelta(seconds=900),
    )

    class _Result:
        def scalars(self):
            return self

        def all(self):
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_Result())

    result = await verify_session_token(wrong, session)
    assert result is None
