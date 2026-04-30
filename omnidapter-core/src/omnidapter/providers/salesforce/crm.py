"""Salesforce CRM service implementation."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError
from omnidapter.providers.salesforce import mappers
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
from omnidapter.transport.correlation import new_correlation_id
from omnidapter.transport.retry import RetryPolicy

_SF_API_VERSION = "v60.0"
_SF_DEFAULT_BASE = "https://login.salesforce.com"

_SF_CRM_CAPABILITIES = frozenset(
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
        CrmCapability.TAGS,
    }
)

_CONTACT_FIELDS = "Id,FirstName,LastName,Name,Email,Phone,MobilePhone,AccountId,Description"
_ACCOUNT_FIELDS = "Id,Name,Website,Industry,Phone,Email__c"
_OPP_FIELDS = (
    "Id,Name,StageName,Amount,CurrencyIsoCode,AccountId,ContactId,OwnerId,CloseDate,Description"
)
_TASK_FIELDS = "Id,Subject,Description,ActivityDateTime,CreatedDate,WhoId,WhatId,ActivityType"
_EVENT_FIELDS = "Id,Subject,Description,ActivityDateTime,CreatedDate,WhoId,WhatId"


class SalesforceCrmService(CrmService):
    """Salesforce REST API CRM service."""

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
            provider_key="salesforce",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CrmCapability]:
        return _SF_CRM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "salesforce"

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
        instance_url = config.get("instance_url") or _SF_DEFAULT_BASE
        return f"{instance_url}/services/data/{_SF_API_VERSION}"

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

    async def _patch(self, path: str, body: dict[str, Any]) -> None:
        await self._http.request(
            "PATCH",
            f"{self._base_url()}{path}",
            headers=await self._auth_headers(),
            json=body,
        )

    async def _delete(self, path: str) -> None:
        await self._http.request(
            "DELETE",
            f"{self._base_url()}{path}",
            headers=await self._auth_headers(),
        )

    async def _soql(self, query: str) -> list[dict]:
        data = await self._get("/query", {"q": query})
        if isinstance(data, dict) and "error" in data:
            raise ProviderAPIError(
                f"Salesforce SOQL error: {data['error']}",
                provider_key="salesforce",
                response_body=str(data),
                correlation_id=new_correlation_id(),
            )
        records: list[dict] = []
        if isinstance(data, dict):
            records = data.get("records") or []
            next_url = data.get("nextRecordsUrl")
            while next_url:
                resp = await self._http.request(
                    "GET",
                    f"{(self._stored.provider_config or {}).get('instance_url', _SF_DEFAULT_BASE)}{next_url}",
                    headers=await self._auth_headers(),
                )
                page = resp.json()
                records.extend(page.get("records") or [])
                next_url = page.get("nextRecordsUrl")
        return records

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        self._require_capability(CrmCapability.LIST_CONTACTS)
        return self._iter_contacts(request)

    async def _iter_contacts(self, request: ListContactsRequest) -> AsyncGenerator[Contact, None]:
        where = ""
        if request.search:
            safe = request.search.replace("'", "\\'")
            where = f" WHERE Name LIKE '%{safe}%'"
        elif request.company_id:
            where = f" WHERE AccountId = '{request.company_id}'"
        limit = request.page_size or 200
        records = await self._soql(f"SELECT {_CONTACT_FIELDS} FROM Contact{where} LIMIT {limit}")
        for r in records:
            yield mappers.to_contact(r)

    async def get_contact(self, contact_id: str) -> Contact:
        self._require_capability(CrmCapability.GET_CONTACT)
        data = await self._get(f"/sobjects/Contact/{contact_id}")
        return mappers.to_contact(data)

    async def create_contact(self, request: CreateContactRequest) -> Contact:
        self._require_capability(CrmCapability.CREATE_CONTACT)
        body: dict[str, Any] = {}
        if request.first_name:
            body["FirstName"] = request.first_name
        if request.last_name:
            body["LastName"] = request.last_name
        if request.emails:
            body["Email"] = request.emails[0].address
        if request.phones:
            body["Phone"] = request.phones[0].number
        if request.company_id:
            body["AccountId"] = request.company_id
        if request.notes:
            body["Description"] = request.notes
        result = await self._post("/sobjects/Contact/", body)
        return await self.get_contact(result["id"])

    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        self._require_capability(CrmCapability.UPDATE_CONTACT)
        body: dict[str, Any] = {}
        if request.first_name is not None:
            body["FirstName"] = request.first_name
        if request.last_name is not None:
            body["LastName"] = request.last_name
        if request.emails is not None:
            body["Email"] = request.emails[0].address if request.emails else None
        if request.phones is not None:
            body["Phone"] = request.phones[0].number if request.phones else None
        if request.notes is not None:
            body["Description"] = request.notes
        await self._patch(f"/sobjects/Contact/{request.contact_id}", body)
        return await self.get_contact(request.contact_id)

    async def delete_contact(self, contact_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_CONTACT)
        await self._delete(f"/sobjects/Contact/{contact_id}")

    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        self._require_capability(CrmCapability.SEARCH_CONTACTS)
        safe = query.replace("'", "\\'")
        records = await self._soql(
            f"SELECT {_CONTACT_FIELDS} FROM Contact WHERE Name LIKE '%{safe}%' LIMIT {limit}"
        )
        return [mappers.to_contact(r) for r in records]

    # ── Companies (Accounts) ──────────────────────────────────────────────────

    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        self._require_capability(CrmCapability.LIST_COMPANIES)
        return self._iter_companies(request)

    async def _iter_companies(self, request: ListCompaniesRequest) -> AsyncGenerator[Company, None]:
        where = ""
        if request.search:
            safe = request.search.replace("'", "\\'")
            where = f" WHERE Name LIKE '%{safe}%'"
        limit = request.page_size or 200
        records = await self._soql(f"SELECT {_ACCOUNT_FIELDS} FROM Account{where} LIMIT {limit}")
        for r in records:
            yield mappers.to_company(r)

    async def get_company(self, company_id: str) -> Company:
        self._require_capability(CrmCapability.GET_COMPANY)
        data = await self._get(f"/sobjects/Account/{company_id}")
        return mappers.to_company(data)

    async def create_company(self, request: CreateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.CREATE_COMPANY)
        body: dict[str, Any] = {"Name": request.name}
        if request.website:
            body["Website"] = request.website
        if request.industry:
            body["Industry"] = request.industry
        if request.phone:
            body["Phone"] = request.phone
        result = await self._post("/sobjects/Account/", body)
        return await self.get_company(result["id"])

    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.UPDATE_COMPANY)
        body: dict[str, Any] = {}
        if request.name is not None:
            body["Name"] = request.name
        if request.website is not None:
            body["Website"] = request.website
        if request.industry is not None:
            body["Industry"] = request.industry
        if request.phone is not None:
            body["Phone"] = request.phone
        await self._patch(f"/sobjects/Account/{request.company_id}", body)
        return await self.get_company(request.company_id)

    async def delete_company(self, company_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_COMPANY)
        await self._delete(f"/sobjects/Account/{company_id}")

    # ── Deals (Opportunities) ─────────────────────────────────────────────────

    def list_deals(self, request: ListDealsRequest) -> AsyncIterator[Deal]:
        self._require_capability(CrmCapability.LIST_DEALS)
        return self._iter_deals(request)

    async def _iter_deals(self, request: ListDealsRequest) -> AsyncGenerator[Deal, None]:
        where_parts: list[str] = []
        if request.contact_id:
            where_parts.append(f"ContactId = '{request.contact_id}'")
        if request.company_id:
            where_parts.append(f"AccountId = '{request.company_id}'")
        if request.owner_id:
            where_parts.append(f"OwnerId = '{request.owner_id}'")
        if request.stage:
            sf_label = mappers.stage_to_sf_label(request.stage)
            where_parts.append(f"StageName = '{sf_label}'")
        where = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        limit = request.page_size or 200
        records = await self._soql(f"SELECT {_OPP_FIELDS} FROM Opportunity{where} LIMIT {limit}")
        for r in records:
            yield mappers.to_deal(r)

    async def get_deal(self, deal_id: str) -> Deal:
        self._require_capability(CrmCapability.GET_DEAL)
        data = await self._get(f"/sobjects/Opportunity/{deal_id}")
        return mappers.to_deal(data)

    async def create_deal(self, request: CreateDealRequest) -> Deal:
        self._require_capability(CrmCapability.CREATE_DEAL)
        stage_label = request.stage_id or (
            mappers.stage_to_sf_label(request.stage) if request.stage else "Prospecting"
        )
        body: dict[str, Any] = {
            "Name": request.name,
            "StageName": stage_label,
            "CloseDate": (
                request.close_date.date().isoformat() if request.close_date else "2099-12-31"
            ),
        }
        if request.value:
            body["Amount"] = float(request.value)
        if request.company_id:
            body["AccountId"] = request.company_id
        if request.contact_id:
            body["ContactId"] = request.contact_id
        if request.owner_id:
            body["OwnerId"] = request.owner_id
        if request.notes:
            body["Description"] = request.notes
        result = await self._post("/sobjects/Opportunity/", body)
        return await self.get_deal(result["id"])

    async def update_deal(self, request: UpdateDealRequest) -> Deal:
        self._require_capability(CrmCapability.UPDATE_DEAL)
        body: dict[str, Any] = {}
        if request.name is not None:
            body["Name"] = request.name
        if request.stage is not None:
            body["StageName"] = mappers.stage_to_sf_label(request.stage)
        if request.stage_id is not None:
            body["StageName"] = request.stage_id
        if request.value is not None:
            body["Amount"] = float(request.value)
        if request.close_date is not None:
            body["CloseDate"] = request.close_date.date().isoformat()
        if request.notes is not None:
            body["Description"] = request.notes
        await self._patch(f"/sobjects/Opportunity/{request.deal_id}", body)
        return await self.get_deal(request.deal_id)

    async def delete_deal(self, deal_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_DEAL)
        await self._delete(f"/sobjects/Opportunity/{deal_id}")

    # ── Activities (Tasks + Events) ───────────────────────────────────────────

    def list_activities(self, request: ListActivitiesRequest) -> AsyncIterator[Activity]:
        self._require_capability(CrmCapability.LIST_ACTIVITIES)
        return self._iter_activities(request)

    async def _iter_activities(
        self, request: ListActivitiesRequest
    ) -> AsyncGenerator[Activity, None]:
        where_parts: list[str] = []
        if request.contact_id:
            where_parts.append(f"WhoId = '{request.contact_id}'")
        if request.company_id:
            where_parts.append(f"AccountId = '{request.company_id}'")
        if request.deal_id:
            where_parts.append(f"WhatId = '{request.deal_id}'")
        where = f" WHERE {' AND '.join(where_parts)}" if where_parts else ""
        limit = request.page_size or 200
        tasks = await self._soql(f"SELECT {_TASK_FIELDS} FROM Task{where} LIMIT {limit}")
        for t in tasks:
            yield mappers.to_activity(t, kind=None)  # type: ignore[arg-type]
        events = await self._soql(f"SELECT {_EVENT_FIELDS} FROM Event{where} LIMIT {limit}")
        for e in events:
            yield mappers.to_activity(e, kind=None)  # type: ignore[arg-type]

    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        from omnidapter.services.crm.models import ActivityKind

        self._require_capability(CrmCapability.CREATE_ACTIVITY)
        if request.kind in (ActivityKind.CALL, ActivityKind.MEETING):
            obj = "Event"
            body: dict[str, Any] = {
                "Subject": request.subject or request.kind.value.title(),
                "Description": request.body or "",
                "ActivityDateTime": (
                    request.occurred_at.isoformat() if request.occurred_at else None
                ),
                "DurationInMinutes": 30,
            }
        else:
            obj = "Task"
            body = {
                "Subject": request.subject or request.kind.value.title(),
                "Description": request.body or "",
                "ActivityDate": (
                    request.occurred_at.date().isoformat() if request.occurred_at else None
                ),
                "Status": "Completed",
                "Priority": "Normal",
            }
        if request.contact_id:
            body["WhoId"] = request.contact_id
        if request.deal_id:
            body["WhatId"] = request.deal_id
        result = await self._post(f"/sobjects/{obj}/", body)
        data = await self._get(f"/sobjects/{obj}/{result['id']}")
        return mappers.to_activity(data)

    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.UPDATE_ACTIVITY)
        body: dict[str, Any] = {}
        if request.subject is not None:
            body["Subject"] = request.subject
        if request.body is not None:
            body["Description"] = request.body
        if request.occurred_at is not None:
            body["ActivityDateTime"] = request.occurred_at.isoformat()
        for obj in ("Task", "Event"):
            try:
                await self._patch(f"/sobjects/{obj}/{request.activity_id}", body)
                data = await self._get(f"/sobjects/{obj}/{request.activity_id}")
                return mappers.to_activity(data)
            except Exception:  # noqa: BLE001
                continue
        data = await self._get(f"/sobjects/Task/{request.activity_id}")
        return mappers.to_activity(data)

    async def delete_activity(self, activity_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_ACTIVITY)
        for obj in ("Task", "Event"):
            try:
                await self._delete(f"/sobjects/{obj}/{activity_id}")
                return
            except Exception:  # noqa: BLE001
                continue
