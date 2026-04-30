"""Unit tests for JobberCrmService (GraphQL)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.jobber.crm import JobberCrmService
from omnidapter.services.crm.capabilities import CrmCapability
from omnidapter.services.crm.requests import (
    CreateActivityRequest,
    CreateCompanyRequest,
    CreateContactRequest,
    ListActivitiesRequest,
    ListCompaniesRequest,
    ListContactsRequest,
    UpdateActivityRequest,
    UpdateContactRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(token: str = "tok-123") -> StoredCredential:
    return StoredCredential(
        provider_key="jobber",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=token),
    )


def _make_service() -> tuple[JobberCrmService, AsyncMock]:
    svc = JobberCrmService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {}}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _gql_resp(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = {"data": data}
    return m


class TestCapabilities:
    def test_contacts_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.LIST_CONTACTS)
        assert svc.supports(CrmCapability.CREATE_CONTACT)
        assert svc.supports(CrmCapability.SEARCH_CONTACTS)

    def test_companies_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.LIST_COMPANIES)
        assert svc.supports(CrmCapability.CREATE_COMPANY)

    def test_deals_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(CrmCapability.LIST_DEALS)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert CrmCapability.WEBHOOKS not in svc.capabilities

    def test_provider_key(self):
        svc, _ = _make_service()
        assert svc._provider_key == "jobber"

    def test_unsupported_raises(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(CrmCapability.LIST_DEALS)


class TestListContacts:
    @pytest.mark.asyncio
    async def test_yields_individual_clients(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clients": {
                    "nodes": [
                        {
                            "id": "c1",
                            "name": "Alice Smith",
                            "isCompany": False,
                            "companyName": None,
                            "emails": [],
                            "phones": [],
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        )
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert len(items) == 1
        assert items[0].id == "c1"

    @pytest.mark.asyncio
    async def test_skips_company_clients(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clients": {
                    "nodes": [
                        {
                            "id": "c1",
                            "name": "Acme Corp",
                            "isCompany": True,
                            "companyName": "Acme Corp",
                            "emails": [],
                            "phones": [],
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        )
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert items == []


class TestGetContact:
    @pytest.mark.asyncio
    async def test_returns_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "client": {
                    "id": "c1",
                    "name": "Bob",
                    "isCompany": False,
                    "companyName": None,
                    "emails": [],
                    "phones": [],
                }
            }
        )
        contact = await svc.get_contact("c1")
        assert contact.id == "c1"


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_calls_mutation(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clientCreate": {
                    "client": {
                        "id": "new",
                        "name": "Eve Adams",
                        "isCompany": False,
                        "companyName": None,
                        "emails": [],
                        "phones": [],
                    }
                }
            }
        )
        contact = await svc.create_contact(
            CreateContactRequest(first_name="Eve", last_name="Adams")
        )
        assert contact.id == "new"
        body = mock_req.call_args.kwargs["json"]
        assert "clientCreate" in body["query"]


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_calls_edit_mutation(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clientEdit": {
                    "client": {
                        "id": "c1",
                        "name": "Updated",
                        "isCompany": False,
                        "companyName": None,
                        "emails": [],
                        "phones": [],
                    }
                }
            }
        )
        contact = await svc.update_contact(
            UpdateContactRequest(contact_id="c1", first_name="Updated")
        )
        assert contact.id == "c1"


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_calls_archive_mutation(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp({"clientArchive": {"archivedClient": {"id": "c1"}}})
        await svc.delete_contact("c1")
        body = mock_req.call_args.kwargs["json"]
        assert "clientArchive" in body["query"]


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_returns_individual_clients(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clients": {
                    "nodes": [
                        {
                            "id": "c2",
                            "name": "Carol",
                            "isCompany": False,
                            "companyName": None,
                            "emails": [],
                            "phones": [],
                        }
                    ]
                }
            }
        )
        results = await svc.search_contacts("Carol")
        assert len(results) == 1


class TestListCompanies:
    @pytest.mark.asyncio
    async def test_yields_company_clients(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clients": {
                    "nodes": [
                        {
                            "id": "co1",
                            "name": "Acme Corp",
                            "isCompany": True,
                            "companyName": "Acme Corp",
                            "emails": [],
                            "phones": [],
                        },
                        {
                            "id": "c2",
                            "name": "Bob",
                            "isCompany": False,
                            "companyName": None,
                            "emails": [],
                            "phones": [],
                        },
                    ],
                    "pageInfo": {"hasNextPage": False, "endCursor": None},
                }
            }
        )
        items = []
        async for company in svc.list_companies(ListCompaniesRequest()):
            items.append(company)
        assert len(items) == 1
        assert items[0].id == "co1"


class TestCreateCompany:
    @pytest.mark.asyncio
    async def test_sets_is_company_flag(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "clientCreate": {
                    "client": {
                        "id": "co2",
                        "name": None,
                        "isCompany": True,
                        "companyName": "Globex",
                        "emails": [],
                        "phones": [],
                    }
                }
            }
        )
        company = await svc.create_company(CreateCompanyRequest(name="Globex"))
        assert company.id == "co2"
        body = mock_req.call_args.kwargs["json"]
        assert body["variables"]["input"]["isCompany"] is True


class TestListActivities:
    @pytest.mark.asyncio
    async def test_yields_notes(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "notes": {
                    "nodes": [
                        {
                            "id": "n1",
                            "note": "Follow up",
                            "createdAt": "2024-01-01T00:00:00Z",
                            "client": {"id": "c1"},
                        }
                    ],
                    "pageInfo": {"hasNextPage": False},
                }
            }
        )
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest(contact_id="c1")):
            items.append(activity)
        assert len(items) == 1
        assert items[0].id == "n1"


class TestCreateActivity:
    @pytest.mark.asyncio
    async def test_calls_note_create(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "noteCreate": {
                    "note": {
                        "id": "n2",
                        "note": "test",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "client": {"id": "c1"},
                    }
                }
            }
        )
        activity = await svc.create_activity(
            CreateActivityRequest(kind="note", body="test", contact_id="c1")
        )
        assert activity.id == "n2"


class TestUpdateActivity:
    @pytest.mark.asyncio
    async def test_calls_note_edit(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _gql_resp(
            {
                "noteEdit": {
                    "note": {
                        "id": "n1",
                        "note": "Updated",
                        "createdAt": "2024-01-01T00:00:00Z",
                        "client": {"id": "c1"},
                    }
                }
            }
        )
        activity = await svc.update_activity(
            UpdateActivityRequest(activity_id="n1", body="Updated")
        )
        assert activity.id == "n1"
        body = mock_req.call_args.kwargs["json"]
        assert "noteEdit" in body["query"]
