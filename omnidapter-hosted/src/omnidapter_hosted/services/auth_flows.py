"""Hosted authentication flows — user provisioning and JWT lifecycle."""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser

logger = logging.getLogger(__name__)

# Hardcoded fallback secret for development — keeps sessions valid across restarts.
# MUST be overridden in production via JWT_SECRET environment variable.
_DEV_FALLBACK_JWT_SECRET = "dev-key-do-not-use-in-production-keep-sessions-alive-12345"


def get_jwt_secret(settings: object) -> str:
    """Return the JWT signing secret.

    In production, JWT_SECRET must be explicitly set (enforced by HostedSettings validator).
    In development, falls back to a hardcoded secret so sessions persist across server restarts.
    """
    jwt_secret = getattr(settings, "jwt_secret", "").strip()
    if jwt_secret:
        return jwt_secret

    # Check environment — DEV/LOCAL use hardcoded fallback, PROD should not reach here
    env = getattr(settings, "omnidapter_env", "PROD")
    if env in ("DEV", "LOCAL"):
        logger.debug("Using hardcoded JWT secret for development — sessions survive restarts")
        return _DEV_FALLBACK_JWT_SECRET

    # This should not happen in PROD due to config validation, but fail explicitly
    raise RuntimeError("JWT_SECRET is required in production")


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
) -> tuple[HostedUser, Tenant, HostedMembership]:
    """Look up or provision a user from a WorkOS login.

    Returns ``(user, tenant, membership)``.
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
        return user, tenant, membership

    # --- First sign-in: provision user + tenant + membership ---
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

    await session.commit()
    await session.refresh(user)
    await session.refresh(tenant)

    logger.info("Provisioned new user %s with tenant %s", user.id, tenant.id)
    return user, tenant, membership
