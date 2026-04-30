"""Unit tests for ZohoCrmService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.zoho.crm import ZohoCrmService
from omnidapter.services.crm.capabilities import CrmCapability
from omnidapter.services.crm.requests import (
    CreateActivityRequest,
    CreateCompanyRequest,
    CreateContactRequest,
    CreateDealRequest,
    ListActivitiesRequest,
    ListCompaniesRequest,
    ListContactsRequest,
    ListDealsRequest,
    UpdateContactRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(token: str = "tok-zoho") -> StoredCredential:
    return StoredCredential(
        provider_key="zoho",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=token),
    )


def _make_service() -> tuple[ZohoCrmService, AsyncMock]:
    svc = ZohoCrmService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _resp(data: object) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m


def _zoho_contact(id_: str = "c1", first: str = "Alice", last: str = "Smith") -> dict:
    return {
        "id": id_,
        "First_Name": first,
        "Last_Name": last,
        "Full_Name": f"{first} {last}",
        "Email": f"{first.lower()}@example.com",
        "Phone": None,
        "Mobile": None,
        "Account_Name": None,
        "Description": None,
        "Tag": [],
    }


def _zoho_company(id_: str = "a1", name: str = "Acme") -> dict:
    return {
        "id": id_,
        "Account_Name": name,
        "Website": None,
        "Industry": None,
        "Phone": None,
        "Email": None,
    }


def _zoho_deal(id_: str = "d1", name: str = "Big Deal") -> dict:
    return {
        "id": id_,
        "Deal_Name": name,
        "Stage": "Qualification",
        "Amount": 5000,
        "Currency": "USD",
        "Account_Name": None,
        "Contact_Name": None,
        "Owner": None,
        "Closing_Date": None,
        "Description": None,
    }


def _zoho_note(id_: str = "n1", body: str = "Note body") -> dict:
    return {
        "id": id_,
        "Note_Title": "Note",
        "Note_Content": body,
        "Parent_Id": {"id": "c1"},
        "se_module": "Contacts",
        "Created_Time": "2024-01-01T00:00:00Z",
    }


def _page(records: list, more: bool = False) -> dict:
    return {"data": records, "info": {"more_records": more}}


class TestCapabilities:
    def test_all_contacts_supported(self):
        svc, _ = _make_service()
        for cap in (
            CrmCapability.LIST_CONTACTS,
            CrmCapability.GET_CONTACT,
            CrmCapability.CREATE_CONTACT,
            CrmCapability.UPDATE_CONTACT,
            CrmCapability.DELETE_CONTACT,
            CrmCapability.SEARCH_CONTACTS,
        ):
            assert svc.supports(cap)

    def test_companies_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.LIST_COMPANIES)
        assert svc.supports(CrmCapability.CREATE_COMPANY)

    def test_deals_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.LIST_DEALS)
        assert svc.supports(CrmCapability.CREATE_DEAL)

    def test_activities_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.LIST_ACTIVITIES)
        assert svc.supports(CrmCapability.CREATE_ACTIVITY)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert CrmCapability.WEBHOOKS not in svc.capabilities

    def test_provider_key(self):
        svc, _ = _make_service()
        assert svc._provider_key == "zoho"

    def test_unsupported_raises(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(CrmCapability.WEBHOOKS)


class TestListContacts:
    @pytest.mark.asyncio
    async def test_yields_contacts(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_zoho_contact("c1")]))
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert len(items) == 1
        assert items[0].id == "c1"

    @pytest.mark.asyncio
    async def test_empty_response(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([]))
        items = []
        async for _ in svc.list_contacts(ListContactsRequest()):
            items.append(_)
        assert items == []


class TestGetContact:
    @pytest.mark.asyncio
    async def test_returns_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": [_zoho_contact("c1")]})
        contact = await svc.get_contact("c1")
        assert contact.id == "c1"

    @pytest.mark.asyncio
    async def test_calls_correct_url(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": [_zoho_contact("c1")]})
        await svc.get_contact("c1")
        url = mock_req.call_args.args[1]
        assert "/Contacts/c1" in url


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_posts_then_fetches(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"data": [{"details": {"id": "new-c"}}]}),
            _resp({"data": [_zoho_contact("new-c", "Eve", "Adams")]}),
        ]
        contact = await svc.create_contact(
            CreateContactRequest(first_name="Eve", last_name="Adams")
        )
        assert contact.id == "new-c"
        assert mock_req.call_count == 2

    @pytest.mark.asyncio
    async def test_maps_first_name(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"data": [{"details": {"id": "x"}}]}),
            _resp({"data": [_zoho_contact("x", "Bob", "Jones")]}),
        ]
        await svc.create_contact(CreateContactRequest(first_name="Bob", last_name="Jones"))
        body = mock_req.call_args_list[0].kwargs["json"]
        assert body["data"][0]["First_Name"] == "Bob"


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_puts_then_fetches(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"data": [{"details": {"id": "c1"}}]}),
            _resp({"data": [_zoho_contact("c1", "Updated", "Name")]}),
        ]
        contact = await svc.update_contact(
            UpdateContactRequest(contact_id="c1", first_name="Updated")
        )
        assert contact.id == "c1"
        assert mock_req.call_args_list[0].args[0] == "PUT"


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_deletes(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(None)
        await svc.delete_contact("c1")
        assert mock_req.call_args.args[0] == "DELETE"
        assert "/Contacts/c1" in mock_req.call_args.args[1]


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": [_zoho_contact("c2")]})
        results = await svc.search_contacts("Alice")
        assert len(results) == 1
        assert results[0].id == "c2"


class TestListCompanies:
    @pytest.mark.asyncio
    async def test_yields_accounts(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_zoho_company("a1")]))
        items = []
        async for company in svc.list_companies(ListCompaniesRequest()):
            items.append(company)
        assert len(items) == 1
        assert items[0].id == "a1"


class TestCreateCompany:
    @pytest.mark.asyncio
    async def test_posts_account(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"data": [{"details": {"id": "a2"}}]}),
            _resp({"data": [_zoho_company("a2", "Globex")]}),
        ]
        company = await svc.create_company(CreateCompanyRequest(name="Globex"))
        assert company.id == "a2"


class TestListDeals:
    @pytest.mark.asyncio
    async def test_yields_deals(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_zoho_deal("d1")]))
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        assert len(items) == 1
        assert items[0].id == "d1"


class TestCreateDeal:
    @pytest.mark.asyncio
    async def test_posts_deal(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"data": [{"details": {"id": "d2"}}]}),
            _resp({"data": [_zoho_deal("d2", "New Deal")]}),
        ]
        deal = await svc.create_deal(CreateDealRequest(name="New Deal"))
        assert deal.id == "d2"


class TestListActivities:
    @pytest.mark.asyncio
    async def test_yields_notes(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_zoho_note("n1")]))
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest()):
            items.append(activity)
        assert len(items) == 1
        assert items[0].id == "n1"

    @pytest.mark.asyncio
    async def test_links_contact_id(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_zoho_note("n1")]))
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest()):
            items.append(activity)
        assert items[0].contact_id == "c1"


class TestCreateActivity:
    @pytest.mark.asyncio
    async def test_creates_note(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"data": [{"details": {"id": "n2"}}]}),
            _resp({"data": [_zoho_note("n2", "Follow up")]}),
        ]
        activity = await svc.create_activity(
            CreateActivityRequest(kind="note", body="Follow up", contact_id="c1")
        )
        assert activity.id == "n2"
