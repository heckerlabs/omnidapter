"""API key authentication service."""

from __future__ import annotations

import secrets
import string

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.models.api_key import APIKey

_API_KEY_PREFIX = "omni_sk_"
_RAW_KEY_LENGTH = 32


def generate_api_key(is_test: bool = False) -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, key_hash, key_prefix)
    """
    prefix = "omni_test_" if is_test else "omni_live_"
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(_RAW_KEY_LENGTH))
    raw_key = f"{prefix}{random_part}"
    key_prefix = raw_key[:12]
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    return raw_key, key_hash, key_prefix


def verify_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify a raw API key against its stored hash."""
    try:
        return bcrypt.checkpw(raw_key.encode(), key_hash.encode())
    except Exception:
        return False


async def authenticate_api_key(
    raw_key: str,
    session: AsyncSession,
) -> APIKey | None:
    """Authenticate an API key and return the APIKey or None."""
    if not (raw_key.startswith("omni_live_") or raw_key.startswith("omni_test_")):
        return None

    prefix = raw_key[:12]
    result = await session.execute(
        select(APIKey).where(APIKey.key_prefix == prefix).where(APIKey.is_active.is_(True))
    )
    candidates = result.scalars().all()

    for api_key in candidates:
        if verify_api_key(raw_key, api_key.key_hash):
            return api_key

    return None


async def update_last_used(key_id: object, session: AsyncSession) -> None:
    """Update the last_used_at timestamp for an API key."""
    from datetime import datetime, timezone

    await session.execute(
        update(APIKey).where(APIKey.id == key_id).values(last_used_at=datetime.now(timezone.utc))
    )
    await session.commit()
