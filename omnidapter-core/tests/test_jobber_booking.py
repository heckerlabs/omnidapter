"""Unit tests for JobberBookingService (GraphQL)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import ProviderAPIError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.jobber.booking import JOBBER_GRAPHQL_URL, JobberBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    ListBookingsRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "jb-tok") -> StoredCredential:
    return StoredCredential(
        provider_key="jobber",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[JobberBookingService, AsyncMock]:
    svc = JobberBookingService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": {}}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestGraphQL:
    async def test_posts_to_graphql_endpoint(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {"data": {"products": {"nodes": []}}}
        await svc.list_services()
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "POST"
        assert call.args[1] == JOBBER_GRAPHQL_URL

    async def test_graphql_error_raises_provider_api_error(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {"errors": [{"message": "Field 'x' not found"}]}
        with pytest.raises(ProviderAPIError, match="GraphQL error"):
            await svc._graphql("{ bad }")

    async def test_version_header_set(self):
        svc, _ = _make_service()
        assert "X-JOBBER-GRAPHQL-VERSION" in svc._http._default_headers


class TestCapabilities:
    def test_list_locations_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(BookingCapability.LIST_LOCATIONS)

    def test_customer_management_supported(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.CUSTOMER_MANAGEMENT)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert BookingCapability.WEBHOOKS not in svc.capabilities


class TestCreateBooking:
    async def test_creates_client_if_not_found(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = {"data": data}
            return m

        # find_customer → empty
        mock_req.side_effect = [
            _resp({"clients": {"nodes": []}}),
            # create_customer
            _resp(
                {
                    "clientCreate": {
                        "client": {
                            "id": "cl-1",
                            "name": "Alice",
                            "emails": [{"address": "alice@test.com"}],
                            "phones": [],
                        },
                        "userErrors": [],
                    }
                }
            ),
            # create_booking
            _resp(
                {
                    "jobCreate": {
                        "job": {
                            "id": "job-1",
                            "title": "Lawn Care",
                            "jobStatus": "active",
                            "client": {"id": "cl-1", "name": "Alice"},
                            "visits": {
                                "nodes": [
                                    {
                                        "id": "v-1",
                                        "startAt": "2026-05-01T10:00:00Z",
                                        "endAt": "2026-05-01T11:00:00Z",
                                    }
                                ]
                            },
                            "lineItems": {"nodes": []},
                            "assignedTo": {"nodes": []},
                        },
                        "userErrors": [],
                    }
                }
            ),
        ]

        req = CreateBookingRequest(
            service_id="svc-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Alice", email="alice@test.com"),
        )
        booking = await svc.create_booking(req)
        assert booking.id == "job-1"
        assert mock_req.await_count == 3

    async def test_job_creation_error_raises(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = {"data": data}
            return m

        # customer.id is already set → _resolve_customer returns without any HTTP call.
        # Only one call: the jobCreate mutation.
        mock_req.side_effect = [
            _resp(
                {
                    "jobCreate": {
                        "job": None,
                        "userErrors": [{"message": "client not found", "path": ["clientId"]}],
                    }
                }
            ),
        ]
        req = CreateBookingRequest(
            service_id="svc-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(id="cl-1", name="Alice"),
        )
        with pytest.raises(ProviderAPIError):
            await svc.create_booking(req)


class TestResolveCustomerByPhone:
    async def test_finds_existing_customer_by_phone(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = {"data": data}
            return m

        client = {
            "id": "cl-9",
            "name": "Pat Jones",
            "emails": [],
            "phones": [{"number": "555-0199"}],
        }
        booking_resp = {
            "jobCreate": {
                "job": {
                    "id": "job-9",
                    "title": "",
                    "jobStatus": "active",
                    "client": {"id": "cl-9", "name": "Pat Jones"},
                    "visits": {
                        "nodes": [
                            {
                                "id": "v-1",
                                "startAt": "2026-05-01T10:00:00Z",
                                "endAt": "2026-05-01T11:00:00Z",
                            }
                        ]
                    },
                    "lineItems": {"nodes": []},
                    "assignedTo": {"nodes": []},
                },
                "userErrors": [],
            }
        }
        # find by phone → found; no create_customer; create_booking
        mock_req.side_effect = [
            _resp({"clients": {"nodes": [client]}}),
            _resp(booking_resp),
        ]
        req = CreateBookingRequest(
            service_id="svc-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Pat Jones", phone="555-0199"),
        )
        booking = await svc.create_booking(req)
        assert mock_req.await_count == 2
        assert booking.id == "job-9"

    async def test_creates_customer_when_phone_not_found(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = {"data": data}
            return m

        mock_req.side_effect = [
            _resp({"clients": {"nodes": []}}),  # find by phone → empty
            _resp(
                {
                    "clientCreate": {
                        "client": {"id": "cl-new", "name": "Pat", "emails": [], "phones": []},
                        "userErrors": [],
                    }
                }
            ),
            _resp(
                {
                    "jobCreate": {
                        "job": {
                            "id": "job-new",
                            "title": "",
                            "jobStatus": "active",
                            "client": {"id": "cl-new", "name": "Pat"},
                            "visits": {
                                "nodes": [
                                    {
                                        "id": "v-1",
                                        "startAt": "2026-05-01T10:00:00Z",
                                        "endAt": "2026-05-01T11:00:00Z",
                                    }
                                ]
                            },
                            "lineItems": {"nodes": []},
                            "assignedTo": {"nodes": []},
                        },
                        "userErrors": [],
                    }
                }
            ),
        ]
        booking = await svc.create_booking(
            CreateBookingRequest(
                service_id="svc-1",
                start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
                customer=BookingCustomer(name="Pat", phone="555-0199"),
            )
        )
        assert mock_req.await_count == 3
        assert booking.id == "job-new"


class TestListBookings:
    async def test_cursor_pagination(self):
        svc, mock_req = _make_service()

        def _page(nodes, has_next, cursor=None):
            m = MagicMock()
            m.json.return_value = {
                "data": {
                    "jobs": {
                        "nodes": nodes,
                        "pageInfo": {"hasNextPage": has_next, "endCursor": cursor},
                    }
                }
            }
            return m

        job = {
            "id": "j-1",
            "title": "",
            "jobStatus": "active",
            "instructions": None,
            "client": {"id": "c-1", "name": "Bob", "emails": [], "phones": []},
            "visits": {
                "nodes": [
                    {
                        "id": "v-1",
                        "startAt": "2026-05-01T09:00:00Z",
                        "endAt": "2026-05-01T10:00:00Z",
                    }
                ]
            },
            "lineItems": {"nodes": []},
            "assignedTo": {"nodes": []},
        }
        mock_req.side_effect = [_page([job, job], True, "cur-1"), _page([job], False)]
        items = []
        async for b in svc.list_bookings(ListBookingsRequest(page_size=2)):
            items.append(b)
        assert len(items) == 3
        assert mock_req.await_count == 2
