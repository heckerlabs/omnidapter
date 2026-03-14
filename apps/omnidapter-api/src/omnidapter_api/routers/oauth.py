"""OAuth callback endpoints — hosted OAuth flow."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from omnidapter import OAuthStateError, Omnidapter
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_api.config import Settings, get_settings
from omnidapter_api.database import get_session
from omnidapter_api.dependencies import get_encryption_service
from omnidapter_api.encryption import EncryptionService
from omnidapter_api.models.connection import Connection, ConnectionStatus
from omnidapter_api.models.oauth_state import OAuthState
from omnidapter_api.models.provider_config import ProviderConfig
from omnidapter_api.services.connection_health import transition_to_active
from omnidapter_api.stores.credential_store import DatabaseCredentialStore
from omnidapter_api.stores.oauth_state_store import DatabaseOAuthStateStore

router = APIRouter(prefix="/oauth", tags=["oauth"])


async def _get_provider_config(
    org_id: uuid.UUID, provider_key: str, session: AsyncSession
) -> ProviderConfig | None:
    result = await session.execute(
        select(ProviderConfig).where(
            ProviderConfig.organization_id == org_id,
            ProviderConfig.provider_key == provider_key,
        )
    )
    return result.scalar_one_or_none()


@router.get("/{provider_key}/authorize")
async def oauth_authorize(
    provider_key: str,
    state: str = Query(...),
    request: Request = None,
    session: AsyncSession = Depends(get_session),
):
    """Redirect browser to provider's authorization URL.

    This endpoint is called when organizations redirect end users here.
    We look up the OAuth state and redirect to the provider.
    """
    # Look up the state record to get the authorization URL stored by begin()
    result = await session.execute(select(OAuthState).where(OAuthState.state_token == state))
    state_row = result.scalar_one_or_none()
    if state_row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    raise HTTPException(
        status_code=400,
        detail="Authorization URL should be used directly. This endpoint is for callbacks.",
    )


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
        # Provider denied access or error occurred
        # Try to look up state to find redirect_url
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
                        return RedirectResponse(
                            url=f"{redirect_url}?error={error}&connection_id={conn.id}"
                        )
        raise HTTPException(status_code=400, detail=f"OAuth error: {error}: {error_description}")

    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    # Look up state token to find the connection
    state_result = await session.execute(select(OAuthState).where(OAuthState.state_token == state))
    state_row = state_result.scalar_one_or_none()
    if state_row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    connection_id = str(state_row.connection_id)

    # Look up connection
    conn_result = await session.execute(
        select(Connection).where(Connection.id == state_row.connection_id)
    )
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(status_code=400, detail="Connection not found")

    # Get provider config for the organization
    provider_config = await _get_provider_config(conn.organization_id, provider_key, session)

    # Set up env override if org has their own credentials
    if provider_config and not provider_config.is_fallback:
        client_id = encryption.decrypt(provider_config.client_id_encrypted or "")
        client_secret = encryption.decrypt(provider_config.client_secret_encrypted or "")
        import os

        env_prefix = provider_key.upper()
        os.environ[f"OMNIDAPTER_{env_prefix}_CLIENT_ID"] = client_id
        os.environ[f"OMNIDAPTER_{env_prefix}_CLIENT_SECRET"] = client_secret

    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = DatabaseOAuthStateStore(session=session, encryption=encryption)

    omni = Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        auto_register_by_env=True,
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
        # Mark connection as revoked on failure
        await session.execute(
            update(Connection)
            .where(Connection.id == state_row.connection_id)
            .values(status=ConnectionStatus.REVOKED, status_reason=str(e))
        )
        await session.commit()
        raise HTTPException(status_code=400, detail=f"OAuth completion failed: {e}") from e

    # Transition connection to active
    await transition_to_active(
        connection_id=state_row.connection_id,
        session=session,
        granted_scopes=stored_credential.granted_scopes,
        provider_account_id=stored_credential.provider_account_id,
    )

    # Get redirect URL from connection's provider_config
    redirect_url = (conn.provider_config or {}).get("redirect_url", "")
    if redirect_url:
        return RedirectResponse(url=f"{redirect_url}?connection_id={connection_id}")

    return {"status": "connected", "connection_id": connection_id}
