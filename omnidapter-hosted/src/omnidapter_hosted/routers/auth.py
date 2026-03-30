"""WorkOS AuthKit endpoints — login, callback, me, and logout."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from omnidapter_server.database import get_session
from sqlalchemy.ext.asyncio import AsyncSession
from workos import AsyncWorkOSClient

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    DashboardAuthContext,
    get_dashboard_auth_context,
    get_request_id,
)
from omnidapter_hosted.services.auth_flows import issue_jwt, provision_user_flow

router = APIRouter(prefix="/auth", tags=["auth"])


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


@router.get("/login")
async def login(
    redirect_uri: str | None = None,
    settings: HostedSettings = Depends(get_hosted_settings),
):
    """Return the WorkOS AuthKit authorization URL."""
    _require_workos(settings)
    client = _workos_client(settings)
    callback_uri = redirect_uri or f"{settings.omnidapter_base_url}/v1/auth/callback"
    url = client.user_management.get_authorization_url(
        redirect_uri=callback_uri,
        provider="authkit",
    )
    return {"url": url}


@router.get("/callback")
async def callback(
    code: str,
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Exchange the WorkOS authorization code for a JWT access token.

    Returns the raw API key only on first signup.
    """
    _require_workos(settings)
    client = _workos_client(settings)

    auth_response = await client.user_management.authenticate_with_code(code=code)
    wu = auth_response.user

    user, tenant, membership, initial_key = await provision_user_flow(
        workos_user_id=wu.id,
        email=wu.email,
        first_name=wu.first_name,
        last_name=wu.last_name,
        session=session,
    )

    access_token = issue_jwt(user.id, tenant.id, membership.role, settings)

    data: dict = {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {"id": str(user.id), "email": user.email, "name": user.name},
        "tenant": {"id": str(tenant.id), "name": tenant.name, "plan": tenant.plan},
    }
    if initial_key is not None:
        data["api_key"] = getattr(initial_key, "raw_key", None)

    return {"data": data, "meta": {"request_id": request_id}}


@router.get("/me")
async def me(
    auth: DashboardAuthContext = Depends(get_dashboard_auth_context),
    request_id: str = Depends(get_request_id),
):
    """Return the currently authenticated user and tenant."""
    return {
        "data": {
            "user": {"id": str(auth.user.id), "email": auth.user.email, "name": auth.user.name},
            "tenant": {
                "id": str(auth.tenant.id),
                "name": auth.tenant.name,
                "plan": auth.tenant.plan,
            },
            "role": auth.membership.role,
        },
        "meta": {"request_id": request_id},
    }
