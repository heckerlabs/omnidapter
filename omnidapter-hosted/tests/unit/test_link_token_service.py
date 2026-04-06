"""Unit tests for the hosted link token service wrapper."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from omnidapter_hosted.models.link_token_owner import HostedLinkTokenOwner
from omnidapter_hosted.services.link_tokens import (
    create_link_token,
    generate_link_token,
    verify_link_token,
)
from omnidapter_server.models.link_token import LinkToken


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# generate_link_token (re-exported from server — basic sanity checks)
# ---------------------------------------------------------------------------


def test_generate_link_token_format() -> None:
    raw, hashed, prefix = generate_link_token()
    assert raw.startswith("lt_")
    assert len(raw) == 35  # "lt_" + 32 chars
    assert prefix == raw[:16]
    assert hashed != raw


def test_generate_link_token_is_random() -> None:
    token1, _, _ = generate_link_token()
    token2, _, _ = generate_link_token()
    assert token1 != token2


# ---------------------------------------------------------------------------
# create_link_token (hosted wrapper)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_link_token_creates_companion_owner() -> None:
    """Hosted create_link_token must add a HostedLinkTokenOwner companion row."""
    tenant_id = uuid.uuid4()
    token_id = uuid.uuid4()

    server_token = LinkToken(
        id=token_id,
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

    captured_owners: list[HostedLinkTokenOwner] = []
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()

    def _add(obj: object) -> None:
        if isinstance(obj, HostedLinkTokenOwner):
            captured_owners.append(obj)

    session.add = MagicMock(side_effect=_add)
    session.refresh = AsyncMock()

    with patch(
        "omnidapter_hosted.services.link_tokens._server_create_link_token",
        new=AsyncMock(return_value=("lt_rawtoken", server_token)),
    ) as mock_server_create:
        raw, model = await create_link_token(
            tenant_id=tenant_id,
            end_user_id="u1",
            allowed_providers=["google"],
            redirect_uri="https://app.example.com",
            ttl_seconds=1800,
            session=session,
        )

    assert raw == "lt_rawtoken"
    assert model is server_token

    # Verify that server create was called with a persist_post_create callback
    mock_server_create.assert_awaited_once()
    call_kwargs = mock_server_create.call_args.kwargs
    assert "persist_post_create" in call_kwargs
    assert call_kwargs["persist_post_create"] is not None


@pytest.mark.asyncio
async def test_create_link_token_with_reconnect_fields() -> None:
    tenant_id = uuid.uuid4()
    conn_id = uuid.uuid4()

    server_token = LinkToken(
        id=uuid.uuid4(),
        token_hash="hash",
        token_prefix="lt_abc123456789",
        end_user_id=None,
        allowed_providers=None,
        redirect_uri=None,
        expires_at=_now() + timedelta(seconds=600),
        is_active=True,
        connection_id=conn_id,
        locked_provider_key="google",
    )

    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()
    session.refresh = AsyncMock()

    with patch(
        "omnidapter_hosted.services.link_tokens._server_create_link_token",
        new=AsyncMock(return_value=("lt_reconnect", server_token)),
    ) as mock_server_create:
        raw, model = await create_link_token(
            tenant_id=tenant_id,
            end_user_id=None,
            allowed_providers=None,
            redirect_uri=None,
            ttl_seconds=600,
            session=session,
            connection_id=conn_id,
            locked_provider_key="google",
        )

    assert raw == "lt_reconnect"
    call_kwargs = mock_server_create.call_args.kwargs
    assert call_kwargs["connection_id"] == conn_id
    assert call_kwargs["locked_provider_key"] == "google"


# ---------------------------------------------------------------------------
# verify_link_token (re-exported from server)
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
