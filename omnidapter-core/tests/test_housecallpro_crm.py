"""Unit tests for HousecallProCrmService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import ApiKeyCredentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.housecallpro.crm import HousecallProCrmService
from omnidapter.services.crm.capabilities import CrmCapability
from omnidapter.services.crm.requests import (
    CreateActivityRequest,
    CreateContactRequest,
    ListActivitiesRequest,
    ListContactsRequest,
    UpdateActivityRequest,
    UpdateContactRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(api_key: str = "hcp-key") -> StoredCredential:
    return StoredCredential(
        provider_key="housecallpro",
        auth_kind=AuthKind.API_KEY,
        credentials=ApiKeyCredentials(api_key=api_key),
    )


def _make_service() -> tuple[HousecallProCrmService, AsyncMock]:
    svc = HousecallProCrmService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _resp(data: object) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m


class TestCapabilities:
    def test_list_contacts_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.LIST_CONTACTS)

    def test_tags_supported(self):
        svc, _ = _make_service()
        assert svc.supports(CrmCapability.TAGS)

    def test_companies_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(CrmCapability.LIST_COMPANIES)

    def test_deals_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(CrmCapability.LIST_DEALS)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert CrmCapability.WEBHOOKS not in svc.capabilities

    def test_provider_key(self):
        svc, _ = _make_service()
        assert svc._provider_key == "housecallpro"

    def test_unsupported_raises(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(CrmCapability.LIST_COMPANIES)


class TestListContacts:
    @pytest.mark.asyncio
    async def test_yields_contacts(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {
                "customers": [
                    {
                        "id": "c1",
                        "first_name": "Alice",
                        "last_name": "Smith",
                        "email": "alice@example.com",
                    },
                ],
                "meta": {"total_pages": 1},
            }
        )
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert len(items) == 1
        assert items[0].id == "c1"

    @pytest.mark.asyncio
    async def test_empty_response(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"customers": [], "meta": {"total_pages": 1}})
        items = []
        async for contact in svc.list_contacts(ListContactsRequest()):
            items.append(contact)
        assert items == []

    @pytest.mark.asyncio
    async def test_search_param_forwarded(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"customers": [], "meta": {"total_pages": 1}})
        async for _ in svc.list_contacts(ListContactsRequest(search="Bob")):
            pass
        call_kwargs = mock_req.call_args
        assert "params" in call_kwargs.kwargs
        assert call_kwargs.kwargs["params"].get("q") == "Bob"


class TestGetContact:
    @pytest.mark.asyncio
    async def test_returns_contact(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "c1", "first_name": "Bob", "last_name": "Jones"})
        contact = await svc.get_contact("c1")
        assert contact.id == "c1"

    @pytest.mark.asyncio
    async def test_calls_correct_url(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "c1"})
        await svc.get_contact("c1")
        url = mock_req.call_args.args[1]
        assert "/customers/c1" in url


class TestCreateContact:
    @pytest.mark.asyncio
    async def test_posts_customer(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "new", "first_name": "Eve", "last_name": "Adams"})
        contact = await svc.create_contact(
            CreateContactRequest(first_name="Eve", last_name="Adams")
        )
        assert contact.id == "new"
        assert mock_req.call_args.args[0] == "POST"


class TestUpdateContact:
    @pytest.mark.asyncio
    async def test_patches_customer(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "c1", "first_name": "Updated"})
        contact = await svc.update_contact(
            UpdateContactRequest(contact_id="c1", first_name="Updated")
        )
        assert contact.id == "c1"
        assert mock_req.call_args.args[0] == "PATCH"


class TestDeleteContact:
    @pytest.mark.asyncio
    async def test_deletes_customer(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({})
        await svc.delete_contact("c1")
        assert mock_req.call_args.args[0] == "DELETE"
        assert "/customers/c1" in mock_req.call_args.args[1]


class TestSearchContacts:
    @pytest.mark.asyncio
    async def test_returns_list(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {
                "customers": [{"id": "c2", "first_name": "Carol"}],
                "meta": {"total_pages": 1},
            }
        )
        results = await svc.search_contacts("Carol")
        assert len(results) == 1
        assert results[0].id == "c2"


class TestListActivities:
    @pytest.mark.asyncio
    async def test_yields_notes(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp([{"id": "n1", "content": "Call customer"}])
        items = []
        async for activity in svc.list_activities(ListActivitiesRequest(contact_id="c1")):
            items.append(activity)
        assert len(items) == 1
        assert items[0].id == "n1"


class TestCreateActivity:
    @pytest.mark.asyncio
    async def test_creates_note(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "n2", "content": "Follow up"})
        activity = await svc.create_activity(
            CreateActivityRequest(
                kind="note",
                body="Follow up",
                contact_id="c1",
            )
        )
        assert activity.id == "n2"

    @pytest.mark.asyncio
    async def test_posts_to_notes_endpoint(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "n3", "content": "test"})
        await svc.create_activity(CreateActivityRequest(kind="note", body="test", contact_id="c1"))
        url = mock_req.call_args.args[1]
        assert "/customers/c1/notes" in url


class TestUpdateActivity:
    @pytest.mark.asyncio
    async def test_patches_note(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"id": "n1", "content": "Updated"})
        activity = await svc.update_activity(
            UpdateActivityRequest(activity_id="n1", body="Updated")
        )
        assert activity.id == "n1"
        assert mock_req.call_args.args[0] == "PATCH"
