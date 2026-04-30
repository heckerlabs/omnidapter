"""Unit tests for SalesforceCrmService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.salesforce.crm import SalesforceCrmService
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


def _stored(token: str = "tok-sf") -> StoredCredential:
    return StoredCredential(
        provider_key="salesforce",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=token),
        provider_config={"instance_url": "https://my.salesforce.com"},
    )


def _make_service() -> tuple[SalesforceCrmService, AsyncMock]:
    svc = SalesforceCrmService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _resp(data: object) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m


def _sf_contact(id_: str = "c1", first: str = "Alice", last: str = "Smith") -> dict:
    return {
        "Id": id_,
        "FirstName": first,
        "LastName": last,
        "Name": f"{first} {last}",
        "Email": f"{first.lower()}@example.com",
        "Phone": None,
        "MobilePhone": None,
        "AccountId": None,
        "Description": None,
    }


def _sf_company(id_: str = "a1", name: str = "Acme") -> dict:
    return {
        "Id": id_,
        "Name": name,
        "Website": None,
        "Industry": None,
        "Phone": None,
        "Email__c": None,
    }


def _sf_deal(id_: str = "d1", name: str = "Big Deal") -> dict:
    return {
        "Id": id_,
        "Name": name,
        "StageName": "Prospecting",
        "Amount": 5000,
        "CurrencyIsoCode": "USD",
        "AccountId": None,
        "ContactId": None,
        "OwnerId": None,
        "CloseDate": "2025-12-31",
        "Description": None,
    }


def _sf_task(id_: str = "t1", subject: str = "Call") -> dict:
    return {
        "Id": id_,
        "Subject": subject,
        "Description": "Details",
        "ActivityDateTime": "2024-01-01T00:00:00Z",
        "CreatedDate": "2024-01-01T00:00:00Z",
        "WhoId": "c1",
        "WhatId": None,
        "ActivityType": None,
    }


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

    def test_tags_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.TAGS)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert CrmCapability.WEBHOOKS not in svc.capabilities

    def test_provider_key(self):
        svc, _ = _make_service()
        assert svc._provider_key == "salesforce"

    def test_unsupported_raises(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(CrmCapability.WEBHOOKS)


class TestListContacts:
    @pytest.mark.asyncio
    async def test_yields_contacts(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"records": [_sf_contact("c1")], "nextRecordsUrl": None})
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert len(items) == 1
        assert items[0].id == "c1"

    @pytest.mark.asyncio
    async def test_empty_response(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"records": [], "nextRecordsUrl": None})
        items = []
        async for _ in svc.list_contacts(ListContactsRequest()):
            items.append(_)
        assert items == []


class TestGetContact:
    @pytest.mark.asyncio
    async def test_returns_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_sf_contact("c1"))
        contact = await svc.get_contact("c1")
        assert contact.id == "c1"

    @pytest.mark.asyncio
    async def test_calls_correct_url(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_sf_contact("c1"))
        await svc.get_contact("c1")
        url = mock_req.call_args.args[1]
        assert "/sobjects/Contact/c1" in url


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_posts_then_fetches(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp({"id": "new-c"}),
            _resp(_sf_contact("new-c", "Eve", "Adams")),
        ]
        contact = await svc.create_contact(
            CreateContactRequest(first_name="Eve", last_name="Adams")
        )
        assert contact.id == "new-c"
        assert mock_req.call_count == 2

    @pytest.mark.asyncio
    async def test_maps_first_name(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [_resp({"id": "x"}), _resp(_sf_contact("x", "Bob", "Jones"))]
        await svc.create_contact(CreateContactRequest(first_name="Bob", last_name="Jones"))
        body = mock_req.call_args_list[0].kwargs["json"]
        assert body["FirstName"] == "Bob"


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_patches_then_fetches(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [
            _resp(None),
            _resp(_sf_contact("c1", "Updated", "Name")),
        ]
        contact = await svc.update_contact(
            UpdateContactRequest(contact_id="c1", first_name="Updated")
        )
        assert contact.id == "c1"
        assert mock_req.call_args_list[0].args[0] == "PATCH"


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_deletes(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(None)
        await svc.delete_contact("c1")
        assert mock_req.call_args.args[0] == "DELETE"
        assert "/Contact/c1" in mock_req.call_args.args[1]


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"records": [_sf_contact("c2")], "nextRecordsUrl": None})
        results = await svc.search_contacts("Alice")
        assert len(results) == 1
        assert results[0].id == "c2"


class TestListCompanies:
    @pytest.mark.asyncio
    async def test_yields_accounts(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"records": [_sf_company("a1")], "nextRecordsUrl": None})
        items = []
        async for company in svc.list_companies(ListCompaniesRequest()):
            items.append(company)
        assert len(items) == 1
        assert items[0].id == "a1"


class TestCreateCompany:
    @pytest.mark.asyncio
    async def test_posts_account(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [_resp({"id": "a2"}), _resp(_sf_company("a2", "Globex"))]
        company = await svc.create_company(CreateCompanyRequest(name="Globex"))
        assert company.id == "a2"
        assert mock_req.call_args_list[0].args[0] == "POST"


class TestListDeals:
    @pytest.mark.asyncio
    async def test_yields_opportunities(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"records": [_sf_deal("d1")], "nextRecordsUrl": None})
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        assert len(items) == 1
        assert items[0].id == "d1"

    @pytest.mark.asyncio
    async def test_maps_stage(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"records": [_sf_deal("d1")], "nextRecordsUrl": None})
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        from omnidapter.services.crm.models import DealStage

        assert items[0].stage == DealStage.LEAD


class TestCreateDeal:
    @pytest.mark.asyncio
    async def test_posts_opportunity(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [_resp({"id": "d2"}), _resp(_sf_deal("d2", "New Deal"))]
        deal = await svc.create_deal(CreateDealRequest(name="New Deal"))
        assert deal.id == "d2"


class TestListActivities:
    @pytest.mark.asyncio
    async def test_yields_tasks_and_events(self):
        svc, mock_req = _make_service()
        # list_activities makes two SOQL calls (tasks + events)
        mock_req.side_effect = [
            _resp({"records": [_sf_task("t1")], "nextRecordsUrl": None}),
            _resp({"records": [], "nextRecordsUrl": None}),
        ]
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest()):
            items.append(activity)
        assert len(items) == 1
        assert items[0].id == "t1"


class TestCreateActivity:
    @pytest.mark.asyncio
    async def test_creates_task(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [_resp({"id": "t2"}), _resp(_sf_task("t2", "Follow up"))]
        activity = await svc.create_activity(
            CreateActivityRequest(kind="note", body="Follow up", contact_id="c1")
        )
        assert activity.id == "t2"
