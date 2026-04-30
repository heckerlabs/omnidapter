"""Jobber CRM service implementation (GraphQL)."""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator
from typing import Any

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError
from omnidapter.providers.jobber import mappers
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

JOBBER_GRAPHQL_URL = "https://api.getjobber.com/api/graphql"
_JOBBER_VERSION = "2024-01-01"

_JOBBER_CRM_CAPABILITIES = frozenset(
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
        CrmCapability.LIST_ACTIVITIES,
        CrmCapability.CREATE_ACTIVITY,
        CrmCapability.UPDATE_ACTIVITY,
        CrmCapability.DELETE_ACTIVITY,
    }
)


class JobberCrmService(CrmService):
    """Jobber GraphQL API CRM service."""

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
            provider_key="jobber",
            retry_policy=retry_policy,
            hooks=hooks,
            default_headers={"X-JOBBER-GRAPHQL-VERSION": _JOBBER_VERSION},
        )

    @property
    def capabilities(self) -> frozenset[CrmCapability]:
        return _JOBBER_CRM_CAPABILITIES

    @property
    def _provider_key(self) -> str:
        return "jobber"

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

    async def _graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"query": query}
        if variables:
            body["variables"] = variables
        resp = await self._http.request(
            "POST",
            JOBBER_GRAPHQL_URL,
            headers=await self._auth_headers(),
            json=body,
        )
        result = resp.json()
        if errors := result.get("errors"):
            raise ProviderAPIError(
                f"Jobber GraphQL error: {errors[0].get('message', 'Unknown error')}",
                provider_key="jobber",
                response_body=str(errors),
                correlation_id=new_correlation_id(),
            )
        return result.get("data") or {}

    # ── Contacts ──────────────────────────────────────────────────────────────

    _CLIENTS_QUERY = """
    query($filter: ClientFilterAttributes, $first: Int, $after: String) {
      clients(filter: $filter, first: $first, after: $after) {
        nodes {
          id name companyName isCompany
          emails { address }
          phones { number description }
        }
        pageInfo { hasNextPage endCursor }
      }
    }
    """

    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        self._require_capability(CrmCapability.LIST_CONTACTS)
        return self._iter_contacts(request)

    async def _iter_contacts(self, request: ListContactsRequest) -> AsyncGenerator[Contact, None]:
        cursor: str | None = None
        while True:
            filt: dict[str, Any] = {}
            if request.search:
                filt["searchTerm"] = request.search
            variables: dict[str, Any] = {"filter": filt, "first": request.page_size or 50}
            if cursor:
                variables["after"] = cursor
            data = await self._graphql(self._CLIENTS_QUERY, variables)
            nodes = (data.get("clients") or {}).get("nodes") or []
            page_info = (data.get("clients") or {}).get("pageInfo") or {}
            for node in nodes:
                if not (node.get("isCompany") or node.get("companyName")):
                    yield mappers.to_crm_contact(node)
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

    async def get_contact(self, contact_id: str) -> Contact:
        self._require_capability(CrmCapability.GET_CONTACT)
        query = """
        query($id: EncodedId!) {
          client(id: $id) {
            id name companyName isCompany
            emails { address }
            phones { number description }
          }
        }
        """
        data = await self._graphql(query, {"id": contact_id})
        return mappers.to_crm_contact(data.get("client") or {})

    async def create_contact(self, request: CreateContactRequest) -> Contact:
        self._require_capability(CrmCapability.CREATE_CONTACT)
        mutation = """
        mutation($input: ClientCreateInput!) {
          clientCreate(input: $input) {
            client {
              id name companyName isCompany
              emails { address }
              phones { number description }
            }
          }
        }
        """
        inp: dict[str, Any] = {}
        if request.first_name or request.last_name:
            inp["firstName"] = request.first_name or ""
            inp["lastName"] = request.last_name or ""
        if request.emails:
            inp["emails"] = [
                {"address": e.address, "description": e.label or "MAIN"} for e in request.emails
            ]
        if request.phones:
            inp["phones"] = [
                {"number": p.number, "description": p.label or "MAIN"} for p in request.phones
            ]
        if request.notes:
            inp["notes"] = request.notes
        data = await self._graphql(mutation, {"input": inp})
        return mappers.to_crm_contact((data.get("clientCreate") or {}).get("client") or {})

    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        self._require_capability(CrmCapability.UPDATE_CONTACT)
        mutation = """
        mutation($id: EncodedId!, $input: ClientEditInput!) {
          clientEdit(id: $id, input: $input) {
            client {
              id name companyName isCompany
              emails { address }
              phones { number description }
            }
          }
        }
        """
        inp: dict[str, Any] = {}
        if request.first_name is not None:
            inp["firstName"] = request.first_name
        if request.last_name is not None:
            inp["lastName"] = request.last_name
        if request.emails is not None:
            inp["emails"] = [
                {"address": e.address, "description": e.label or "MAIN"} for e in request.emails
            ]
        if request.phones is not None:
            inp["phones"] = [
                {"number": p.number, "description": p.label or "MAIN"} for p in request.phones
            ]
        if request.notes is not None:
            inp["notes"] = request.notes
        data = await self._graphql(mutation, {"id": request.contact_id, "input": inp})
        return mappers.to_crm_contact((data.get("clientEdit") or {}).get("client") or {})

    async def delete_contact(self, contact_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_CONTACT)
        mutation = """
        mutation($id: EncodedId!) {
          clientArchive(id: $id) { archivedClient { id } }
        }
        """
        await self._graphql(mutation, {"id": contact_id})

    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        self._require_capability(CrmCapability.SEARCH_CONTACTS)
        gql = """
        query($filter: ClientFilterAttributes, $first: Int) {
          clients(filter: $filter, first: $first) {
            nodes {
              id name companyName isCompany
              emails { address }
              phones { number description }
            }
          }
        }
        """
        data = await self._graphql(gql, {"filter": {"searchTerm": query}, "first": limit})
        nodes = (data.get("clients") or {}).get("nodes") or []
        return [mappers.to_crm_contact(n) for n in nodes if not n.get("isCompany")]

    # ── Companies ─────────────────────────────────────────────────────────────

    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        self._require_capability(CrmCapability.LIST_COMPANIES)
        return self._iter_companies(request)

    async def _iter_companies(self, request: ListCompaniesRequest) -> AsyncGenerator[Company, None]:
        cursor: str | None = None
        while True:
            filt: dict[str, Any] = {}
            if request.search:
                filt["searchTerm"] = request.search
            variables: dict[str, Any] = {"filter": filt, "first": request.page_size or 50}
            if cursor:
                variables["after"] = cursor
            data = await self._graphql(self._CLIENTS_QUERY, variables)
            nodes = (data.get("clients") or {}).get("nodes") or []
            page_info = (data.get("clients") or {}).get("pageInfo") or {}
            for node in nodes:
                if node.get("isCompany") or node.get("companyName"):
                    yield mappers.to_crm_company(node)
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")

    async def get_company(self, company_id: str) -> Company:
        self._require_capability(CrmCapability.GET_COMPANY)
        query = """
        query($id: EncodedId!) {
          client(id: $id) {
            id name companyName isCompany
            emails { address }
            phones { number description }
          }
        }
        """
        data = await self._graphql(query, {"id": company_id})
        return mappers.to_crm_company(data.get("client") or {})

    async def create_company(self, request: CreateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.CREATE_COMPANY)
        mutation = """
        mutation($input: ClientCreateInput!) {
          clientCreate(input: $input) {
            client {
              id name companyName isCompany
              emails { address }
              phones { number description }
            }
          }
        }
        """
        inp: dict[str, Any] = {"companyName": request.name, "isCompany": True}
        if request.email:
            inp["emails"] = [{"address": request.email, "description": "MAIN"}]
        if request.phone:
            inp["phones"] = [{"number": request.phone, "description": "MAIN"}]
        data = await self._graphql(mutation, {"input": inp})
        return mappers.to_crm_company((data.get("clientCreate") or {}).get("client") or {})

    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        self._require_capability(CrmCapability.UPDATE_COMPANY)
        mutation = """
        mutation($id: EncodedId!, $input: ClientEditInput!) {
          clientEdit(id: $id, input: $input) {
            client {
              id name companyName isCompany
              emails { address }
              phones { number description }
            }
          }
        }
        """
        inp: dict[str, Any] = {}
        if request.name is not None:
            inp["companyName"] = request.name
        if request.email is not None:
            inp["emails"] = [{"address": request.email, "description": "MAIN"}]
        if request.phone is not None:
            inp["phones"] = [{"number": request.phone, "description": "MAIN"}]
        data = await self._graphql(mutation, {"id": request.company_id, "input": inp})
        return mappers.to_crm_company((data.get("clientEdit") or {}).get("client") or {})

    async def delete_company(self, company_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_COMPANY)
        mutation = """
        mutation($id: EncodedId!) {
          clientArchive(id: $id) { archivedClient { id } }
        }
        """
        await self._graphql(mutation, {"id": company_id})

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
        query = """
        query($filter: NoteFilterAttributes, $first: Int) {
          notes(filter: $filter, first: $first) {
            nodes { id note createdAt client { id } }
            pageInfo { hasNextPage endCursor }
          }
        }
        """
        filt: dict[str, Any] = {}
        if request.contact_id:
            filt["clientId"] = request.contact_id
        elif request.company_id:
            filt["clientId"] = request.company_id
        data = await self._graphql(query, {"filter": filt, "first": request.page_size or 50})
        nodes = (data.get("notes") or {}).get("nodes") or []
        for node in nodes:
            yield mappers.to_crm_activity(node)

    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.CREATE_ACTIVITY)
        mutation = """
        mutation($input: NoteCreateInput!) {
          noteCreate(input: $input) {
            note { id note createdAt client { id } }
          }
        }
        """
        inp: dict[str, Any] = {"note": request.body or request.subject or ""}
        if request.contact_id:
            inp["clientId"] = request.contact_id
        elif request.company_id:
            inp["clientId"] = request.company_id
        data = await self._graphql(mutation, {"input": inp})
        return mappers.to_crm_activity((data.get("noteCreate") or {}).get("note") or {})

    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        self._require_capability(CrmCapability.UPDATE_ACTIVITY)
        mutation = """
        mutation($id: EncodedId!, $input: NoteEditInput!) {
          noteEdit(id: $id, input: $input) {
            note { id note createdAt client { id } }
          }
        }
        """
        inp: dict[str, Any] = {}
        if request.body is not None:
            inp["note"] = request.body
        data = await self._graphql(mutation, {"id": request.activity_id, "input": inp})
        return mappers.to_crm_activity((data.get("noteEdit") or {}).get("note") or {})

    async def delete_activity(self, activity_id: str) -> None:
        self._require_capability(CrmCapability.DELETE_ACTIVITY)
        mutation = """
        mutation($id: EncodedId!) {
          noteDelete(id: $id) { deletedNote { id } }
        }
        """
        await self._graphql(mutation, {"id": activity_id})
