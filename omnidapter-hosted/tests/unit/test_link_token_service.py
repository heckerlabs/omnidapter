"""Unit tests for the link token service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from omnidapter_hosted.models.link_token import HostedLinkToken
from omnidapter_hosted.services.link_tokens import (
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
    # Plaintext is NOT the same as the hash
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
    tenant_id = uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    token_model = HostedLinkToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        token_hash="hash",
        token_prefix="lt_abc123456789",
        end_user_id="u1",
        allowed_providers=["google"],
        redirect_uri="https://app.example.com",
        expires_at=_now() + timedelta(seconds=1800),
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )

    async def _refresh(obj: object) -> None:
        pass  # already populated

    session.refresh = AsyncMock(side_effect=_refresh)

    with (
        patch(
            "omnidapter_hosted.services.link_tokens.generate_link_token",
            return_value=("lt_rawtoken123456789abcdefghijklmno", "hashed", "lt_rawtoken12345"),
        ),
        # Monkey-patch the HostedLinkToken constructor to return our model
        patch("omnidapter_hosted.services.link_tokens.HostedLinkToken", return_value=token_model),
    ):
        raw, model = await create_link_token(
            tenant_id=tenant_id,
            end_user_id="u1",
            allowed_providers=["google"],
            redirect_uri="https://app.example.com",
            ttl_seconds=1800,
            session=session,
        )

    assert raw.startswith("lt_")
    session.add.assert_called_once()
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_link_token_with_reconnect_fields() -> None:
    tenant_id = uuid.uuid4()
    conn_id = uuid.uuid4()
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    captured: list[HostedLinkToken] = []

    def _add(obj: object) -> None:
        if isinstance(obj, HostedLinkToken):
            captured.append(obj)

    session.add = MagicMock(side_effect=_add)

    async def _refresh(obj: object) -> None:
        pass

    session.refresh = AsyncMock(side_effect=_refresh)

    raw, model = await create_link_token(
        tenant_id=tenant_id,
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
    expired_model = HostedLinkToken(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id=None,
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() - timedelta(seconds=1),  # expired
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )

    class _ScalarResult:
        def scalars(self) -> _ScalarResult:
            return self

        def all(self) -> list[HostedLinkToken]:
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
    valid_model = HostedLinkToken(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=raw[:16],
        end_user_id="u1",
        allowed_providers=None,
        redirect_uri="https://app.example.com",
        expires_at=_now() + timedelta(seconds=1800),  # valid
        is_active=True,
        connection_id=None,
        locked_provider_key=None,
    )

    class _ScalarResult:
        def scalars(self) -> _ScalarResult:
            return self

        def all(self) -> list[HostedLinkToken]:
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
    model = HostedLinkToken(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        token_hash=hashed,
        token_prefix=wrong[:16],  # same prefix as wrong token for this test
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

        def all(self) -> list[HostedLinkToken]:
            return [model]

    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarResult())

    result = await verify_link_token(wrong, session)
    assert result is None
