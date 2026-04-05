"""Shared connection endpoint orchestration flows."""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.origin_policy import parse_allowed_origin_domains, validate_redirect_url
from omnidapter_server.schemas.connection import (
    CreateConnectionRequest,
    ReauthorizeConnectionRequest,
)

ProviderConfigLike = Any
ConnectionByUuidLoader = Callable[[uuid.UUID, AsyncSession], Awaitable[Connection | None]]
ProviderConfigLoader = Callable[[str, AsyncSession], Awaitable[ProviderConfigLike | None]]
ActiveConnectionCounter = Callable[[str, AsyncSession], Awaitable[int]]
OmniBuilder = Callable[[AsyncSession, str, ProviderConfigLike | None], Awaitable[Any]]
ConnectionPostCreate = Callable[[Connection, AsyncSession], Awaitable[None]]
PaginatedConnectionLoader = Callable[
    [AsyncSession, str | None, str | None, int, int, str | None],
    Awaitable[tuple[int, list[Connection]]],
]


@dataclass(frozen=True)
class CreateConnectionFlowResult:
    connection_id: str
    status: str
    authorization_url: str


@dataclass(frozen=True)
class ReauthorizeConnectionFlowResult:
    connection_id: str
    status: str
    authorization_url: str


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


async def get_connection_or_404(
    *,
    connection_id: str,
    session: AsyncSession,
    load_connection_by_uuid: ConnectionByUuidLoader,
) -> Connection:
    try:
        conn_uuid = uuid.UUID(connection_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        ) from exc

    conn = await load_connection_by_uuid(conn_uuid, session)
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )
    return conn


async def create_connection_flow(
    *,
    body: CreateConnectionRequest,
    request: Request,
    session: AsyncSession,
    settings: Settings,
    load_provider_config: ProviderConfigLoader,
    count_active_connections: ActiveConnectionCounter,
    build_omni: OmniBuilder,
    persist_post_create: ConnectionPostCreate | None = None,
) -> CreateConnectionFlowResult:
    validate_redirect_url_or_400(
        redirect_url=body.redirect_url,
        request=request,
        settings=settings,
    )

    provider_config = await load_provider_config(body.provider, session)

    conn = Connection(
        id=uuid.uuid4(),
        provider_key=body.provider,
        external_id=body.external_id,
        status=ConnectionStatus.PENDING,
        provider_config=None,
    )
    session.add(conn)
    await session.flush()
    if persist_post_create is not None:
        await persist_post_create(conn, session)
    await session.commit()
    await session.refresh(conn)

    omni = await build_omni(session, body.provider, provider_config)
    callback_url = f"{settings.omnidapter_base_url}/oauth/{body.provider}/callback"

    try:
        result = await omni.oauth.begin(
            provider=body.provider,
            connection_id=str(conn.id),
            redirect_uri=callback_url,
            scopes=getattr(provider_config, "scopes", None),
        )
    except Exception as exc:
        await session.delete(conn)
        await session.commit()
        raise HTTPException(
            status_code=400,
            detail={"code": "oauth_begin_failed", "message": str(exc)},
        ) from exc

    conn.provider_config = {
        "redirect_url": body.redirect_url,
        "metadata": body.metadata or {},
        "oauth_state": result.state,
    }
    await session.commit()

    return CreateConnectionFlowResult(
        connection_id=str(conn.id),
        status=ConnectionStatus.PENDING,
        authorization_url=result.authorization_url,
    )


async def list_connections_flow(
    *,
    session: AsyncSession,
    status: str | None,
    provider: str | None,
    external_id: str | None,
    limit: int,
    offset: int,
    load_paginated_connections: PaginatedConnectionLoader,
) -> tuple[int, list[Connection]]:
    return await load_paginated_connections(session, status, provider, limit, offset, external_id)


async def reauthorize_connection_flow(
    *,
    connection_id: str,
    body: ReauthorizeConnectionRequest,
    request: Request,
    session: AsyncSession,
    settings: Settings,
    load_connection: Callable[[str, AsyncSession], Awaitable[Connection]],
    load_provider_config: ProviderConfigLoader,
    build_omni: OmniBuilder,
) -> ReauthorizeConnectionFlowResult:
    conn = await load_connection(connection_id, session)
    validate_redirect_url_or_400(redirect_url=body.redirect_url, request=request, settings=settings)

    if conn.status == ConnectionStatus.REVOKED:
        raise HTTPException(
            status_code=410,
            detail={
                "code": "connection_revoked",
                "message": "Cannot reauthorize a revoked connection",
            },
        )

    provider_config = await load_provider_config(conn.provider_key, session)
    omni = await build_omni(session, conn.provider_key, provider_config)
    callback_url = f"{settings.omnidapter_base_url}/oauth/{conn.provider_key}/callback"

    existing_scopes = set(conn.granted_scopes or [])
    config_scopes = set(getattr(provider_config, "scopes", None) or [])
    union_scopes = list(existing_scopes | config_scopes) or None

    result = await omni.oauth.begin(
        provider=conn.provider_key,
        connection_id=str(conn.id),
        redirect_uri=callback_url,
        scopes=union_scopes,
    )

    await session.execute(
        update(Connection)
        .where(Connection.id == conn.id)
        .values(
            status=ConnectionStatus.PENDING,
            status_reason=None,
            provider_config={
                **(conn.provider_config or {}),
                "redirect_url": body.redirect_url,
                "oauth_state": result.state,
            },
        )
    )
    await session.commit()

    return ReauthorizeConnectionFlowResult(
        connection_id=connection_id,
        status=ConnectionStatus.PENDING,
        authorization_url=result.authorization_url,
    )
