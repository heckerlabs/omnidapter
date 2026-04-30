"""CRM service proxy endpoints."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from omnidapter import (
    Activity,
    Company,
    Contact,
    CreateActivityRequest,
    CreateCompanyRequest,
    CreateContactRequest,
    CreateDealRequest,
    Deal,
    ListActivitiesRequest,
    ListCompaniesRequest,
    ListContactsRequest,
    ListDealsRequest,
    Omnidapter,
    UpdateActivityRequest,
    UpdateCompanyRequest,
    UpdateContactRequest,
    UpdateDealRequest,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.dependencies import (
    AuthContext,
    get_auth_context,
    get_encryption_service,
    get_request_id,
)
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.errors import check_connection_status
from omnidapter_server.models.connection import Connection
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.schemas.common import ApiResponse
from omnidapter_server.services.calendar_flows import get_connection_ready_or_404
from omnidapter_server.services.connection_health import update_last_used
from omnidapter_server.services.crm_flows import execute_crm_operation
from omnidapter_server.services.response_utils import wrap_response
from omnidapter_server.stores.credential_store import DatabaseCredentialStore
from omnidapter_server.stores.factory import build_oauth_state_store

router = APIRouter(tags=["crm"])


async def _build_omni(
    session: AsyncSession,
    encryption: EncryptionService,
    settings: Settings,
    provider_key: str,
) -> Omnidapter:
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    state_store = build_oauth_state_store(settings, session, encryption)
    registry = build_provider_registry(settings)
    return Omnidapter(
        credential_store=cred_store,
        oauth_state_store=state_store,
        registry=registry,
        auto_refresh=True,
    )


async def _load_connection_by_uuid(
    conn_uuid: uuid.UUID, session: AsyncSession
) -> Connection | None:
    result = await session.execute(select(Connection).where(Connection.id == conn_uuid))
    return result.scalar_one_or_none()


async def _get_conn(
    connection_id: str,
    session: AsyncSession,
    request: Request,
) -> Connection:
    return await get_connection_ready_or_404(
        connection_id=connection_id,
        session=session,
        request=request,
        load_connection_by_uuid=_load_connection_by_uuid,
        check_status=check_connection_status,
    )


def _wrap(data: object, request_id: str) -> dict:
    return wrap_response(data, request_id)


def _respond(data: object, request_id: str):
    if isinstance(data, Response):
        return data
    return _wrap(data, request_id)


# ── Contacts ──────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/crm/contacts",
    operation_id="crm_list_contacts",
    response_model=ApiResponse[list[Contact]],
)
async def crm_list_contacts(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    search: str | None = Query(None),
    company_id: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    list_req = ListContactsRequest(
        search=search,
        company_id=company_id,
        tag=tag,
        page_size=limit,
    )

    async def _op(crm):
        items = []
        async for contact in crm.list_contacts(list_req):
            items.append(contact)
            if len(items) >= limit:
                break
        return items

    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=_op,
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/crm/contacts/search",
    operation_id="crm_search_contacts",
    response_model=ApiResponse[list[Contact]],
)
async def crm_search_contacts(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    q: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.search_contacts(q, limit=limit),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/crm/contacts/{contact_id}",
    operation_id="crm_get_contact",
    response_model=ApiResponse[Contact],
)
async def crm_get_contact(
    connection_id: str,
    contact_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.get_contact(contact_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post(
    "/connections/{connection_id}/crm/contacts",
    status_code=201,
    operation_id="crm_create_contact",
    response_model=ApiResponse[Contact],
)
async def crm_create_contact(
    connection_id: str,
    body: CreateContactRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.create_contact(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch(
    "/connections/{connection_id}/crm/contacts/{contact_id}",
    operation_id="crm_update_contact",
    response_model=ApiResponse[Contact],
)
async def crm_update_contact(
    connection_id: str,
    contact_id: str,
    body: UpdateContactRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.update_contact(
            body.model_copy(update={"contact_id": contact_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete(
    "/connections/{connection_id}/crm/contacts/{contact_id}",
    status_code=204,
    operation_id="crm_delete_contact",
)
async def crm_delete_contact(
    connection_id: str,
    contact_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.delete_contact(contact_id),
        update_last_used=update_last_used,
    )


# ── Companies ─────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/crm/companies",
    operation_id="crm_list_companies",
    response_model=ApiResponse[list[Company]],
)
async def crm_list_companies(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    search: str | None = Query(None),
    tag: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    list_req = ListCompaniesRequest(search=search, tag=tag, page_size=limit)

    async def _op(crm):
        items = []
        async for company in crm.list_companies(list_req):
            items.append(company)
            if len(items) >= limit:
                break
        return items

    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=_op,
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/crm/companies/{company_id}",
    operation_id="crm_get_company",
    response_model=ApiResponse[Company],
)
async def crm_get_company(
    connection_id: str,
    company_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.get_company(company_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post(
    "/connections/{connection_id}/crm/companies",
    status_code=201,
    operation_id="crm_create_company",
    response_model=ApiResponse[Company],
)
async def crm_create_company(
    connection_id: str,
    body: CreateCompanyRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.create_company(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch(
    "/connections/{connection_id}/crm/companies/{company_id}",
    operation_id="crm_update_company",
    response_model=ApiResponse[Company],
)
async def crm_update_company(
    connection_id: str,
    company_id: str,
    body: UpdateCompanyRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.update_company(
            body.model_copy(update={"company_id": company_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete(
    "/connections/{connection_id}/crm/companies/{company_id}",
    status_code=204,
    operation_id="crm_delete_company",
)
async def crm_delete_company(
    connection_id: str,
    company_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.delete_company(company_id),
        update_last_used=update_last_used,
    )


# ── Deals ─────────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/crm/deals",
    operation_id="crm_list_deals",
    response_model=ApiResponse[list[Deal]],
)
async def crm_list_deals(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    contact_id: str | None = Query(None),
    company_id: str | None = Query(None),
    owner_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    list_req = ListDealsRequest(
        contact_id=contact_id,
        company_id=company_id,
        owner_id=owner_id,
        page_size=limit,
    )

    async def _op(crm):
        items = []
        async for deal in crm.list_deals(list_req):
            items.append(deal)
            if len(items) >= limit:
                break
        return items

    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=_op,
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.get(
    "/connections/{connection_id}/crm/deals/{deal_id}",
    operation_id="crm_get_deal",
    response_model=ApiResponse[Deal],
)
async def crm_get_deal(
    connection_id: str,
    deal_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.get_deal(deal_id),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post(
    "/connections/{connection_id}/crm/deals",
    status_code=201,
    operation_id="crm_create_deal",
    response_model=ApiResponse[Deal],
)
async def crm_create_deal(
    connection_id: str,
    body: CreateDealRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.create_deal(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch(
    "/connections/{connection_id}/crm/deals/{deal_id}",
    operation_id="crm_update_deal",
    response_model=ApiResponse[Deal],
)
async def crm_update_deal(
    connection_id: str,
    deal_id: str,
    body: UpdateDealRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.update_deal(body.model_copy(update={"deal_id": deal_id})),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete(
    "/connections/{connection_id}/crm/deals/{deal_id}",
    status_code=204,
    operation_id="crm_delete_deal",
)
async def crm_delete_deal(
    connection_id: str,
    deal_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.delete_deal(deal_id),
        update_last_used=update_last_used,
    )


# ── Activities ────────────────────────────────────────────────────────────────


@router.get(
    "/connections/{connection_id}/crm/activities",
    operation_id="crm_list_activities",
    response_model=ApiResponse[list[Activity]],
)
async def crm_list_activities(
    connection_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
    contact_id: str | None = Query(None),
    company_id: str | None = Query(None),
    deal_id: str | None = Query(None),
    limit: int = Query(100, ge=1, le=1000),
):
    list_req = ListActivitiesRequest(
        contact_id=contact_id,
        company_id=company_id,
        deal_id=deal_id,
        page_size=limit,
    )

    async def _op(crm):
        items = []
        async for activity in crm.list_activities(list_req):
            items.append(activity)
            if len(items) >= limit:
                break
        return items

    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=_op,
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.post(
    "/connections/{connection_id}/crm/activities",
    status_code=201,
    operation_id="crm_create_activity",
    response_model=ApiResponse[Activity],
)
async def crm_create_activity(
    connection_id: str,
    body: CreateActivityRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.create_activity(body),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.patch(
    "/connections/{connection_id}/crm/activities/{activity_id}",
    operation_id="crm_update_activity",
    response_model=ApiResponse[Activity],
)
async def crm_update_activity(
    connection_id: str,
    activity_id: str,
    body: UpdateActivityRequest,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
    request_id: str = Depends(get_request_id),
):
    result = await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.update_activity(
            body.model_copy(update={"activity_id": activity_id})
        ),
        update_last_used=update_last_used,
    )
    return _respond(result, request_id)


@router.delete(
    "/connections/{connection_id}/crm/activities/{activity_id}",
    status_code=204,
    operation_id="crm_delete_activity",
)
async def crm_delete_activity(
    connection_id: str,
    activity_id: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    encryption: Annotated[EncryptionService, Depends(get_encryption_service)],
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
):
    await execute_crm_operation(
        connection_id=connection_id,
        request=request,
        session=session,
        load_connection=_get_conn,
        build_omni=lambda s, provider_key: _build_omni(s, encryption, settings, provider_key),
        operation=lambda crm: crm.delete_activity(activity_id),
        update_last_used=update_last_used,
    )
