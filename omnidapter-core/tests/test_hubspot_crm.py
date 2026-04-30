"""Unit tests for HubspotCrmService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.hubspot.crm import HubspotCrmService
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


def _stored(token: str = "tok-hs") -> StoredCredential:
    return StoredCredential(
        provider_key="hubspot",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=token),
    )


def _make_service() -> tuple[HubspotCrmService, AsyncMock]:
    svc = HubspotCrmService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _resp(data: object) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m


def _hs_contact(id_: str = "c1", first: str = "Alice", last: str = "Smith") -> dict:
    return {
        "id": id_,
        "properties": {
            "firstname": first,
            "lastname": last,
            "email": f"{first.lower()}@example.com",
            "phone": None,
            "mobilephone": None,
            "associatedcompanyid": None,
            "company": None,
            "hs_tags": None,
        },
    }


def _hs_company(id_: str = "co1", name: str = "Acme") -> dict:
    return {
        "id": id_,
        "properties": {
            "name": name,
            "website": None,
            "industry": None,
            "phone": None,
            "email": None,
        },
    }


def _hs_deal(id_: str = "d1", name: str = "Big Deal") -> dict:
    return {
        "id": id_,
        "properties": {
            "dealname": name,
            "dealstage": "closedwon",
            "amount": "5000",
            "hubspot_owner_id": None,
            "closedate": None,
            "description": None,
        },
    }


def _hs_note(id_: str = "n1", body: str = "Note body") -> dict:
    return {
        "id": id_,
        "properties": {
            "hs_note_body": body,
            "hs_timestamp": "2024-01-01T00:00:00Z",
            "createdate": "2024-01-01T00:00:00Z",
        },
    }


def _page(results: list) -> dict:
    return {"results": results}


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

    def test_tags_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(CrmCapability.TAGS)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert CrmCapability.WEBHOOKS not in svc.capabilities

    def test_provider_key(self):
        svc, _ = _make_service()
        assert svc._provider_key == "hubspot"

    def test_unsupported_raises(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(CrmCapability.TAGS)


class TestListContacts:
    @pytest.mark.asyncio
    async def test_yields_contacts(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_hs_contact("c1")]))
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
        mock_req.return_value = _resp(_hs_contact("c1"))
        contact = await svc.get_contact("c1")
        assert contact.id == "c1"

    @pytest.mark.asyncio
    async def test_calls_correct_url(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_contact("c1"))
        await svc.get_contact("c1")
        url = mock_req.call_args.args[1]
        assert "/contacts/c1" in url


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_posts_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_contact("new"))
        contact = await svc.create_contact(
            CreateContactRequest(first_name="Eve", last_name="Adams")
        )
        assert contact.id == "new"
        assert mock_req.call_args.args[0] == "POST"

    @pytest.mark.asyncio
    async def test_maps_properties(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_contact("new"))
        await svc.create_contact(CreateContactRequest(first_name="Bob", last_name="Jones"))
        body = mock_req.call_args.kwargs["json"]
        assert body["properties"]["firstname"] == "Bob"
        assert body["properties"]["lastname"] == "Jones"


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_patches_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_contact("c1", "Updated", "Name"))
        contact = await svc.update_contact(
            UpdateContactRequest(contact_id="c1", first_name="Updated")
        )
        assert contact.id == "c1"
        assert mock_req.call_args.args[0] == "PATCH"


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_deletes_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(None)
        await svc.delete_contact("c1")
        assert mock_req.call_args.args[0] == "DELETE"
        assert "/contacts/c1" in mock_req.call_args.args[1]


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"results": [_hs_contact("c2")]})
        results = await svc.search_contacts("Alice")
        assert len(results) == 1
        assert results[0].id == "c2"

    @pytest.mark.asyncio
    async def test_posts_to_search_endpoint(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"results": []})
        await svc.search_contacts("query")
        assert mock_req.call_args.args[0] == "POST"
        assert "/search" in mock_req.call_args.args[1]


class TestListCompanies:
    @pytest.mark.asyncio
    async def test_yields_companies(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_hs_company("co1")]))
        items = []
        async for company in svc.list_companies(ListCompaniesRequest()):
            items.append(company)
        assert len(items) == 1
        assert items[0].id == "co1"


class TestCreateCompany:
    @pytest.mark.asyncio
    async def test_posts_company(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_company("co2", "Globex"))
        company = await svc.create_company(CreateCompanyRequest(name="Globex"))
        assert company.id == "co2"


class TestListDeals:
    @pytest.mark.asyncio
    async def test_yields_deals(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_hs_deal("d1")]))
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        assert len(items) == 1
        assert items[0].id == "d1"

    @pytest.mark.asyncio
    async def test_maps_stage(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_hs_deal("d1")]))
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        from omnidapter.services.crm.models import DealStage

        assert items[0].stage == DealStage.CLOSED_WON


class TestCreateDeal:
    @pytest.mark.asyncio
    async def test_posts_deal(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_deal("d2", "New Deal"))
        deal = await svc.create_deal(CreateDealRequest(name="New Deal"))
        assert deal.id == "d2"
        body = mock_req.call_args.kwargs["json"]
        assert body["properties"]["dealname"] == "New Deal"


class TestListActivities:
    @pytest.mark.asyncio
    async def test_yields_notes(self):
        svc, mock_req = _make_service()
        # list_activities iterates all 4 activity types; first call returns a note
        mock_req.side_effect = [
            _resp(_page([_hs_note("n1")])),  # notes
            _resp(_page([])),  # calls
            _resp(_page([])),  # emails
            _resp(_page([])),  # meetings
        ]
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest()):
            items.append(activity)
        assert len(items) == 1
        assert items[0].id == "n1"


class TestCreateActivity:
    @pytest.mark.asyncio
    async def test_creates_note(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_hs_note("n2"))
        activity = await svc.create_activity(
            CreateActivityRequest(kind="note", body="Follow up", contact_id="c1")
        )
        assert activity.id == "n2"
