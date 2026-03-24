"""Hosted API key authentication — resolves tenant_id from hosted API key."""

from __future__ import annotations

import secrets
import string

import bcrypt
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.tenant import Tenant

_RAW_KEY_LENGTH = 32


def generate_hosted_api_key() -> tuple[str, str, str]:
    """Generate a new hosted API key.

    Returns:
        (raw_key, key_hash, key_prefix)
    """
    prefix = "omni_"
    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(_RAW_KEY_LENGTH))
    raw_key = f"{prefix}{random_part}"
    key_prefix = raw_key[:12]
    key_hash = bcrypt.hashpw(raw_key.encode(), bcrypt.gensalt()).decode()
    return raw_key, key_hash, key_prefix


def verify_hosted_api_key(raw_key: str, key_hash: str) -> bool:
    """Verify a raw hosted API key against its stored hash."""
    try:
        return bcrypt.checkpw(raw_key.encode(), key_hash.encode())
    except Exception:
        return False


async def authenticate_hosted_key(
    raw_key: str,
    session: AsyncSession,
) -> tuple[HostedAPIKey, Tenant] | None:
    """Authenticate a hosted API key and return (HostedAPIKey, Tenant) or None."""
    if not raw_key.startswith("omni_"):
        return None

    prefix = raw_key[:12]
    result = await session.execute(
        select(HostedAPIKey)
        .where(HostedAPIKey.key_prefix == prefix)
        .where(HostedAPIKey.is_active.is_(True))
    )
    candidates = result.scalars().all()

    for api_key in candidates:
        if verify_hosted_api_key(raw_key, api_key.key_hash):
            tenant_result = await session.execute(
                select(Tenant).where(Tenant.id == api_key.tenant_id)
            )
            tenant = tenant_result.scalar_one_or_none()
            if tenant and tenant.is_active:
                return api_key, tenant
            return None

    return None


async def update_key_last_used(key_id: object, session: AsyncSession) -> None:
    from datetime import datetime, timezone

    await session.execute(
        update(HostedAPIKey)
        .where(HostedAPIKey.id == key_id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await session.commit()
