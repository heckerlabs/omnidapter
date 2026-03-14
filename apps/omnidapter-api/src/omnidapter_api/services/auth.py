"""API key authentication service."""

from __future__ import annotations

import secrets
import string

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.models.api_key import APIKey
from omnidapter_api.models.organization import Organization

_API_KEY_PREFIX = "omni_sk_"
_RAW_KEY_LENGTH = 32


def generate_api_key() -> tuple[str, str, str]:
    """Generate a new API key.

    Returns:
        (raw_key, key_hash, key_prefix)
    """
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(_RAW_KEY_LENGTH))
    raw_key = f"{_API_KEY_PREFIX}{random_part}"
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
) -> tuple[APIKey, Organization] | None:
    """Authenticate an API key and return (APIKey, Organization) or None."""
    if not raw_key.startswith(_API_KEY_PREFIX):
        return None

    # Look up active keys by prefix (reduces hash comparison candidates)
    prefix = raw_key[:12]
    result = await session.execute(
        select(APIKey).where(APIKey.key_prefix == prefix).where(APIKey.is_active.is_(True))
    )
    candidates = result.scalars().all()

    for api_key in candidates:
        if verify_api_key(raw_key, api_key.key_hash):
            # Load the organization
            org_result = await session.execute(
                select(Organization).where(Organization.id == api_key.organization_id)
            )
            org = org_result.scalar_one_or_none()
            if org and org.is_active:
                return api_key, org
            return None

    return None


async def update_last_used(key_id: object, session: AsyncSession) -> None:
    """Update the last_used_at timestamp for an API key."""
    from datetime import datetime, timezone

    await session.execute(
        update(APIKey).where(APIKey.id == key_id).values(last_used_at=datetime.now(timezone.utc))
    )
    await session.commit()
