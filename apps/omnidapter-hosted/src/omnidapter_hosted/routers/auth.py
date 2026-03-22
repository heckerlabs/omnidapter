"""WorkOS AuthKit endpoints — login, callback, session refresh, logout, and /me."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from omnidapter_server.database import get_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from workos import AsyncWorkOSClient
from workos.types.user_management.session import SessionConfig

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import get_request_id
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth import generate_hosted_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

_COOKIE_NAME = "wos_session"
_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


def _workos_client(settings: HostedSettings) -> AsyncWorkOSClient:
    return AsyncWorkOSClient(
        api_key=settings.workos_api_key,
        client_id=settings.workos_client_id,
    )


def _require_workos(settings: HostedSettings) -> None:
    if not settings.workos_api_key or not settings.workos_client_id:
        raise HTTPException(
            status_code=503,
            detail={"code": "workos_not_configured", "message": "WorkOS is not configured"},
        )
    if not settings.workos_cookie_password or len(settings.workos_cookie_password) < 32:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "workos_not_configured",
                "message": "WORKOS_COOKIE_PASSWORD must be at least 32 characters",
            },
        )


async def _get_or_provision_user(
    workos_user_id: str,
    email: str,
    first_name: str | None,
    last_name: str | None,
    session: AsyncSession,
) -> tuple[HostedUser, Tenant, HostedAPIKey | None]:
    """Return (user, tenant, initial_api_key).

    initial_api_key is only non-None on the very first signup — callers should
    return the raw key to the user once and never again.
    """
    # Look up existing user by workos_user_id first, then fall back to email.
    result = await session.execute(
        select(HostedUser).where(HostedUser.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()

    if user is None:
        # Could be a user created before WorkOS was added — match by email.
        result = await session.execute(
            select(HostedUser).where(HostedUser.email == email)
        )
        user = result.scalar_one_or_none()
        if user is not None:
            user.workos_user_id = workos_user_id
            await session.flush()

    if user is not None:
        # Existing user — look up their owner membership to find the tenant.
        result = await session.execute(
            select(HostedMembership)
            .where(HostedMembership.user_id == user.id)
            .where(HostedMembership.role == MemberRole.OWNER)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            # Shouldn't happen, but pick any membership.
            result = await session.execute(
                select(HostedMembership).where(HostedMembership.user_id == user.id)
            )
            membership = result.scalar_one_or_none()

        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )
        tenant = tenant_result.scalar_one()
        return user, tenant, None

    # --- First sign-in: provision user + tenant + membership + initial API key ---
    name = " ".join(filter(None, [first_name, last_name])) or email.split("@")[0]

    user = HostedUser(
        id=uuid.uuid4(),
        email=email,
        name=name,
        workos_user_id=workos_user_id,
    )
    session.add(user)
    await session.flush()

    tenant = Tenant(
        id=uuid.uuid4(),
        name=name,
        is_active=True,
    )
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

    raw_key, key_hash, key_prefix = generate_hosted_api_key(is_test=False)
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="default",
        key_hash=key_hash,
        key_prefix=key_prefix,
        is_active=True,
        is_test=False,
    )
    session.add(api_key)
    await session.commit()
    await session.refresh(user)
    await session.refresh(tenant)
    api_key.raw_key = raw_key  # type: ignore[attr-defined]  # transient attribute

    logger.info("Provisioned new user %s with tenant %s", user.id, tenant.id)
    return user, tenant, api_key


@router.get("/login")
async def login(
    redirect_uri: str | None = None,
    settings: HostedSettings = Depends(get_hosted_settings),
):
    """Return the WorkOS AuthKit authorization URL.

    The client should redirect the user's browser to the returned URL.
    """
    _require_workos(settings)
    client = _workos_client(settings)
    callback_uri = redirect_uri or f"{settings.omnidapter_base_url}/auth/callback"
    url = await client.user_management.get_authorization_url(
        redirect_uri=callback_uri,
        provider="authkit",
    )
    return {"url": url}


@router.get("/callback")
async def callback(
    code: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Exchange the WorkOS authorization code for a sealed session cookie.

    On first login the response also includes the raw API key (shown once).
    """
    _require_workos(settings)
    client = _workos_client(settings)

    auth_response = await client.user_management.authenticate_with_code(
        code=code,
        session=SessionConfig(
            seal_session=True,
            cookie_password=settings.workos_cookie_password,
        ),
    )

    wu = auth_response.user
    user, tenant, initial_key = await _get_or_provision_user(
        workos_user_id=wu.id,
        email=wu.email,
        first_name=wu.first_name,
        last_name=wu.last_name,
        session=session,
    )

    data: dict = {
        "user": {
            "id": str(user.id),
            "email": user.email,
            "name": user.name,
        },
        "tenant": {
            "id": str(tenant.id),
            "name": tenant.name,
            "plan": tenant.plan,
        },
    }
    if initial_key is not None:
        data["initial_api_key"] = getattr(initial_key, "raw_key", None)

    response = JSONResponse(
        content={"data": data, "meta": {"request_id": request_id}},
        status_code=200,
    )
    response.set_cookie(
        key=_COOKIE_NAME,
        value=auth_response.sealed_session,
        httponly=True,
        secure=settings.omnidapter_env == "production",
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
    )
    return response


@router.get("/me")
async def me(
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
    wos_session: str | None = Cookie(default=None),
):
    """Return the currently authenticated user and their tenant.

    Automatically refreshes an expired session and rotates the cookie.
    """
    _require_workos(settings)
    if not wos_session:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "No session cookie"},
        )

    client = _workos_client(settings)
    ws = client.user_management.load_sealed_session(
        sealed_session=wos_session,
        cookie_password=settings.workos_cookie_password,
    )

    auth = await ws.authenticate()

    new_sealed: str | None = None
    if not auth.authenticated:
        # Try to refresh.
        refresh = await ws.refresh(cookie_password=settings.workos_cookie_password)
        if not refresh.authenticated:
            raise HTTPException(
                status_code=401,
                detail={"code": "session_expired", "message": "Session expired — please log in again"},
            )
        new_sealed = refresh.sealed_session
        # Re-authenticate with the freshly sealed session to get the user.
        ws2 = client.user_management.load_sealed_session(
            sealed_session=new_sealed,
            cookie_password=settings.workos_cookie_password,
        )
        auth = await ws2.authenticate()
        if not auth.authenticated:
            raise HTTPException(
                status_code=401,
                detail={"code": "session_expired", "message": "Session expired — please log in again"},
            )

    workos_user_id = auth.user.id
    result = await session.execute(
        select(HostedUser).where(HostedUser.workos_user_id == workos_user_id)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "user_not_found", "message": "User not found in database"},
        )

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

    tenant = None
    if membership:
        tenant_result = await session.execute(
            select(Tenant).where(Tenant.id == membership.tenant_id)
        )
        tenant = tenant_result.scalar_one_or_none()

    response_data: dict = {
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "tenant": (
            {"id": str(tenant.id), "name": tenant.name, "plan": tenant.plan}
            if tenant
            else None
        ),
    }

    response = JSONResponse(
        content={"data": response_data, "meta": {"request_id": request_id}},
        status_code=200,
    )
    if new_sealed:
        response.set_cookie(
            key=_COOKIE_NAME,
            value=new_sealed,
            httponly=True,
            secure=settings.omnidapter_env == "production",
            samesite="lax",
            max_age=_COOKIE_MAX_AGE,
        )
    return response


@router.post("/logout")
async def logout(request_id: str = Depends(get_request_id)):
    """Clear the session cookie."""
    response = JSONResponse(
        content={"data": {"logged_out": True}, "meta": {"request_id": request_id}},
        status_code=200,
    )
    response.delete_cookie(key=_COOKIE_NAME)
    return response
