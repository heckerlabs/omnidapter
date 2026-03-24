"""Link token generation and verification."""

from __future__ import annotations

import secrets
import string
import uuid
from datetime import datetime, timezone

import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.link_token import HostedLinkToken

_RAW_TOKEN_LENGTH = 32


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
    tenant_id: uuid.UUID,
    end_user_id: str | None,
    allowed_providers: list[str] | None,
    redirect_uri: str | None,
    ttl_seconds: int,
    session: AsyncSession,
) -> tuple[str, HostedLinkToken]:
    """Create and persist a link token. Returns (raw_token, model)."""
    raw_token, token_hash, token_prefix = generate_link_token()

    now = datetime.now(timezone.utc)
    expires_at = datetime.fromtimestamp(now.timestamp() + ttl_seconds, tz=timezone.utc)

    link_token = HostedLinkToken(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        token_hash=token_hash,
        token_prefix=token_prefix,
        end_user_id=end_user_id,
        allowed_providers=allowed_providers,
        redirect_uri=redirect_uri,
        expires_at=expires_at,
        is_active=True,
    )
    session.add(link_token)
    await session.commit()
    await session.refresh(link_token)
    return raw_token, link_token


async def verify_link_token(
    raw_token: str,
    session: AsyncSession,
) -> HostedLinkToken | None:
    """Verify a raw link token and return the model if valid, None otherwise."""
    if not raw_token.startswith("lt_"):
        return None

    prefix = raw_token[:16]
    result = await session.execute(
        select(HostedLinkToken)
        .where(HostedLinkToken.token_prefix == prefix)
        .where(HostedLinkToken.is_active.is_(True))
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
