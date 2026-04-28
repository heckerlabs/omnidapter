"""Link token generation and verification."""

from __future__ import annotations

import secrets
import string
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.models.link_token import LinkToken

_RAW_TOKEN_LENGTH = 32

LinkTokenPostCreate = Callable[[LinkToken, AsyncSession], Awaitable[None]]


def generate_link_token() -> tuple[str, str, str]:
    """Generate a new link token.

    Returns:
        (raw_token, token_hash, token_prefix)
    """
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(_RAW_TOKEN_LENGTH))
    raw_token = f"lt_{random_part}"
    token_prefix = raw_token[:16]
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    return raw_token, token_hash, token_prefix


async def create_link_token(
    end_user_id: str | None,
    allowed_providers: list[str] | None,
    redirect_uri: str | None,
    ttl_seconds: int,
    session: AsyncSession,
    *,
    connection_id: uuid.UUID | None = None,
    locked_provider_key: str | None = None,
    services: list[str] | None = None,
    persist_post_create: LinkTokenPostCreate | None = None,
) -> tuple[str, LinkToken]:
    """Create and persist a link token. Returns (raw_token, model).

    When ``connection_id`` is provided the token is a *reconnect* token — it is
    locked to a single existing connection so the connect UI can skip provider
    selection and go straight to the authorization flow.

    The optional ``persist_post_create`` callback is invoked after the token is
    flushed to the DB (same pattern as ``connection_flows.persist_post_create``).
    Hosted uses this to create the companion ``HostedLinkTokenOwner`` row.
    """
    raw_token, token_hash, token_prefix = generate_link_token()

    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

    link_token = LinkToken(
        id=uuid.uuid4(),
        token_hash=token_hash,
        token_prefix=token_prefix,
        end_user_id=end_user_id,
        allowed_providers=allowed_providers,
        redirect_uri=redirect_uri,
        expires_at=expires_at,
        is_active=True,
        connection_id=connection_id,
        locked_provider_key=locked_provider_key,
        services=services,
    )
    session.add(link_token)
    await session.flush()

    if persist_post_create is not None:
        await persist_post_create(link_token, session)

    await session.commit()
    await session.refresh(link_token)
    return raw_token, link_token


async def verify_link_token(
    raw_token: str,
    session: AsyncSession,
) -> LinkToken | None:
    """Verify a raw link token and return the model if valid, None otherwise."""
    if not raw_token.startswith("lt_"):
        return None

    prefix = raw_token[:16]
    result = await session.execute(
        select(LinkToken)
        .where(LinkToken.token_prefix == prefix)
        .where(LinkToken.is_active.is_(True))
    )
    candidates = result.scalars().all()

    now = datetime.now(timezone.utc)
    for link_token in candidates:
        if link_token.expires_at < now:
            continue
        try:
            if bcrypt.checkpw(raw_token.encode(), link_token.token_hash.encode()):
                return link_token
        except Exception:
            continue

    return None


async def deactivate_link_token(token_id: uuid.UUID, session: AsyncSession) -> None:
    """Mark a link token as inactive (consumed)."""
    await session.execute(update(LinkToken).where(LinkToken.id == token_id).values(is_active=False))
    await session.commit()


# ---------------------------------------------------------------------------
# Session token (cs_*) — issued in exchange for a bootstrap lt_ token
# ---------------------------------------------------------------------------

_SESSION_TOKEN_TTL_SECONDS = 900  # 15 minutes


def generate_session_token() -> tuple[str, str, str]:
    """Generate a connect session token.

    Returns:
        (raw_token, token_hash, token_prefix)

    The ``cs_`` prefix distinguishes session tokens from bootstrap ``lt_`` tokens
    so that each can only be used in its designated slot.
    """
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(_RAW_TOKEN_LENGTH))
    raw_token = f"cs_{random_part}"
    token_prefix = raw_token[:16]
    token_hash = bcrypt.hashpw(raw_token.encode(), bcrypt.gensalt()).decode()
    return raw_token, token_hash, token_prefix


async def create_connect_session(
    raw_bootstrap_token: str,
    session: AsyncSession,
) -> tuple[str, LinkToken]:
    """Exchange a bootstrap lt_ token for a short-lived cs_ session token.

    This is the server-side half of the one-time exchange flow:

    1. Verify the bootstrap token is valid and not yet consumed.
    2. Mark it as consumed (``consumed_at`` is set — irreversible).
    3. Generate a fresh ``cs_`` session token.
    4. Store the session token hash + prefix + expiry on the ``LinkToken`` record.
    5. Return ``(raw_session_token, link_token)``.

    Raises ``ValueError`` with a descriptive message on any failure so callers
    can map it to the appropriate HTTP response.
    """
    link_token = await verify_link_token(raw_bootstrap_token, session)
    if link_token is None:
        raise ValueError("invalid_token")

    if link_token.consumed_at is not None:
        raise ValueError("token_already_used")

    raw_session, session_hash, session_prefix = generate_session_token()
    now = datetime.now(timezone.utc)
    # Session TTL is capped by the remaining link-token lifetime so a session
    # can never outlive its parent bootstrap token's original intent.
    remaining = (link_token.expires_at - now).total_seconds()
    session_ttl = min(_SESSION_TOKEN_TTL_SECONDS, max(0, remaining))
    session_expires_at = datetime.fromtimestamp(now.timestamp() + session_ttl, tz=timezone.utc)

    await session.execute(
        update(LinkToken)
        .where(LinkToken.id == link_token.id)
        .values(
            consumed_at=now,
            session_token_hash=session_hash,
            session_token_prefix=session_prefix,
            session_expires_at=session_expires_at,
        )
    )
    await session.commit()
    await session.refresh(link_token)
    return raw_session, link_token


async def verify_session_token(
    raw_token: str,
    session: AsyncSession,
) -> LinkToken | None:
    """Verify a cs_ session token and return the parent LinkToken if valid.

    Checks:
    - ``cs_`` prefix
    - Prefix lookup against ``session_token_prefix``
    - bcrypt hash match against ``session_token_hash``
    - ``session_expires_at`` not in the past
    - ``is_active`` still True (link token not deactivated by connection creation)
    """
    if not raw_token.startswith("cs_"):
        return None

    prefix = raw_token[:16]
    result = await session.execute(
        select(LinkToken)
        .where(LinkToken.session_token_prefix == prefix)
        .where(LinkToken.is_active.is_(True))
    )
    candidates = result.scalars().all()

    now = datetime.now(timezone.utc)
    for link_token in candidates:
        if link_token.session_expires_at is None or link_token.session_expires_at < now:
            continue
        if link_token.session_token_hash is None:
            continue
        try:
            if bcrypt.checkpw(raw_token.encode(), link_token.session_token_hash.encode()):
                return link_token
        except Exception:
            continue

    return None
