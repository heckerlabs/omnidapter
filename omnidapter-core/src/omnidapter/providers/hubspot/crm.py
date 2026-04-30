"""HubSpot CRM service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.hubspot import mappers
from omnidapter.services.crm.capabilities import CrmCapability
from omnidapter.services.crm.interface import CrmService
from omnidapter.services.crm.models import Activity, Company, Contact, Deal
from omnidapter.services.crm.requests import (
    CreateActivityRequest,
    CreateCompanyRequest,
    CreateContactRequest,
    CreateDealRequest,
    ListActivitiesRequest,
    ListCompaniesRequest,
    ListContactsRequest,
    ListDealsRequest,
    UpdateActivityRequest,
    UpdateCompanyRequest,
    UpdateContactRequest,
    UpdateDealRequest,
)
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

_HS_BASE = "https://api.hubapi.com"

_HS_CRM_CAPABILITIES = frozenset(
    {
        CrmCapability.LIST_CONTACTS,
        CrmCapability.GET_CONTACT,
        CrmCapability.CREATE_CONTACT,
        CrmCapability.UPDATE_CONTACT,
        CrmCapability.DELETE_CONTACT,
        CrmCapability.SEARCH_CONTACTS,
        CrmCapability.LIST_COMPANIES,
        CrmCapability.GET_COMPANY,
        CrmCapability.CREATE_COMPANY,
        CrmCapability.UPDATE_COMPANY,
        CrmCapability.DELETE_COMPANY,
        CrmCapability.LIST_DEALS,
        CrmCapability.GET_DEAL,
        CrmCapability.CREATE_DEAL,
        CrmCapability.UPDATE_DEAL,
        CrmCapability.DELETE_DEAL,
        CrmCapability.LIST_ACTIVITIES,
        CrmCapability.CREATE_ACTIVITY,
        CrmCapability.UPDATE_ACTIVITY,
        CrmCapability.DELETE_ACTIVITY,
    }
)

_CONTACT_PROPS = "firstname,lastname,email,phone,mobilephone,company,associatedcompanyid,hs_tags"
_COMPANY_PROPS = "name,website,industry,phone,email"
_DEAL_PROPS = "dealname,dealstage,amount,closedate,hubspot_owner_id,description"
_NOTE_PROPS = "hs_note_body,hs_timestamp,createdate"


class HubspotCrmService(CrmService):
    """HubSpot v3 API CRM service."""

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: RetryPolicy | None = None,
        hooks: Any = None,
    ) -> None:
        self._connection_id = connection_id
        self._stored = stored_credential
        self._http = OmnidapterHttpClient(
            provider_key="hubspot",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CrmCapability]:
        return _HS_CRM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "hubspot"

    async def _resolve_stored_credential(self) -> StoredCredential:
        resolver = getattr(self, "_credential_resolver", None)
        if resolver is None:
            return self._stored
        self._stored = await resolver(self._connection_id)
        return self._stored

    async def _auth_headers(self) -> dict[str, str]:
        creds = (await self._resolve_stored_credential()).credentials
        if isinstance(creds, OAuth2Credentials):
            return {"Authorization": f"Bearer {creds.access_token}"}
        return {}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.request(
            "GET",
            f"{_HS_BASE}{path}",
            headers=await self._auth_headers(),
            params=params,
        )
        return resp.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        resp = await self._http.request(
            "POST",
            f"{_HS_BASE}{path}",
            headers=await self._auth_headers(),
            json=body,
        )
        return resp.json()

    async def _patch(self, path: str, body: dict[str, Any]) -> Any:
        resp = await self._http.request(
            "PATCH",
            f"{_HS_BASE}{path}",
            headers=await self._auth_headers(),
            json=body,
        )
        return resp.json()

    async def _delete(self, path: str) -> None:
        await self._http.request(
            "DELETE",
            f"{_HS_BASE}{path}",
            headers=await self._auth_headers(),
        )

    async def _paginate(
        self, path: str, params: dict[str, Any], object_type: str = ""
    ) -> AsyncGenerator[dict, None]:
        after: str | None = None
        while True:
            p = {**params}
            if after:
                p["after"] = after
            data = await self._get(path, p)
            for item in data.get("results") or []:
                yield item
            paging = data.get("paging") or {}
            next_page = (paging.get("next") or {}).get("after")
            if not next_page:
                break
            after = next_page

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        self._require_capability(CrmCapability.LIST_CONTACTS)
        return self._iter_contacts(request)

    async def _iter_contacts(self, request: ListContactsRequest) -> AsyncGenerator[Contact, None]:
        limit = min(request.page_size or 100, 100)
        async for item in self._paginate(
            "/crm/v3/objects/contacts",
            {"properties": _CONTACT_PROPS, "limit": limit},
        ):
            yield mappers.to_contact(item)

    async def get_contact(self, contact_id: str) -> Contact:
        self._require_capability(CrmCapability.GET_CONTACT)
        data = await self._get(
            f"/crm/v3/objects/contacts/{contact_id}", {"properties": _CONTACT_PROPS}
        )
        return mappers.to_contact(data)

    async def create_contact(self, request: CreateContactRequest) -> Contact:
        self._require_capability(CrmCapability.CREATE_CONTACT)
        props: dict[str, Any] = {}
        if request.first_name:
            props["firstname"] = request.first_name
        if request.last_name:
            props["lastname"] = request.last_name
        if request.emails:
            props["email"] = request.emails[0].address
        if request.phones:
            props["phone"] = request.phones[0].number
        if request.company_name:
            props["company"] = request.company_name
        if request.notes:
            props["hs_content_membership_notes"] = request.notes
        data = await self._post("/crm/v3/objects/contacts", {"properties": props})
        return mappers.to_contact(data)

    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        self._require_capability(CrmCapability.UPDATE_CONTACT)
        props: dict[str, Any] = {}
        if request.first_name is not None:
            props["firstname"] = request.first_name
        if request.last_name is not None:
            props["lastname"] = request.last_name
        if request.emails is not None:
            props["email"] = request.emails[0].address if request.emails else ""
        if request.phones is not None:
            props["phone"] = request.phones[0].number if request.phones else ""
        if request.notes is not None:
            props["hs_content_membership_notes"] = request.notes
        data = await self._patch(
            f"/crm/v3/objects/contacts/{request.contact_id}", {"properties": props}
        )
        return mappers.to_contact(data)

    async def delete_contact(self, contact_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_CONTACT)
        await self._delete(f"/crm/v3/objects/contacts/{contact_id}")

    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        self._require_capability(CrmCapability.SEARCH_CONTACTS)
        body = {
            "filterGroups": [
                {
                    "filters": [
                        {"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": query}
                    ]
                },
                {
                    "filters": [
                        {"propertyName": "lastname", "operator": "CONTAINS_TOKEN", "value": query}
                    ]
                },
                {
                    "filters": [
                        {"propertyName": "email", "operator": "CONTAINS_TOKEN", "value": query}
                    ]
                },
            ],
            "properties": _CONTACT_PROPS.split(","),
            "limit": min(limit, 100),
        }
        data = await self._post("/crm/v3/objects/contacts/search", body)
        return [mappers.to_contact(item) for item in (data.get("results") or [])]

    # ── Companies ─────────────────────────────────────────────────────────────

    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        self._require_capability(CrmCapability.LIST_COMPANIES)
        return self._iter_companies(request)

    async def _iter_companies(self, request: ListCompaniesRequest) -> AsyncGenerator[Company, None]:
        limit = min(request.page_size or 100, 100)
        async for item in self._paginate(
            "/crm/v3/objects/companies",
            {"properties": _COMPANY_PROPS, "limit": limit},
        ):
            yield mappers.to_company(item)

    async def get_company(self, company_id: str) -> Company:
        self._require_capability(CrmCapability.GET_COMPANY)
        data = await self._get(
            f"/crm/v3/objects/companies/{company_id}", {"properties": _COMPANY_PROPS}
        )
        return mappers.to_company(data)

    async def create_company(self, request: CreateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.CREATE_COMPANY)
        props: dict[str, Any] = {"name": request.name}
        if request.website:
            props["website"] = request.website
        if request.industry:
            props["industry"] = request.industry
        if request.phone:
            props["phone"] = request.phone
        if request.email:
            props["email"] = request.email
        data = await self._post("/crm/v3/objects/companies", {"properties": props})
        return mappers.to_company(data)

    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.UPDATE_COMPANY)
        props: dict[str, Any] = {}
        if request.name is not None:
            props["name"] = request.name
        if request.website is not None:
            props["website"] = request.website
        if request.industry is not None:
            props["industry"] = request.industry
        if request.phone is not None:
            props["phone"] = request.phone
        if request.email is not None:
            props["email"] = request.email
        data = await self._patch(
            f"/crm/v3/objects/companies/{request.company_id}", {"properties": props}
        )
        return mappers.to_company(data)

    async def delete_company(self, company_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_COMPANY)
        await self._delete(f"/crm/v3/objects/companies/{company_id}")

    # ── Deals ─────────────────────────────────────────────────────────────────

    def list_deals(self, request: ListDealsRequest) -> AsyncIterator[Deal]:
        self._require_capability(CrmCapability.LIST_DEALS)
        return self._iter_deals(request)

    async def _iter_deals(self, request: ListDealsRequest) -> AsyncGenerator[Deal, None]:
        limit = min(request.page_size or 100, 100)
        async for item in self._paginate(
            "/crm/v3/objects/deals",
            {"properties": _DEAL_PROPS, "limit": limit},
        ):
            yield mappers.to_deal(item)

    async def get_deal(self, deal_id: str) -> Deal:
        self._require_capability(CrmCapability.GET_DEAL)
        data = await self._get(f"/crm/v3/objects/deals/{deal_id}", {"properties": _DEAL_PROPS})
        return mappers.to_deal(data)

    async def create_deal(self, request: CreateDealRequest) -> Deal:
        self._require_capability(CrmCapability.CREATE_DEAL)
        stage_id = request.stage_id or (
            mappers.stage_to_hs_id(request.stage) if request.stage else "appointmentscheduled"
        )
        props: dict[str, Any] = {
            "dealname": request.name,
            "dealstage": stage_id,
        }
        if request.value:
            props["amount"] = request.value
        if request.close_date:
            props["closedate"] = request.close_date.isoformat()
        if request.owner_id:
            props["hubspot_owner_id"] = request.owner_id
        if request.notes:
            props["description"] = request.notes
        data = await self._post("/crm/v3/objects/deals", {"properties": props})
        return mappers.to_deal(data)

    async def update_deal(self, request: UpdateDealRequest) -> Deal:
        self._require_capability(CrmCapability.UPDATE_DEAL)
        props: dict[str, Any] = {}
        if request.name is not None:
            props["dealname"] = request.name
        if request.stage is not None:
            props["dealstage"] = mappers.stage_to_hs_id(request.stage)
        if request.stage_id is not None:
            props["dealstage"] = request.stage_id
        if request.value is not None:
            props["amount"] = request.value
        if request.close_date is not None:
            props["closedate"] = request.close_date.isoformat()
        if request.notes is not None:
            props["description"] = request.notes
        data = await self._patch(f"/crm/v3/objects/deals/{request.deal_id}", {"properties": props})
        return mappers.to_deal(data)

    async def delete_deal(self, deal_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_DEAL)
        await self._delete(f"/crm/v3/objects/deals/{deal_id}")

    # ── Activities (Notes + Calls + Meetings) ─────────────────────────────────

    _ACTIVITY_OBJECT_TYPES = {
        "notes": _NOTE_PROPS,
        "calls": "hs_call_title,hs_call_body,hs_timestamp",
        "emails": "hs_email_subject,hs_email_text,hs_timestamp",
        "meetings": "hs_meeting_title,hs_meeting_body,hs_timestamp",
    }

    def list_activities(self, request: ListActivitiesRequest) -> AsyncIterator[Activity]:
        self._require_capability(CrmCapability.LIST_ACTIVITIES)
        return self._iter_activities(request)

    async def _iter_activities(
        self, request: ListActivitiesRequest
    ) -> AsyncGenerator[Activity, None]:
        limit = min(request.page_size or 100, 100)
        for obj_type, props in self._ACTIVITY_OBJECT_TYPES.items():
            async for item in self._paginate(
                f"/crm/v3/objects/{obj_type}",
                {"properties": props, "limit": limit},
            ):
                yield mappers.to_activity(item, object_type=obj_type)

    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        from omnidapter.services.crm.models import ActivityKind

        self._require_capability(CrmCapability.CREATE_ACTIVITY)
        kind_to_obj = {
            ActivityKind.NOTE: "notes",
            ActivityKind.CALL: "calls",
            ActivityKind.EMAIL: "emails",
            ActivityKind.MEETING: "meetings",
            ActivityKind.TASK: "tasks",
        }
        obj_type = kind_to_obj.get(request.kind, "notes")
        props: dict[str, Any] = {}
        if obj_type == "notes":
            props["hs_note_body"] = request.body or request.subject or ""
        elif obj_type == "calls":
            props["hs_call_title"] = request.subject or "Call"
            props["hs_call_body"] = request.body or ""
        elif obj_type == "emails":
            props["hs_email_subject"] = request.subject or "Email"
            props["hs_email_text"] = request.body or ""
        elif obj_type == "meetings":
            props["hs_meeting_title"] = request.subject or "Meeting"
            props["hs_meeting_body"] = request.body or ""
        elif obj_type == "tasks":
            props["hs_task_subject"] = request.subject or "Task"
            props["hs_task_body"] = request.body or ""
            props["hs_task_status"] = "COMPLETED"
        if request.occurred_at:
            props["hs_timestamp"] = int(request.occurred_at.timestamp() * 1000)
        data = await self._post(f"/crm/v3/objects/{obj_type}", {"properties": props})
        return mappers.to_activity(data, object_type=obj_type)

    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.UPDATE_ACTIVITY)
        for obj_type, _props_str in self._ACTIVITY_OBJECT_TYPES.items():
            try:
                props: dict[str, Any] = {}
                if request.body is not None:
                    if obj_type == "notes":
                        props["hs_note_body"] = request.body
                    else:
                        props[f"hs_{obj_type[:-1]}_body"] = request.body
                if request.subject is not None:
                    props[f"hs_{obj_type[:-1]}_title"] = request.subject
                if request.occurred_at is not None:
                    props["hs_timestamp"] = int(request.occurred_at.timestamp() * 1000)
                data = await self._patch(
                    f"/crm/v3/objects/{obj_type}/{request.activity_id}", {"properties": props}
                )
                return mappers.to_activity(data, object_type=obj_type)
            except Exception:  # noqa: BLE001
                continue
        data = await self._get(
            f"/crm/v3/objects/notes/{request.activity_id}", {"properties": _NOTE_PROPS}
        )
        return mappers.to_activity(data, object_type="notes")

    async def delete_activity(self, activity_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_ACTIVITY)
        for obj_type in self._ACTIVITY_OBJECT_TYPES:
            try:
                await self._delete(f"/crm/v3/objects/{obj_type}/{activity_id}")
                return
            except Exception:  # noqa: BLE001
                continue
