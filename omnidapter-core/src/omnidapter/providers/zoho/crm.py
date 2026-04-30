"""Zoho CRM service implementation."""

from __future__ import annotations

import contextlib
from collections.abc import AsyncGenerator, AsyncIterator
from datetime import datetime
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.services.crm.capabilities import CrmCapability
from omnidapter.services.crm.interface import CrmService
from omnidapter.services.crm.models import (
    Activity,
    ActivityKind,
    Company,
    Contact,
    ContactEmail,
    ContactPhone,
    Deal,
    DealStage,
)
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

_ZOHO_CRM_BASE = "https://www.zohoapis.com/crm/v6"

_ZOHO_CRM_CAPABILITIES = frozenset(
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

_ZOHO_STAGE_MAP: dict[str, DealStage] = {
    "qualification": DealStage.LEAD,
    "needs analysis": DealStage.QUALIFIED,
    "value proposition": DealStage.PROPOSAL,
    "id. decision makers": DealStage.PROPOSAL,
    "perception analysis": DealStage.PROPOSAL,
    "proposal/price quote": DealStage.PROPOSAL,
    "negotiation/review": DealStage.NEGOTIATION,
    "closed won": DealStage.CLOSED_WON,
    "closed lost": DealStage.CLOSED_LOST,
}

_DEAL_STAGE_TO_ZOHO: dict[DealStage, str] = {
    DealStage.LEAD: "Qualification",
    DealStage.QUALIFIED: "Needs Analysis",
    DealStage.PROPOSAL: "Proposal/Price Quote",
    DealStage.NEGOTIATION: "Negotiation/Review",
    DealStage.CLOSED_WON: "Closed Won",
    DealStage.CLOSED_LOST: "Closed Lost",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError, TypeError):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    return None


def _to_contact(data: dict) -> Contact:
    emails = []
    if data.get("Email"):
        emails = [ContactEmail(address=data["Email"])]
    phones = []
    if data.get("Phone"):
        phones.append(ContactPhone(number=data["Phone"], label="work"))
    if data.get("Mobile"):
        phones.append(ContactPhone(number=data["Mobile"], label="mobile"))
    name = data.get("Full_Name") or (
        f"{data.get('First_Name', '')} {data.get('Last_Name', '')}".strip() or None
    )
    account = data.get("Account_Name") or {}
    return Contact(
        id=str(data.get("id", "")),
        first_name=data.get("First_Name") or None,
        last_name=data.get("Last_Name") or None,
        name=name,
        emails=emails,
        phones=phones,
        company_id=str(account["id"]) if isinstance(account, dict) and account.get("id") else None,
        company_name=account.get("name") if isinstance(account, dict) else None,
        tags=data.get("Tag") or [],
        notes=data.get("Description") or None,
        provider_data=data,
    )


def _to_company(data: dict) -> Company:
    return Company(
        id=str(data.get("id", "")),
        name=data.get("Account_Name") or "",
        website=data.get("Website") or None,
        industry=data.get("Industry") or None,
        phone=data.get("Phone") or None,
        email=data.get("Email") or None,
        provider_data=data,
    )


def _to_deal(data: dict) -> Deal:
    stage_raw = data.get("Stage") or ""
    stage = _ZOHO_STAGE_MAP.get(stage_raw.lower())
    stage_label = stage_raw if stage is None else None
    amount = data.get("Amount")
    account = data.get("Account_Name") or {}
    contact = data.get("Contact_Name") or {}
    owner = data.get("Owner") or {}
    return Deal(
        id=str(data.get("id", "")),
        name=data.get("Deal_Name") or "",
        stage=stage,
        stage_label=stage_label,
        value=str(amount) if amount is not None else None,
        currency=data.get("Currency") or None,
        contact_id=str(contact["id"]) if isinstance(contact, dict) and contact.get("id") else None,
        company_id=str(account["id"]) if isinstance(account, dict) and account.get("id") else None,
        owner_id=str(owner["id"]) if isinstance(owner, dict) and owner.get("id") else None,
        close_date=_parse_dt(data.get("Closing_Date")),
        notes=data.get("Description") or None,
        provider_data=data,
    )


def _to_activity(data: dict) -> Activity:
    parent = data.get("Parent_Id") or {}
    parent_module = data.get("se_module") or ""
    contact_id = (
        str(parent["id"])
        if isinstance(parent, dict) and parent_module == "Contacts" and parent.get("id")
        else None
    )
    company_id = (
        str(parent["id"])
        if isinstance(parent, dict) and parent_module == "Accounts" and parent.get("id")
        else None
    )
    deal_id = (
        str(parent["id"])
        if isinstance(parent, dict) and parent_module == "Deals" and parent.get("id")
        else None
    )
    return Activity(
        id=str(data.get("id", "")),
        kind=ActivityKind.NOTE,
        subject=data.get("Note_Title") or None,
        body=data.get("Note_Content") or None,
        contact_id=contact_id,
        company_id=company_id,
        deal_id=deal_id,
        occurred_at=_parse_dt(data.get("Created_Time")),
        provider_data=data,
    )


class ZohoCrmService(CrmService):
    """Zoho CRM v6 service."""

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
            provider_key="zoho",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def capabilities(self) -> frozenset[CrmCapability]:
        return _ZOHO_CRM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "zoho"

    async def _resolve_stored_credential(self) -> StoredCredential:
        resolver = getattr(self, "_credential_resolver", None)
        if resolver is None:
            return self._stored
        self._stored = await resolver(self._connection_id)
        return self._stored

    async def _auth_headers(self) -> dict[str, str]:
        creds = (await self._resolve_stored_credential()).credentials
        if isinstance(creds, OAuth2Credentials):
            return {"Authorization": f"Zoho-oauthtoken {creds.access_token}"}
        return {}

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = await self._http.request(
            "GET",
            f"{_ZOHO_CRM_BASE}{path}",
            headers=await self._auth_headers(),
            params=params,
        )
        return resp.json()

    async def _post(self, path: str, records: list[dict]) -> Any:
        resp = await self._http.request(
            "POST",
            f"{_ZOHO_CRM_BASE}{path}",
            headers=await self._auth_headers(),
            json={"data": records},
        )
        return resp.json()

    async def _put(self, path: str, records: list[dict]) -> Any:
        resp = await self._http.request(
            "PUT",
            f"{_ZOHO_CRM_BASE}{path}",
            headers=await self._auth_headers(),
            json={"data": records},
        )
        return resp.json()

    async def _delete(self, path: str) -> None:
        await self._http.request(
            "DELETE",
            f"{_ZOHO_CRM_BASE}{path}",
            headers=await self._auth_headers(),
        )

    async def _paginate(self, module: str, params: dict[str, Any]) -> AsyncGenerator[dict, None]:
        page = 1
        while True:
            p = {**params, "page": page}
            data = await self._get(f"/{module}", p)
            records = data.get("data") or []
            for r in records:
                yield r
            info = data.get("info") or {}
            if not info.get("more_records"):
                break
            page += 1

    # ── Contacts ──────────────────────────────────────────────────────────────

    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        self._require_capability(CrmCapability.LIST_CONTACTS)
        return self._iter_contacts(request)

    async def _iter_contacts(self, request: ListContactsRequest) -> AsyncGenerator[Contact, None]:
        params: dict[str, Any] = {"per_page": request.page_size or 200}
        async for r in self._paginate("Contacts", params):
            yield _to_contact(r)

    async def get_contact(self, contact_id: str) -> Contact:
        self._require_capability(CrmCapability.GET_CONTACT)
        data = await self._get(f"/Contacts/{contact_id}")
        return _to_contact((data.get("data") or [{}])[0])

    async def create_contact(self, request: CreateContactRequest) -> Contact:
        self._require_capability(CrmCapability.CREATE_CONTACT)
        record: dict[str, Any] = {}
        if request.first_name:
            record["First_Name"] = request.first_name
        if request.last_name:
            record["Last_Name"] = request.last_name
        if request.emails:
            record["Email"] = request.emails[0].address
        if request.phones:
            record["Phone"] = request.phones[0].number
        if request.company_id:
            record["Account_Name"] = {"id": request.company_id}
        if request.notes:
            record["Description"] = request.notes
        result = await self._post("/Contacts", [record])
        new_id = (result.get("data") or [{}])[0].get("details", {}).get("id", "")
        return await self.get_contact(new_id)

    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        self._require_capability(CrmCapability.UPDATE_CONTACT)
        record: dict[str, Any] = {"id": request.contact_id}
        if request.first_name is not None:
            record["First_Name"] = request.first_name
        if request.last_name is not None:
            record["Last_Name"] = request.last_name
        if request.emails is not None:
            record["Email"] = request.emails[0].address if request.emails else None
        if request.phones is not None:
            record["Phone"] = request.phones[0].number if request.phones else None
        if request.notes is not None:
            record["Description"] = request.notes
        await self._put("/Contacts", [record])
        return await self.get_contact(request.contact_id)

    async def delete_contact(self, contact_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_CONTACT)
        await self._delete(f"/Contacts/{contact_id}")

    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        self._require_capability(CrmCapability.SEARCH_CONTACTS)
        data = await self._get("/Contacts/search", {"word": query, "per_page": limit})
        return [_to_contact(r) for r in (data.get("data") or [])]

    # ── Companies (Accounts) ──────────────────────────────────────────────────

    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        self._require_capability(CrmCapability.LIST_COMPANIES)
        return self._iter_companies(request)

    async def _iter_companies(self, request: ListCompaniesRequest) -> AsyncGenerator[Company, None]:
        params: dict[str, Any] = {"per_page": request.page_size or 200}
        async for r in self._paginate("Accounts", params):
            yield _to_company(r)

    async def get_company(self, company_id: str) -> Company:
        self._require_capability(CrmCapability.GET_COMPANY)
        data = await self._get(f"/Accounts/{company_id}")
        return _to_company((data.get("data") or [{}])[0])

    async def create_company(self, request: CreateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.CREATE_COMPANY)
        record: dict[str, Any] = {"Account_Name": request.name}
        if request.website:
            record["Website"] = request.website
        if request.industry:
            record["Industry"] = request.industry
        if request.phone:
            record["Phone"] = request.phone
        if request.email:
            record["Email"] = request.email
        result = await self._post("/Accounts", [record])
        new_id = (result.get("data") or [{}])[0].get("details", {}).get("id", "")
        return await self.get_company(new_id)

    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.UPDATE_COMPANY)
        record: dict[str, Any] = {"id": request.company_id}
        if request.name is not None:
            record["Account_Name"] = request.name
        if request.website is not None:
            record["Website"] = request.website
        if request.industry is not None:
            record["Industry"] = request.industry
        if request.phone is not None:
            record["Phone"] = request.phone
        if request.email is not None:
            record["Email"] = request.email
        await self._put("/Accounts", [record])
        return await self.get_company(request.company_id)

    async def delete_company(self, company_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_COMPANY)
        await self._delete(f"/Accounts/{company_id}")

    # ── Deals ─────────────────────────────────────────────────────────────────

    def list_deals(self, request: ListDealsRequest) -> AsyncIterator[Deal]:
        self._require_capability(CrmCapability.LIST_DEALS)
        return self._iter_deals(request)

    async def _iter_deals(self, request: ListDealsRequest) -> AsyncGenerator[Deal, None]:
        params: dict[str, Any] = {"per_page": request.page_size or 200}
        async for r in self._paginate("Deals", params):
            yield _to_deal(r)

    async def get_deal(self, deal_id: str) -> Deal:
        self._require_capability(CrmCapability.GET_DEAL)
        data = await self._get(f"/Deals/{deal_id}")
        return _to_deal((data.get("data") or [{}])[0])

    async def create_deal(self, request: CreateDealRequest) -> Deal:
        self._require_capability(CrmCapability.CREATE_DEAL)
        stage = (
            request.stage_id or _DEAL_STAGE_TO_ZOHO.get(request.stage, "Qualification")
            if request.stage
            else "Qualification"
        )
        record: dict[str, Any] = {
            "Deal_Name": request.name,
            "Stage": stage,
        }
        if request.value:
            record["Amount"] = float(request.value)
        if request.close_date:
            record["Closing_Date"] = request.close_date.date().isoformat()
        if request.company_id:
            record["Account_Name"] = {"id": request.company_id}
        if request.contact_id:
            record["Contact_Name"] = {"id": request.contact_id}
        if request.notes:
            record["Description"] = request.notes
        result = await self._post("/Deals", [record])
        new_id = (result.get("data") or [{}])[0].get("details", {}).get("id", "")
        return await self.get_deal(new_id)

    async def update_deal(self, request: UpdateDealRequest) -> Deal:
        self._require_capability(CrmCapability.UPDATE_DEAL)
        record: dict[str, Any] = {"id": request.deal_id}
        if request.name is not None:
            record["Deal_Name"] = request.name
        if request.stage is not None:
            record["Stage"] = _DEAL_STAGE_TO_ZOHO.get(request.stage, "Qualification")
        if request.stage_id is not None:
            record["Stage"] = request.stage_id
        if request.value is not None:
            record["Amount"] = float(request.value)
        if request.close_date is not None:
            record["Closing_Date"] = request.close_date.date().isoformat()
        if request.notes is not None:
            record["Description"] = request.notes
        await self._put("/Deals", [record])
        return await self.get_deal(request.deal_id)

    async def delete_deal(self, deal_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_DEAL)
        await self._delete(f"/Deals/{deal_id}")

    # ── Activities (Notes) ────────────────────────────────────────────────────

    def list_activities(self, request: ListActivitiesRequest) -> AsyncIterator[Activity]:
        self._require_capability(CrmCapability.LIST_ACTIVITIES)
        return self._iter_activities(request)

    async def _iter_activities(
        self, request: ListActivitiesRequest
    ) -> AsyncGenerator[Activity, None]:
        params: dict[str, Any] = {"per_page": request.page_size or 200}
        async for r in self._paginate("Notes", params):
            yield _to_activity(r)

    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.CREATE_ACTIVITY)
        record: dict[str, Any] = {
            "Note_Content": request.body or request.subject or "",
        }
        if request.subject:
            record["Note_Title"] = request.subject
        if request.contact_id:
            record["Parent_Id"] = {"id": request.contact_id}
            record["se_module"] = "Contacts"
        elif request.company_id:
            record["Parent_Id"] = {"id": request.company_id}
            record["se_module"] = "Accounts"
        elif request.deal_id:
            record["Parent_Id"] = {"id": request.deal_id}
            record["se_module"] = "Deals"
        result = await self._post("/Notes", [record])
        new_id = (result.get("data") or [{}])[0].get("details", {}).get("id", "")
        data = await self._get(f"/Notes/{new_id}")
        return _to_activity((data.get("data") or [{}])[0])

    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.UPDATE_ACTIVITY)
        record: dict[str, Any] = {"id": request.activity_id}
        if request.body is not None:
            record["Note_Content"] = request.body
        if request.subject is not None:
            record["Note_Title"] = request.subject
        await self._put("/Notes", [record])
        data = await self._get(f"/Notes/{request.activity_id}")
        return _to_activity((data.get("data") or [{}])[0])

    async def delete_activity(self, activity_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_ACTIVITY)
        await self._delete(f"/Notes/{activity_id}")
