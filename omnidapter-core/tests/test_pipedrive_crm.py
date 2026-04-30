"""Unit tests for PipedriveCrmService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.pipedrive.crm import PipedriveCrmService
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


def _stored(token: str = "tok-pd") -> StoredCredential:
    return StoredCredential(
        provider_key="pipedrive",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=token),
        provider_config={"api_domain": "api"},
    )


def _make_service() -> tuple[PipedriveCrmService, AsyncMock]:
    svc = PipedriveCrmService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _resp(data: object) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m


def _pd_person(id_: int = 1, name: str = "Alice Smith") -> dict:
    return {"id": id_, "name": name, "email": [], "phone": [], "org_id": None, "label_ids": []}


def _pd_org(id_: int = 10, name: str = "Acme") -> dict:
    return {"id": id_, "name": name, "web_site_or_url": None, "industry": None}


def _pd_deal(id_: int = 100, title: str = "Big Deal") -> dict:
    return {
        "id": id_,
        "title": title,
        "status": "open",
        "stage_name": "Lead",
        "value": 5000,
        "currency": "USD",
        "person_id": None,
        "org_id": None,
        "user_id": None,
        "won_time": None,
        "lost_time": None,
        "expected_close_date": None,
    }


def _pd_note(id_: int = 200, content: str = "Note body") -> dict:
    return {
        "id": id_,
        "content": content,
        "person_id": 1,
        "org_id": None,
        "deal_id": None,
        "add_time": "2024-01-01 00:00:00",
    }


def _page(items: list, more: bool = False) -> dict:
    return {
        "data": items,
        "additional_data": {"pagination": {"more_items_in_collection": more}},
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

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert CrmCapability.WEBHOOKS not in svc.capabilities

    def test_provider_key(self):
        svc, _ = _make_service()
        assert svc._provider_key == "pipedrive"

    def test_unsupported_raises(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(CrmCapability.WEBHOOKS)


class TestListContacts:
    @pytest.mark.asyncio
    async def test_yields_persons(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_pd_person(1)]))
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert len(items) == 1
        assert items[0].id == "1"

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
        mock_req.return_value = _resp({"data": _pd_person(1)})
        contact = await svc.get_contact("1")
        assert contact.id == "1"

    @pytest.mark.asyncio
    async def test_calls_persons_url(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": _pd_person(1)})
        await svc.get_contact("1")
        url = mock_req.call_args.args[1]
        assert "/persons/1" in url


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_posts_person(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": _pd_person(2, "Eve Adams")})
        contact = await svc.create_contact(
            CreateContactRequest(first_name="Eve", last_name="Adams")
        )
        assert contact.id == "2"
        assert mock_req.call_args.args[0] == "POST"

    @pytest.mark.asyncio
    async def test_name_combined(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": _pd_person(3, "Bob Jones")})
        await svc.create_contact(CreateContactRequest(first_name="Bob", last_name="Jones"))
        body = mock_req.call_args.kwargs["json"]
        assert body["name"] == "Bob Jones"


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_puts_person(self):
        svc, mock_req = _make_service()
        # update with only email (no name fetch needed)
        from omnidapter.services.crm.models import ContactEmail

        mock_req.return_value = _resp({"data": _pd_person(1)})
        contact = await svc.update_contact(
            UpdateContactRequest(
                contact_id="1",
                emails=[ContactEmail(address="new@example.com")],
            )
        )
        assert contact.id == "1"
        assert mock_req.call_args.args[0] == "PUT"


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_deletes_person(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"success": True})
        await svc.delete_contact("1")
        assert mock_req.call_args.args[0] == "DELETE"
        assert "/persons/1" in mock_req.call_args.args[1]


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": {"items": [{"item": _pd_person(2, "Carol")}]}})
        results = await svc.search_contacts("Carol")
        assert len(results) == 1
        assert results[0].id == "2"


class TestListCompanies:
    @pytest.mark.asyncio
    async def test_yields_organizations(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_pd_org(10)]))
        items = []
        async for company in svc.list_companies(ListCompaniesRequest()):
            items.append(company)
        assert len(items) == 1
        assert items[0].id == "10"


class TestCreateCompany:
    @pytest.mark.asyncio
    async def test_posts_organization(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": _pd_org(20, "Globex")})
        company = await svc.create_company(CreateCompanyRequest(name="Globex"))
        assert company.id == "20"
        assert mock_req.call_args.args[0] == "POST"


class TestListDeals:
    @pytest.mark.asyncio
    async def test_yields_deals(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_pd_deal(100)]))
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        assert len(items) == 1
        assert items[0].id == "100"

    @pytest.mark.asyncio
    async def test_maps_stage(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(_page([_pd_deal(100)]))
        items = []
        async for deal in svc.list_deals(ListDealsRequest()):
            items.append(deal)
        from omnidapter.services.crm.models import DealStage

        assert items[0].stage == DealStage.LEAD


class TestCreateDeal:
    @pytest.mark.asyncio
    async def test_posts_deal(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": _pd_deal(101, "New Deal")})
        deal = await svc.create_deal(CreateDealRequest(name="New Deal"))
        assert deal.id == "101"
        body = mock_req.call_args.kwargs["json"]
        assert body["title"] == "New Deal"


class TestListActivities:
    @pytest.mark.asyncio
    async def test_yields_notes(self):
        svc, mock_req = _make_service()
        # list_activities paginates /notes then /activities
        mock_req.side_effect = [
            _resp(_page([_pd_note(200)])),  # /notes
            _resp(_page([])),  # /activities
        ]
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest()):
            items.append(activity)
        assert len(items) == 1
        assert items[0].id == "200"

    @pytest.mark.asyncio
    async def test_note_kind(self):
        svc, mock_req = _make_service()
        mock_req.side_effect = [_resp(_page([_pd_note(200)])), _resp(_page([]))]
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest()):
            items.append(activity)
        from omnidapter.services.crm.models import ActivityKind

        assert items[0].kind == ActivityKind.NOTE


class TestCreateActivity:
    @pytest.mark.asyncio
    async def test_creates_note(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"data": _pd_note(201, "Follow up")})
        activity = await svc.create_activity(
            CreateActivityRequest(kind="note", body="Follow up", contact_id="1")
        )
        assert activity.id == "201"
        url = mock_req.call_args.args[1]
        assert "/notes" in url
