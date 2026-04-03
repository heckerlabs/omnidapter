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
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import (
    LinkTokenContext,
    get_encryption_service,
    get_link_token_context,
    get_request_id,
)
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.models.provider_config import ProviderConfig
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.schemas.connection import (
    CreateConnectionRequest,
    ReauthorizeConnectionRequest,
)
from omnidapter_server.services.connect import (
    create_credential_connection,
    is_provider_available,
    list_available_providers,
    update_credential_connection,
)
from omnidapter_server.services.connection_flows import (
    create_connection_flow,
    reauthorize_connection_flow,
)
from omnidapter_server.services.link_tokens import create_connect_session
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(prefix="/connect", tags=["connect"])


def _metadata_omni() -> Omnidapter:
    """Omnidapter instance used only for provider metadata (listing, describing).

    Registers all built-in providers regardless of whether server-level OAuth
    credentials are present, so configured providers are never invisible.
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

    The bootstrap token is consumed immediately and permanently on first call —
    subsequent calls with the same token return ``token_already_used``.  The
    returned ``cs_`` session token is used as the ``Authorization: Bearer``
    credential for all other ``/connect/*`` endpoints.

    This endpoint requires **no** Authorization header.  The bootstrap token
    is passed in the request body so it never appears in server logs or the
    browser's address bar after the initial page load.
    """
    try:
        raw_session, link_token = await create_connect_session(body.token, session)
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

    from omnidapter_server.services.link_tokens import _SESSION_TOKEN_TTL_SECONDS

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
    settings: Settings,
    provider_key: str,
    provider_config: ProviderConfig | None,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = build_provider_registry(
        settings,
        provider_config=provider_config,
        encryption=encryption,
    )
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
    )


async def _get_provider_config(
    provider_key: str,
    session: AsyncSession,
) -> ProviderConfig | None:
    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    return result.scalar_one_or_none()


async def _load_all_provider_configs(session: AsyncSession) -> dict[str, ProviderConfig]:
    result = await session.execute(select(ProviderConfig))
    return {c.provider_key: c for c in result.scalars().all()}


async def _count_active_connections(provider_key: str, session: AsyncSession) -> int:
    result = await session.execute(
        select(func.count())
        .select_from(Connection)
        .where(
            Connection.provider_key == provider_key,
            Connection.status != ConnectionStatus.REVOKED,
        )
    )
    return int(result.scalar_one())


async def _load_connection_by_id(connection_id: str, session: AsyncSession) -> Connection:
    """Load a connection by string UUID, raising 404 if not found."""
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc
    result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    conn = result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )
    return conn


# ---------------------------------------------------------------------------
# GET /connect/providers
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_providers(
    link_token: Annotated[LinkTokenContext, Depends(get_link_token_context)],
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    session: AsyncSession = Depends(get_session),
):
    """List providers available for this connect session.

    - Filters by ``allowed_providers`` on the link token (if set).
    - Returns only the locked provider for reconnect tokens.
    - Includes ``credential_schema`` for non-OAuth providers so the UI can
      render a dynamic credential form.

    Returns an empty list if no providers are available (error shown in UI).
    """
    omni = _metadata_omni()

    async def _load_configs() -> dict[str, ProviderConfig]:
        return await _load_all_provider_configs(session)

    def _check(provider_key: str, auth_kind: str, config: ProviderConfig | None) -> bool:
        return is_provider_available(
            provider_key=provider_key,
            auth_kind=auth_kind,
            config=config,
            settings=settings,
        )

    providers = await list_available_providers(
        allowed_providers=link_token.allowed_providers,
        locked_provider_key=link_token.locked_provider_key,
        settings=settings,
        omni=omni,
        load_provider_configs=_load_configs,
        check_availability=_check,
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
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    """Initiate or complete a provider connection on behalf of the link token's end user.

    Behavior varies by provider type and token scope:

    **OAuth providers (``credentials`` is null):**
    Creates a pending connection and returns ``authorization_url`` for the
    browser to redirect to. For reconnect tokens, reauthorizes the existing
    connection.

    **Non-OAuth providers (``credentials`` provided):**
    Validates and stores credentials immediately. Returns ``status: "active"``
    with no ``authorization_url`` on success. Returns 422 with inline errors on
    validation failure — the user can retry without a new link token.
    """
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
            status_code=422,
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
            status_code=422,
            detail={
                "code": "provider_not_allowed",
                "message": f"Provider '{body.provider_key}' is not allowed for this session",
            },
        )

    # Enforce provider availability
    provider_config = await _get_provider_config(body.provider_key, session)
    if not is_provider_available(
        provider_key=body.provider_key,
        auth_kind=auth_kind,
        config=provider_config,
        settings=settings,
    ):
        raise HTTPException(
            status_code=422,
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
                status_code=422,
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
                    status_code=422,
                    detail={
                        "code": "credentials_required",
                        "message": "Credentials are required for non-OAuth reconnect",
                    },
                )
            conn = await update_credential_connection(
                connection_id=reconnect_connection_id,
                credentials=body.credentials,
                session=session,
                encryption=encryption,
            )
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
                status_code=422,
                detail={"code": "redirect_uri_required", "message": "redirect_uri is required"},
            )

        result = await reauthorize_connection_flow(
            connection_id=str(reconnect_connection_id),
            body=ReauthorizeConnectionRequest(redirect_url=redirect_uri),
            request=request,
            session=session,
            settings=settings,
            load_connection=lambda cid, s: _load_connection_by_id(cid, s),
            load_provider_config=lambda pk, s: _get_provider_config(pk, s),
            build_omni=lambda s, pk, pc: _build_omni(s, encryption, settings, pk, pc),
        )
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
                status_code=422,
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
        )
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
            status_code=422,
            detail={"code": "redirect_uri_required", "message": "redirect_uri is required"},
        )

    server_body = CreateConnectionRequest(
        provider=body.provider_key,
        external_id=external_id,
        redirect_url=redirect_uri,
        metadata=None,
    )

    flow_result = await create_connection_flow(
        body=server_body,
        request=request,
        session=session,
        settings=settings,
        load_provider_config=lambda pk, s: _get_provider_config(pk, s),
        count_active_connections=lambda pk, s: _count_active_connections(pk, s),
        build_omni=lambda s, pk, pc: _build_omni(s, encryption, settings, pk, pc),
    )

    return {
        "data": ConnectCreateConnectionResponse(
            connection_id=flow_result.connection_id,
            status=flow_result.status,
            authorization_url=flow_result.authorization_url,
        ),
        "meta": {"request_id": request_id},
    }
