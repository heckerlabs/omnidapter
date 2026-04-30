"""Housecall Pro CRM service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from omnidapter.auth.models import ApiKeyCredentials
from omnidapter.providers.housecallpro import mappers
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

HCP_API_BASE = "https://api.housecallpro.com"

_HCP_CRM_CAPABILITIES = frozenset(
    {
        CrmCapability.LIST_CONTACTS,
        CrmCapability.GET_CONTACT,
        CrmCapability.CREATE_CONTACT,
        CrmCapability.UPDATE_CONTACT,
        CrmCapability.DELETE_CONTACT,
        CrmCapability.SEARCH_CONTACTS,
        CrmCapability.LIST_ACTIVITIES,
        CrmCapability.CREATE_ACTIVITY,
        CrmCapability.UPDATE_ACTIVITY,
        CrmCapability.DELETE_ACTIVITY,
        CrmCapability.TAGS,
    }
)


class HousecallProCrmService(CrmService):
    """Housecall Pro v1 REST API CRM service."""

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
            provider_key="housecallpro",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CrmCapability]:
        return _HCP_CRM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "housecallpro"

    async def _resolve_stored_credential(self) -> StoredCredential:
        resolver = getattr(self, "_credential_resolver", None)
        if resolver is None:
            return self._stored
        self._stored = await resolver(self._connection_id)
        return self._stored

    async def _auth_headers(self) -> dict[str, str]:
        creds = (await self._resolve_stored_credential()).credentials
        if isinstance(creds, ApiKeyCredentials):
            return {"Authorization": f"Bearer {creds.api_key}"}
        return {}

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        self._require_capability(CrmCapability.LIST_CONTACTS)
        return self._iter_contacts(request)

    async def _iter_contacts(self, request: ListContactsRequest) -> AsyncGenerator[Contact, None]:
        params: dict[str, Any] = {"page_size": request.page_size or 100}
        if request.search:
            params["q"] = request.search
        if request.tag:
            params["tag"] = request.tag
        page = 1
        headers = await self._auth_headers()
        while True:
            params["page"] = page
            resp = await self._http.request(
                "GET", f"{HCP_API_BASE}/customers", headers=headers, params=params
            )
            data = resp.json()
            items = data.get("customers") or (data if isinstance(data, list) else [])
            if not items:
                break
            for item in items:
                yield mappers.to_crm_contact(item)
            if len(items) < (request.page_size or 100):
                break
            page += 1

    async def get_contact(self, contact_id: str) -> Contact:
        self._require_capability(CrmCapability.GET_CONTACT)
        resp = await self._http.request(
            "GET", f"{HCP_API_BASE}/customers/{contact_id}", headers=await self._auth_headers()
        )
        return mappers.to_crm_contact(resp.json())

    async def create_contact(self, request: CreateContactRequest) -> Contact:
        self._require_capability(CrmCapability.CREATE_CONTACT)
        body: dict[str, Any] = {}
        if request.first_name:
            body["first_name"] = request.first_name
        if request.last_name:
            body["last_name"] = request.last_name
        if request.emails:
            body["email"] = request.emails[0].address
        if request.phones:
            body["mobile_number"] = request.phones[0].number
        if request.notes:
            body["notes"] = request.notes
        if request.tags:
            body["tags"] = request.tags
        if request.addresses:
            addr = request.addresses[0]
            body["address"] = {
                "street": addr.street,
                "city": addr.city,
                "state": addr.state,
                "zip": addr.zip,
                "country": addr.country,
            }
        if request.provider_data:
            body.update(request.provider_data)
        resp = await self._http.request(
            "POST",
            f"{HCP_API_BASE}/customers",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_crm_contact(resp.json())

    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        self._require_capability(CrmCapability.UPDATE_CONTACT)
        body: dict[str, Any] = {}
        if request.first_name is not None:
            body["first_name"] = request.first_name
        if request.last_name is not None:
            body["last_name"] = request.last_name
        if request.emails is not None:
            body["email"] = request.emails[0].address if request.emails else None
        if request.phones is not None:
            body["mobile_number"] = request.phones[0].number if request.phones else None
        if request.notes is not None:
            body["notes"] = request.notes
        if request.tags is not None:
            body["tags"] = request.tags
        if request.provider_data:
            body.update(request.provider_data)
        resp = await self._http.request(
            "PATCH",
            f"{HCP_API_BASE}/customers/{request.contact_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_crm_contact(resp.json())

    async def delete_contact(self, contact_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_CONTACT)
        await self._http.request(
            "DELETE",
            f"{HCP_API_BASE}/customers/{contact_id}",
            headers=await self._auth_headers(),
        )

    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        self._require_capability(CrmCapability.SEARCH_CONTACTS)
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/customers",
            headers=await self._auth_headers(),
            params={"q": query, "page_size": limit},
        )
        data = resp.json()
        items = data.get("customers") or (data if isinstance(data, list) else [])
        return [mappers.to_crm_contact(item) for item in items]

    # ── Companies — not supported ──────────────────────────────────────────────

    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        self._require_capability(CrmCapability.LIST_COMPANIES)
        raise AssertionError("unreachable")

    async def get_company(self, company_id: str) -> Company:
        self._require_capability(CrmCapability.GET_COMPANY)
        raise AssertionError("unreachable")

    async def create_company(self, request: CreateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.CREATE_COMPANY)
        raise AssertionError("unreachable")

    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.UPDATE_COMPANY)
        raise AssertionError("unreachable")

    async def delete_company(self, company_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_COMPANY)
        raise AssertionError("unreachable")

    # ── Deals — not supported ─────────────────────────────────────────────────

    def list_deals(self, request: ListDealsRequest) -> AsyncIterator[Deal]:
        self._require_capability(CrmCapability.LIST_DEALS)
        raise AssertionError("unreachable")

    async def get_deal(self, deal_id: str) -> Deal:
        self._require_capability(CrmCapability.GET_DEAL)
        raise AssertionError("unreachable")

    async def create_deal(self, request: CreateDealRequest) -> Deal:
        self._require_capability(CrmCapability.CREATE_DEAL)
        raise AssertionError("unreachable")

    async def update_deal(self, request: UpdateDealRequest) -> Deal:
        self._require_capability(CrmCapability.UPDATE_DEAL)
        raise AssertionError("unreachable")

    async def delete_deal(self, deal_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_DEAL)
        raise AssertionError("unreachable")

    # ── Activities (notes) ────────────────────────────────────────────────────

    def list_activities(self, request: ListActivitiesRequest) -> AsyncIterator[Activity]:
        self._require_capability(CrmCapability.LIST_ACTIVITIES)
        return self._iter_activities(request)

    async def _iter_activities(
        self, request: ListActivitiesRequest
    ) -> AsyncGenerator[Activity, None]:
        if not request.contact_id:
            return
        resp = await self._http.request(
            "GET",
            f"{HCP_API_BASE}/customers/{request.contact_id}/notes",
            headers=await self._auth_headers(),
        )
        data = resp.json()
        items = data if isinstance(data, list) else data.get("notes", [])
        for item in items:
            yield mappers.to_crm_activity(item, contact_id=request.contact_id)

    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.CREATE_ACTIVITY)
        body: dict[str, Any] = {"content": request.body or request.subject or ""}
        if request.provider_data:
            body.update(request.provider_data)
        resp = await self._http.request(
            "POST",
            f"{HCP_API_BASE}/customers/{request.contact_id}/notes",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_crm_activity(resp.json(), contact_id=request.contact_id)

    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.UPDATE_ACTIVITY)
        body: dict[str, Any] = {}
        if request.body is not None:
            body["content"] = request.body
        if request.provider_data:
            body.update(request.provider_data)
        resp = await self._http.request(
            "PATCH",
            f"{HCP_API_BASE}/notes/{request.activity_id}",
            headers=await self._auth_headers(),
            json=body,
        )
        return mappers.to_crm_activity(resp.json())

    async def delete_activity(self, activity_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_ACTIVITY)
        await self._http.request(
            "DELETE",
            f"{HCP_API_BASE}/notes/{activity_id}",
            headers=await self._auth_headers(),
        )
