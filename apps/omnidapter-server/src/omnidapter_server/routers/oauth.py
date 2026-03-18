"""OAuth callback endpoints."""

from __future__ import annotations

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from omnidapter import OAuthStateError, Omnidapter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import get_encryption_service
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.models.oauth_state import OAuthState
from omnidapter_server.models.provider_config import ProviderConfig
from omnidapter_server.origin_policy import parse_allowed_origin_domains, validate_redirect_url
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.services.connection_health import transition_to_active
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(prefix="/oauth", tags=["oauth"])


async def _get_provider_config(provider_key: str, session: AsyncSession) -> ProviderConfig | None:
    result = await session.execute(
        select(ProviderConfig).where(ProviderConfig.provider_key == provider_key)
    )
    return result.scalar_one_or_none()


def _append_query_params(url: str, **params: str) -> str:
    parts = urlsplit(url)
    query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value:
            query_params[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query_params), parts.fragment)
    )


def _validate_redirect_url_or_400(
    redirect_url: str,
    request: Request,
    settings: Settings,
) -> None:
    allowed_domains = parse_allowed_origin_domains(settings.omnidapter_allowed_origin_domains)
    try:
        validate_redirect_url(
            redirect_url,
            request_host=request.url.hostname,
            allowed_domain_patterns=allowed_domains,
            env=settings.omnidapter_env,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_redirect_url", "message": str(exc)},
        ) from exc


@router.get("/{provider_key}/callback")
async def oauth_callback(
    provider_key: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    encryption: EncryptionService = Depends(get_encryption_service),
    settings: Settings = Depends(get_settings),
    code: str | None = Query(None),
    state: str | None = Query(None),
    error: str | None = Query(None),
    error_description: str | None = Query(None),
):
    """Handle OAuth callback from provider."""
    if error:
        if state:
            result = await session.execute(
                select(OAuthState).where(OAuthState.state_token == state)
            )
            state_row = result.scalar_one_or_none()
            if state_row:
                conn_result = await session.execute(
                    select(Connection).where(Connection.id == state_row.connection_id)
                )
                conn = conn_result.scalar_one_or_none()
                if conn:
                    redirect_url = (conn.provider_config or {}).get("redirect_url", "")
                    if redirect_url:
                        _validate_redirect_url_or_400(redirect_url, request, settings)
                        return RedirectResponse(
                            url=_append_query_params(
                                redirect_url,
                                error=error,
                                error_description=error_description or "",
                                connection_id=str(conn.id),
                            )
                        )
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}: {error_description}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    state_result = await session.execute(select(OAuthState).where(OAuthState.state_token == state))
    state_row = state_result.scalar_one_or_none()
    if state_row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    connection_id = str(state_row.connection_id)

    conn_result = await session.execute(
        select(Connection).where(Connection.id == state_row.connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=400, detail="Connection not found")

    provider_config = await _get_provider_config(provider_key, session)

    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = build_provider_registry(
        settings,
        provider_config=provider_config,
        encryption=encryption,
    )

    omni = Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
    )

    callback_url = f"{settings.omnidapter_base_url}/oauth/{provider_key}/callback"

    try:
        stored_credential = await omni.oauth.complete(
            provider=provider_key,
            connection_id=connection_id,
            code=code,
            state=state,
            redirect_uri=callback_url,
        )
    except OAuthStateError as e:
        raise HTTPException(status_code=400, detail=f"OAuth state error: {e}") from e
    except Exception as e:
        await session.execute(
            update(Connection)
            .where(Connection.id == state_row.connection_id)
            .values(status=ConnectionStatus.REVOKED, status_reason=str(e))
        )
        await session.commit()
        raise HTTPException(status_code=400, detail=f"OAuth completion failed: {e}") from e

    await transition_to_active(
        connection_id=state_row.connection_id,
        session=session,
        granted_scopes=stored_credential.granted_scopes,
        provider_account_id=stored_credential.provider_account_id,
    )

    redirect_url = (conn.provider_config or {}).get("redirect_url", "")
    if redirect_url:
        _validate_redirect_url_or_400(redirect_url, request, settings)
        return RedirectResponse(url=_append_query_params(redirect_url, connection_id=connection_id))

    return {"status": "connected", "connection_id": connection_id}
