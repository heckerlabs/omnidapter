"""Connect UI endpoints — authenticated via link token (lt_*).

These routes are the only surface available to end-users connecting their
calendars. They are intentionally narrow: list available providers and
initiate a connection (OAuth redirect or inline credentials).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from omnidapter import Omnidapter
from omnidapter.core.registry import ProviderRegistry
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.schemas.connection import (
    CreateConnectionRequest,
    ReauthorizeConnectionRequest,
)
from omnidapter_server.services.connection_flows import (
    create_connection_flow,
    reauthorize_connection_flow,
)
from omnidapter_server.services.link_tokens import (
    _SESSION_TOKEN_TTL_SECONDS,
    create_connect_session,
    deactivate_link_token,
    verify_link_token,
)
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import (
    LinkTokenContext,
    get_encryption_service,
    get_link_token_context,
    get_request_id,
)
from omnidapter_hosted.models.connection_owner import HostedConnectionOwner
from omnidapter_hosted.models.link_token_owner import HostedLinkTokenOwner
from omnidapter_hosted.services.connect import (
    create_credential_connection,
    is_provider_available,
    list_available_providers,
    update_credential_connection,
)
from omnidapter_hosted.services.provider_registry import build_hosted_provider_registry
from omnidapter_hosted.services.tenant_resources import (
    enforce_fallback_connection_limit,
    get_tenant_provider_config,
)

router = APIRouter(prefix="/connect", tags=["connect"])


def _metadata_omni() -> Omnidapter:
    """Omnidapter instance used only for provider metadata (listing, describing).

    Registers all built-in providers regardless of whether server-level OAuth
    credentials are present, so tenant-configured providers are never invisible.
    Availability filtering is done separately via ``is_provider_available()``.
    """
    registry = ProviderRegistry()
    registry.register_builtins(auto_register_by_env=False)
    return Omnidapter(registry=registry)


# ---------------------------------------------------------------------------
# Request/response schemas specific to the connect UI
# ---------------------------------------------------------------------------


class ConnectCreateConnectionRequest(BaseModel):
    """Request body for POST /connect/connections."""

    provider_key: str
    external_id: str | None = None
    scopes: list[str] | None = None
    redirect_uri: str | None = None  # overrides token's redirect_uri if provided
    credentials: dict[str, str] | None = None  # for non-OAuth providers


class ConnectCreateConnectionResponse(BaseModel):
    connection_id: str
    status: str
    authorization_url: str | None


class ConnectSessionRequest(BaseModel):
    """Bootstrap token submitted in the request body — never in the URL."""

    token: str


class ConnectSessionResponse(BaseModel):
    session_token: str
    expires_in: int
    redirect_uri: str | None


# ---------------------------------------------------------------------------
# POST /connect/session — one-time bootstrap token exchange
# ---------------------------------------------------------------------------


@router.post("/session", status_code=200)
async def create_session(
    body: ConnectSessionRequest,
    request_id: str = Depends(get_request_id),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Exchange a one-time bootstrap link token (lt_*) for a short-lived session token (cs_*).

    The bootstrap token is consumed immediately and permanently on first call.
    Subsequent calls with the same token return ``token_already_used``.

    This endpoint requires **no** Authorization header.  The bootstrap token is
    passed in the request body so it never appears in server logs or the
    browser's address bar after the initial page load.

    The hosted version additionally verifies that the bootstrap token belongs to
    a known tenant before issuing the session token.
    """
    # Pre-flight: verify the token belongs to a known hosted tenant.
    # We do this before consuming it so bad tokens don't pollute consumed_at.
    raw_token = body.token
    link_token_check = await verify_link_token(raw_token, session)
    if link_token_check is not None:
        owner_result = await session.execute(
            select(HostedLinkTokenOwner).where(
                HostedLinkTokenOwner.link_token_id == link_token_check.id
            )
        )
        if owner_result.scalar_one_or_none() is None:
            link_token_check = None  # treat as invalid — no tenant ownership

    if link_token_check is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Invalid or expired link token"},
        )

    try:
        raw_session, link_token = await create_connect_session(raw_token, session)
    except ValueError as exc:
        code = str(exc)
        if code == "token_already_used":
            raise HTTPException(
                status_code=401,
                detail={
                    "code": "token_already_used",
                    "message": "This link has already been opened. Please request a new one.",
                },
            ) from exc
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Invalid or expired link token"},
        ) from exc

    return {
        "data": ConnectSessionResponse(
            session_token=raw_session,
            expires_in=_SESSION_TOKEN_TTL_SECONDS,
            redirect_uri=link_token.redirect_uri,
        ),
        "meta": {"request_id": request_id},
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: HostedSettings,
    tenant_id: uuid.UUID,
    provider_key: str,
    provider_config: object | None,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = await build_hosted_provider_registry(
        tenant_id=tenant_id,
        provider_key=provider_key,
        session=session,
        settings=settings,
        encryption=encryption,
    )
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
    )


async def _persist_owner(conn: Connection, session: AsyncSession, tenant_id: uuid.UUID) -> None:
    session.add(
        HostedConnectionOwner(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            connection_id=conn.id,
        )
    )


async def _count_active_connections(
    provider_key: str,
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> int:
    from omnidapter_server.models.connection import ConnectionStatus

    result = await session.execute(
        select(func.count())
        .select_from(Connection)
        .join(HostedConnectionOwner, HostedConnectionOwner.connection_id == Connection.id)
        .where(
            HostedConnectionOwner.tenant_id == tenant_id,
            Connection.provider_key == provider_key,
            Connection.status != ConnectionStatus.REVOKED,
        )
    )
    return int(result.scalar_one())


# ---------------------------------------------------------------------------
# GET /connect/providers
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_providers(
    link_token: Annotated[LinkTokenContext, Depends(get_link_token_context)],
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
    session: AsyncSession = Depends(get_session),
):
    """List providers available for this connect session.

    - Filters by ``allowed_providers`` on the link token (if set).
    - Respects each provider's ``is_enabled`` flag per tenant.
    - Returns only the locked provider for reconnect tokens.
    - Includes ``credential_schema`` for non-OAuth providers so the UI can
      render a dynamic credential form.

    Returns an empty list if no providers are available (error shown in UI).
    """
    omni = _metadata_omni()

    providers = await list_available_providers(
        session=session,
        tenant_id=link_token.tenant_id,
        allowed_providers=link_token.allowed_providers,
        locked_provider_key=link_token.locked_provider_key,
        settings=settings,
        omni=omni,
    )

    return {"providers": providers, "meta": {"request_id": request_id}}


# ---------------------------------------------------------------------------
# POST /connect/connections
# ---------------------------------------------------------------------------


@router.post("/connections", status_code=201)
async def create_connection(
    body: ConnectCreateConnectionRequest,
    request: Request,
    link_token: Annotated[LinkTokenContext, Depends(get_link_token_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: HostedSettings = Depends(get_hosted_settings),
    request_id: str = Depends(get_request_id),
):
    """Initiate or complete a provider connection on behalf of the link token's tenant.

    Behavior varies by provider type and token scope:

    **OAuth providers (``credentials`` is null):**
    Creates a pending connection and returns ``authorization_url`` for the
    browser to redirect to. For reconnect tokens, reauthorizes the existing
    connection.

    **Non-OAuth providers (``credentials`` provided):**
    Validates and stores credentials immediately. Returns ``status: "active"``
    with no ``authorization_url`` on success. Returns 400 with inline errors on
    validation failure — the user can retry without a new link token.
    """
    tenant_id = link_token.tenant_id

    # Effective external_id (prefer body, fall back to token's end_user_id)
    external_id = body.external_id or link_token.end_user_id

    # body.redirect_uri is the OAuth callback URL (where the provider returns the
    # user to the Connect UI).  link_token.redirect_uri is the final app
    # destination after connection; it is returned to the UI via the session
    # exchange and used client-side only — not here.
    redirect_uri = body.redirect_uri or link_token.redirect_uri

    # Determine provider metadata to check auth_kind
    omni = _metadata_omni()
    try:
        meta = omni.describe_provider(body.provider_key)
    except KeyError as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "provider_not_found",
                "message": f"Unknown provider: {body.provider_key}",
            },
        ) from exc

    is_oauth = any(k.value == "oauth2" for k in meta.auth_kinds)
    auth_kind = meta.auth_kinds[0].value if meta.auth_kinds else "oauth2"

    # Enforce allowed_providers restriction from the link token
    if (
        link_token.allowed_providers is not None
        and body.provider_key not in link_token.allowed_providers
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "provider_not_allowed",
                "message": f"Provider '{body.provider_key}' is not allowed for this session",
            },
        )

    # Enforce tenant is_enabled flag
    provider_config = await get_tenant_provider_config(
        session=session, tenant_id=tenant_id, provider_key=body.provider_key
    )
    if not is_provider_available(
        provider_key=body.provider_key,
        auth_kind=auth_kind,
        config=provider_config,
        settings=settings,
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "provider_not_available",
                "message": f"Provider '{body.provider_key}' is not available",
            },
        )

    # -----------------------------------------------------------------------
    # Reconnect flow
    # -----------------------------------------------------------------------
    if link_token.is_reconnect:
        reconnect_connection_id = link_token.connection_id
        if reconnect_connection_id is None:
            raise HTTPException(
                status_code=500,
                detail={
                    "code": "internal_error",
                    "message": "Missing connection_id on reconnect token",
                },
            )

        # Validate that the requested provider matches the locked provider
        if link_token.locked_provider_key and body.provider_key != link_token.locked_provider_key:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "provider_mismatch",
                    "message": (
                        f"This token is locked to provider '{link_token.locked_provider_key}'"
                    ),
                },
            )

        if not is_oauth:
            # Non-OAuth reconnect: update credentials, validate, mark active
            if not body.credentials:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "code": "credentials_required",
                        "message": "Credentials are required for non-OAuth reconnect",
                    },
                )
            # Verify tenant owns this connection before updating credentials
            await _load_tenant_connection(str(reconnect_connection_id), session, tenant_id)
            conn = await update_credential_connection(
                connection_id=reconnect_connection_id,
                credentials=body.credentials,
                session=session,
                encryption=encryption,
            )
            await deactivate_link_token(link_token.link_token_id, session)
            return {
                "data": ConnectCreateConnectionResponse(
                    connection_id=str(conn.id),
                    status=ConnectionStatus.ACTIVE,
                    authorization_url=None,
                ),
                "meta": {"request_id": request_id},
            }

        # OAuth reconnect: reauthorize the existing connection
        if not redirect_uri:
            raise HTTPException(
                status_code=400,
                detail={"code": "redirect_uri_required", "message": "redirect_uri is required"},
            )

        result = await reauthorize_connection_flow(
            connection_id=str(reconnect_connection_id),
            body=ReauthorizeConnectionRequest(redirect_url=redirect_uri),
            request=request,
            session=session,
            settings=settings,
            load_connection=lambda cid, s: _load_tenant_connection(cid, s, tenant_id),
            load_provider_config=lambda pk, s: get_tenant_provider_config(
                session=s, tenant_id=tenant_id, provider_key=pk
            ),
            build_omni=lambda s, pk, pc: _build_omni(s, encryption, settings, tenant_id, pk, pc),
        )
        await deactivate_link_token(link_token.link_token_id, session)
        return {
            "data": ConnectCreateConnectionResponse(
                connection_id=result.connection_id,
                status=result.status,
                authorization_url=result.authorization_url,
            ),
            "meta": {"request_id": request_id},
        }

    # -----------------------------------------------------------------------
    # New connection flow
    # -----------------------------------------------------------------------

    if not is_oauth:
        # Non-OAuth: validate and store credentials inline
        if not body.credentials:
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "credentials_required",
                    "message": "Credentials are required for non-OAuth providers",
                },
            )
        auth_kind = meta.auth_kinds[0].value
        conn = await create_credential_connection(
            provider_key=body.provider_key,
            auth_kind=auth_kind,
            credentials=body.credentials,
            external_id=external_id,
            session=session,
            encryption=encryption,
            persist_post_create=lambda c, s: _persist_owner(c, s, tenant_id),
        )
        await deactivate_link_token(link_token.link_token_id, session)
        return {
            "data": ConnectCreateConnectionResponse(
                connection_id=str(conn.id),
                status=ConnectionStatus.ACTIVE,
                authorization_url=None,
            ),
            "meta": {"request_id": request_id},
        }

    # OAuth: initiate redirect flow
    if not redirect_uri:
        raise HTTPException(
            status_code=400,
            detail={"code": "redirect_uri_required", "message": "redirect_uri is required"},
        )

    # Map to the server's CreateConnectionRequest schema
    server_body = CreateConnectionRequest(
        provider=body.provider_key,
        external_id=external_id,
        redirect_url=redirect_uri,
        metadata=None,
    )

    await enforce_fallback_connection_limit(
        session=session,
        tenant_id=tenant_id,
        provider_key=body.provider_key,
        limit=settings.hosted_fallback_connection_limit,
    )
    flow_result = await create_connection_flow(
        body=server_body,
        request=request,
        session=session,
        settings=settings,
        load_provider_config=lambda pk, s: get_tenant_provider_config(
            session=s,
            tenant_id=tenant_id,
            provider_key=pk,
        ),
        count_active_connections=lambda pk, s: _count_active_connections(pk, s, tenant_id),
        build_omni=lambda s, pk, pc: _build_omni(s, encryption, settings, tenant_id, pk, pc),
        persist_post_create=lambda conn, s: _persist_owner(conn, s, tenant_id),
    )

    await deactivate_link_token(link_token.link_token_id, session)
    return {
        "data": ConnectCreateConnectionResponse(
            connection_id=flow_result.connection_id,
            status=flow_result.status,
            authorization_url=flow_result.authorization_url,
        ),
        "meta": {"request_id": request_id},
    }


async def _load_tenant_connection(
    connection_id: str, session: AsyncSession, tenant_id: uuid.UUID
) -> Connection:
    """Load a connection by ID, verifying tenant ownership. Raises 404 on failure."""

    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    owner_result = await session.execute(
        select(HostedConnectionOwner).where(
            HostedConnectionOwner.connection_id == conn_uuid,
            HostedConnectionOwner.tenant_id == tenant_id,
        )
    )
    if owner_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    conn_result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )
    return conn
