"""Hosted authentication flows — user provisioning and JWT lifecycle."""

from __future__ import annotations

import logging
import secrets
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth import generate_hosted_api_key

logger = logging.getLogger(__name__)

# Module-level fallback — replaced by JWT_SECRET env var in production.
# Rotates on restart when env var is not set.
_fallback_jwt_secret: str | None = None


def get_jwt_secret(settings: object) -> str:
    """Return the JWT signing secret, generating a fallback if not configured."""
    global _fallback_jwt_secret
    jwt_secret = getattr(settings, "jwt_secret", "")
    if jwt_secret:
        return jwt_secret
    if _fallback_jwt_secret is None:
        _fallback_jwt_secret = secrets.token_hex(32)
        logger.warning(
            "JWT_SECRET is not configured — using a randomly generated secret. "
            "Dashboard sessions will be invalidated on restart. Set JWT_SECRET in production."
        )
    return _fallback_jwt_secret


def issue_jwt(user_id: uuid.UUID, tenant_id: uuid.UUID, role: str, settings: object) -> str:
    """Sign and return a dashboard session JWT."""
    import time

    import jwt

    secret = get_jwt_secret(settings)
    ttl = getattr(settings, "jwt_ttl_seconds", 86400)
    payload = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "iat": int(time.time()),
        "exp": int(time.time()) + ttl,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


async def provision_user_flow(
    workos_user_id: str,
    email: str,
    first_name: str | None,
    last_name: str | None,
    session: AsyncSession,
) -> tuple[HostedUser, Tenant, HostedMembership, HostedAPIKey | None]:
    """Look up or provision a user from a WorkOS login.

    Returns ``(user, tenant, membership, initial_api_key)``.
    ``initial_api_key`` is only non-None on the very first signup — callers
    must return the raw key to the client once and never again.
    """
    # Try lookup by WorkOS user ID first, then fall back to email.
    result = await session.execute(
        select(HostedUser).where(HostedUser.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        result = await session.execute(select(HostedUser).where(HostedUser.email == email))
        user = result.scalar_one_or_none()
        if user is not None:
            user.workos_user_id = workos_user_id
            await session.flush()

    if user is not None:
        # Existing user — find their owner membership, fall back to any membership.
        result = await session.execute(
            select(HostedMembership)
            .where(HostedMembership.user_id == user.id)
            .where(HostedMembership.role == MemberRole.OWNER)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            result = await session.execute(
                select(HostedMembership).where(HostedMembership.user_id == user.id)
            )
            membership = result.scalar_one_or_none()

        if membership is None:
            raise HTTPException(
                status_code=500,
                detail={"code": "no_membership", "message": "User has no membership"},
            )

        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )
        tenant = tenant_result.scalar_one()
        return user, tenant, membership, None

    # --- First sign-in: provision user + tenant + membership + initial API key ---
    name = " ".join(filter(None, [first_name, last_name])) or email.split("@")[0]

    user = HostedUser(id=uuid.uuid4(), email=email, name=name, workos_user_id=workos_user_id)
    session.add(user)
    await session.flush()

    tenant = Tenant(id=uuid.uuid4(), name=name, is_active=True)
    session.add(tenant)
    await session.flush()

    membership = HostedMembership(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        user_id=user.id,
        role=MemberRole.OWNER,
    )
    session.add(membership)
    await session.flush()

    raw_key, key_hash, key_prefix = generate_hosted_api_key()
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="default",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(user)
    await session.refresh(tenant)
    api_key.raw_key = raw_key  # type: ignore[attr-defined]  # transient, shown once

    logger.info("Provisioned new user %s with tenant %s", user.id, tenant.id)
    return user, tenant, membership, api_key
