"""Shared OAuth callback orchestration flows."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from fastapi import HTTPException, Request
from fastapi.responses import RedirectResponse
from omnidapter import OAuthStateError, Omnidapter
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.models.oauth_state import OAuthState
from omnidapter_server.origin_policy import parse_allowed_origin_domains, validate_redirect_url
from omnidapter_server.services.connection_health import transition_to_active


@dataclass(frozen=True)
class OAuthCallbackParams:
    provider_key: str
    code: str | None
    state: str | None
    error: str | None
    error_description: str | None


StateLoader = Callable[[str, AsyncSession], Awaitable[OAuthState | None]]
ConnectionByStateLoader = Callable[[OAuthState, AsyncSession], Awaitable[Connection | None]]
OmniBuilder = Callable[[str, Connection, AsyncSession], Awaitable[Omnidapter]]


def append_query_params(url: str, **params: str) -> str:
    parts = urlsplit(url)
    query_params = dict(parse_qsl(parts.query, keep_blank_values=True))
    for key, value in params.items():
        if value:
            query_params[key] = value
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query_params), parts.fragment)
    )


def validate_redirect_url_or_400(
    *,
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


async def oauth_callback_flow(
    *,
    params: OAuthCallbackParams,
    request: Request,
    session: AsyncSession,
    settings: Settings,
    load_oauth_state: StateLoader,
    load_connection_for_state: ConnectionByStateLoader,
    build_omni: OmniBuilder,
):
    if params.error:
        if params.state:
            state_row = await load_oauth_state(params.state, session)
            if state_row:
                conn = await load_connection_for_state(state_row, session)
                if conn:
                    redirect_url = (conn.provider_config or {}).get("redirect_url", "")
                    if redirect_url:
                        validate_redirect_url_or_400(
                            redirect_url=redirect_url,
                            request=request,
                            settings=settings,
                        )
                        return RedirectResponse(
                            url=append_query_params(
                                redirect_url,
                                error=params.error,
                                error_description=params.error_description or "",
                                connection_id=str(conn.id),
                            )
                        )
        raise HTTPException(
            status_code=400,
            detail=f"OAuth error: {params.error}: {params.error_description}",
        )

    if not params.code or not params.state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter")

    state_row = await load_oauth_state(params.state, session)
    if state_row is None:
        raise HTTPException(status_code=400, detail="Invalid or expired OAuth state")

    conn = await load_connection_for_state(state_row, session)
    if conn is None:
        raise HTTPException(status_code=400, detail="Connection not found")

    omni = await build_omni(params.provider_key, conn, session)
    callback_url = f"{settings.omnidapter_base_url}/oauth/{params.provider_key}/callback"

    try:
        stored_credential = await omni.oauth.complete(
            provider=params.provider_key,
            connection_id=str(state_row.connection_id),
            code=params.code,
            state=params.state,
            redirect_uri=callback_url,
        )
    except OAuthStateError as exc:
        raise HTTPException(status_code=400, detail=f"OAuth state error: {exc}") from exc
    except Exception as exc:
        await session.execute(
            update(Connection)
            .where(Connection.id == state_row.connection_id)
            .values(status=ConnectionStatus.REVOKED, status_reason=str(exc))
        )
        await session.commit()
        raise HTTPException(status_code=400, detail=f"OAuth completion failed: {exc}") from exc

    await transition_to_active(
        connection_id=state_row.connection_id,
        session=session,
        granted_scopes=stored_credential.granted_scopes,
        provider_account_id=stored_credential.provider_account_id,
    )

    redirect_url = (conn.provider_config or {}).get("redirect_url", "")
    if redirect_url:
        validate_redirect_url_or_400(redirect_url=redirect_url, request=request, settings=settings)
        return RedirectResponse(
            url=append_query_params(redirect_url, connection_id=str(state_row.connection_id))
        )

    return {"status": "connected", "connection_id": str(state_row.connection_id)}
