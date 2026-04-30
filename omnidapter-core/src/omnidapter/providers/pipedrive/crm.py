"""Pipedrive CRM service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.providers.pipedrive import mappers
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

_PD_DEFAULT_DOMAIN = "api"

_PD_CRM_CAPABILITIES = frozenset(
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


class PipedriveCrmService(CrmService):
    """Pipedrive API v1 CRM service."""

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
            provider_key="pipedrive",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CrmCapability]:
        return _PD_CRM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "pipedrive"

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

    def _base_url(self) -> str:
        config = self._stored.provider_config or {}
        domain = config.get("api_domain") or _PD_DEFAULT_DOMAIN
        return f"https://{domain}.pipedrive.com/api/v1"

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.request(
            "GET",
            f"{self._base_url()}{path}",
            headers=await self._auth_headers(),
            params=params,
        )
        return resp.json()

    async def _post(self, path: str, body: dict[str, Any]) -> Any:
        resp = await self._http.request(
            "POST",
            f"{self._base_url()}{path}",
            headers=await self._auth_headers(),
            json=body,
        )
        return resp.json()

    async def _put(self, path: str, body: dict[str, Any]) -> Any:
        resp = await self._http.request(
            "PUT",
            f"{self._base_url()}{path}",
            headers=await self._auth_headers(),
            json=body,
        )
        return resp.json()

    async def _delete(self, path: str) -> None:
        await self._http.request(
            "DELETE",
            f"{self._base_url()}{path}",
            headers=await self._auth_headers(),
        )

    async def _paginate(self, path: str, params: dict[str, Any]) -> AsyncGenerator[dict, None]:
        start = 0
        limit = params.get("limit", 100)
        while True:
            p = {**params, "start": start}
            data = await self._get(path, p)
            items = data.get("data") or []
            for item in items:
                yield item
            additional = (data.get("additional_data") or {}).get("pagination") or {}
            if not additional.get("more_items_in_collection"):
                break
            start += limit

    # ── Contacts (Persons) ────────────────────────────────────────────────────

    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        self._require_capability(CrmCapability.LIST_CONTACTS)
        return self._iter_contacts(request)

    async def _iter_contacts(self, request: ListContactsRequest) -> AsyncGenerator[Contact, None]:
        params: dict[str, Any] = {"limit": request.page_size or 100}
        async for item in self._paginate("/persons", params):
            yield mappers.to_contact(item)

    async def get_contact(self, contact_id: str) -> Contact:
        self._require_capability(CrmCapability.GET_CONTACT)
        data = await self._get(f"/persons/{contact_id}")
        return mappers.to_contact(data.get("data") or {})

    async def create_contact(self, request: CreateContactRequest) -> Contact:
        self._require_capability(CrmCapability.CREATE_CONTACT)
        name = f"{request.first_name or ''} {request.last_name or ''}".strip() or "Unknown"
        body: dict[str, Any] = {"name": name}
        if request.emails:
            body["email"] = [
                {"value": e.address, "label": e.label or "work"} for e in request.emails
            ]
        if request.phones:
            body["phone"] = [
                {"value": p.number, "label": p.label or "work"} for p in request.phones
            ]
        if request.company_id:
            body["org_id"] = int(request.company_id)
        data = await self._post("/persons", body)
        return mappers.to_contact(data.get("data") or {})

    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        self._require_capability(CrmCapability.UPDATE_CONTACT)
        body: dict[str, Any] = {}
        if request.first_name is not None or request.last_name is not None:
            current = await self.get_contact(request.contact_id)
            first = (
                request.first_name if request.first_name is not None else (current.first_name or "")
            )
            last = request.last_name if request.last_name is not None else (current.last_name or "")
            body["name"] = f"{first} {last}".strip()
        if request.emails is not None:
            body["email"] = [
                {"value": e.address, "label": e.label or "work"} for e in request.emails
            ]
        if request.phones is not None:
            body["phone"] = [
                {"value": p.number, "label": p.label or "work"} for p in request.phones
            ]
        data = await self._put(f"/persons/{request.contact_id}", body)
        return mappers.to_contact(data.get("data") or {})

    async def delete_contact(self, contact_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_CONTACT)
        await self._delete(f"/persons/{contact_id}")

    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        self._require_capability(CrmCapability.SEARCH_CONTACTS)
        data = await self._get("/persons/search", {"term": query, "limit": limit})
        items = (data.get("data") or {}).get("items") or []
        return [mappers.to_contact(item.get("item") or {}) for item in items]

    # ── Companies (Organizations) ─────────────────────────────────────────────

    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        self._require_capability(CrmCapability.LIST_COMPANIES)
        return self._iter_companies(request)

    async def _iter_companies(self, request: ListCompaniesRequest) -> AsyncGenerator[Company, None]:
        params: dict[str, Any] = {"limit": request.page_size or 100}
        async for item in self._paginate("/organizations", params):
            yield mappers.to_company(item)

    async def get_company(self, company_id: str) -> Company:
        self._require_capability(CrmCapability.GET_COMPANY)
        data = await self._get(f"/organizations/{company_id}")
        return mappers.to_company(data.get("data") or {})

    async def create_company(self, request: CreateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.CREATE_COMPANY)
        body: dict[str, Any] = {"name": request.name}
        data = await self._post("/organizations", body)
        return mappers.to_company(data.get("data") or {})

    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.UPDATE_COMPANY)
        body: dict[str, Any] = {}
        if request.name is not None:
            body["name"] = request.name
        data = await self._put(f"/organizations/{request.company_id}", body)
        return mappers.to_company(data.get("data") or {})

    async def delete_company(self, company_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_COMPANY)
        await self._delete(f"/organizations/{company_id}")

    # ── Deals ─────────────────────────────────────────────────────────────────

    def list_deals(self, request: ListDealsRequest) -> AsyncIterator[Deal]:
        self._require_capability(CrmCapability.LIST_DEALS)
        return self._iter_deals(request)

    async def _iter_deals(self, request: ListDealsRequest) -> AsyncGenerator[Deal, None]:
        params: dict[str, Any] = {"limit": request.page_size or 100}
        if request.stage:
            from omnidapter.providers.pipedrive.mappers import _STAGE_TO_PD_STATUS

            params["status"] = _STAGE_TO_PD_STATUS.get(request.stage, "open")
        async for item in self._paginate("/deals", params):
            yield mappers.to_deal(item)

    async def get_deal(self, deal_id: str) -> Deal:
        self._require_capability(CrmCapability.GET_DEAL)
        data = await self._get(f"/deals/{deal_id}")
        return mappers.to_deal(data.get("data") or {})

    async def create_deal(self, request: CreateDealRequest) -> Deal:
        self._require_capability(CrmCapability.CREATE_DEAL)
        from omnidapter.providers.pipedrive.mappers import _STAGE_TO_PD_STATUS

        body: dict[str, Any] = {"title": request.name}
        if request.stage:
            body["status"] = _STAGE_TO_PD_STATUS.get(request.stage, "open")
        if request.stage_id:
            body["stage_id"] = int(request.stage_id)
        if request.value:
            body["value"] = float(request.value)
        if request.currency:
            body["currency"] = request.currency
        if request.contact_id:
            body["person_id"] = int(request.contact_id)
        if request.company_id:
            body["org_id"] = int(request.company_id)
        if request.owner_id:
            body["user_id"] = int(request.owner_id)
        data = await self._post("/deals", body)
        return mappers.to_deal(data.get("data") or {})

    async def update_deal(self, request: UpdateDealRequest) -> Deal:
        self._require_capability(CrmCapability.UPDATE_DEAL)
        from omnidapter.providers.pipedrive.mappers import _STAGE_TO_PD_STATUS

        body: dict[str, Any] = {}
        if request.name is not None:
            body["title"] = request.name
        if request.stage is not None:
            body["status"] = _STAGE_TO_PD_STATUS.get(request.stage, "open")
        if request.stage_id is not None:
            body["stage_id"] = int(request.stage_id)
        if request.value is not None:
            body["value"] = float(request.value)
        if request.notes is not None:
            body["visible_to"] = "3"
        data = await self._put(f"/deals/{request.deal_id}", body)
        return mappers.to_deal(data.get("data") or {})

    async def delete_deal(self, deal_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_DEAL)
        await self._delete(f"/deals/{deal_id}")

    # ── Activities (Notes + Activities) ───────────────────────────────────────

    def list_activities(self, request: ListActivitiesRequest) -> AsyncIterator[Activity]:
        self._require_capability(CrmCapability.LIST_ACTIVITIES)
        return self._iter_activities(request)

    async def _iter_activities(
        self, request: ListActivitiesRequest
    ) -> AsyncGenerator[Activity, None]:
        limit = request.page_size or 100
        note_params: dict[str, Any] = {"limit": limit}
        if request.contact_id:
            note_params["person_id"] = int(request.contact_id)
        if request.deal_id:
            note_params["deal_id"] = int(request.deal_id)
        async for item in self._paginate("/notes", note_params):
            yield mappers.to_note_activity(item)

        act_params: dict[str, Any] = {"limit": limit}
        if request.contact_id:
            act_params["person_id"] = int(request.contact_id)
        if request.deal_id:
            act_params["deal_id"] = int(request.deal_id)
        async for item in self._paginate("/activities", act_params):
            yield mappers.to_activity(item)

    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        from omnidapter.services.crm.models import ActivityKind

        self._require_capability(CrmCapability.CREATE_ACTIVITY)
        if request.kind == ActivityKind.NOTE:
            body: dict[str, Any] = {"content": request.body or request.subject or ""}
            if request.contact_id:
                body["person_id"] = int(request.contact_id)
            if request.company_id:
                body["org_id"] = int(request.company_id)
            if request.deal_id:
                body["deal_id"] = int(request.deal_id)
            data = await self._post("/notes", body)
            return mappers.to_note_activity(data.get("data") or {})
        else:
            from omnidapter.providers.pipedrive.mappers import _PD_ACTIVITY_KIND

            kind_to_type = {v: k for k, v in _PD_ACTIVITY_KIND.items()}
            act_type = kind_to_type.get(request.kind, "task")
            body = {
                "subject": request.subject or request.kind.value.title(),
                "type": act_type,
                "note": request.body or "",
                "done": 1,
            }
            if request.contact_id:
                body["person_id"] = int(request.contact_id)
            if request.company_id:
                body["org_id"] = int(request.company_id)
            if request.deal_id:
                body["deal_id"] = int(request.deal_id)
            if request.occurred_at:
                body["due_date"] = request.occurred_at.date().isoformat()
                body["due_time"] = request.occurred_at.strftime("%H:%M")
            data = await self._post("/activities", body)
            return mappers.to_activity(data.get("data") or {})

    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.UPDATE_ACTIVITY)
        for endpoint, mapper_fn, body_key in (
            ("/notes", mappers.to_note_activity, "content"),
            ("/activities", mappers.to_activity, "note"),
        ):
            try:
                body: dict[str, Any] = {}
                if request.body is not None:
                    body[body_key] = request.body
                if request.subject is not None and endpoint == "/activities":
                    body["subject"] = request.subject
                data = await self._put(f"{endpoint}/{request.activity_id}", body)
                return mapper_fn(data.get("data") or {})
            except Exception:  # noqa: BLE001
                continue
        data = await self._get(f"/notes/{request.activity_id}")
        return mappers.to_note_activity(data.get("data") or {})

    async def delete_activity(self, activity_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_ACTIVITY)
        for endpoint in ("/notes", "/activities"):
            try:
                await self._delete(f"{endpoint}/{activity_id}")
                return
            except Exception:  # noqa: BLE001
                continue
