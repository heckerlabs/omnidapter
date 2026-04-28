"""Unit tests for HousecallProBookingService (API key auth)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import ApiKeyCredentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.housecallpro.booking import HCP_API_BASE, HousecallProBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import CreateBookingRequest, ListBookingsRequest
from omnidapter.stores.credentials import StoredCredential


def _stored(api_key: str = "hcp-key") -> StoredCredential:
    return StoredCredential(
        provider_key="housecallpro",
        auth_kind=AuthKind.API_KEY,
        credentials=ApiKeyCredentials(api_key=api_key),
    )


def _make_service() -> tuple[HousecallProBookingService, AsyncMock]:
    svc = HousecallProBookingService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestAuthHeaders:
    async def test_api_key_sent_as_bearer(self):
        svc, _ = _make_service()
        headers = await svc._auth_headers()
        assert headers["Authorization"] == "Bearer hcp-key"

    async def test_no_oauth(self):
        svc, _ = _make_service()
        # Ensure no token refresh for API key providers
        assert not hasattr(svc, "get_oauth_config")


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


class TestListServices:
    async def test_returns_generic_job_service(self):
        svc, _ = _make_service()
        services = await svc.list_services()
        assert len(services) == 1
        assert services[0].id == "job"

    async def test_uses_provider_config_services(self):
        stored = _stored()
        stored.provider_config = {"services": ["Lawn Care", "Pest Control"]}
        svc = HousecallProBookingService("conn-1", stored)
        services = await svc.list_services()
        assert len(services) == 2
        assert services[0].name == "Lawn Care"


class TestCreateBooking:
    async def test_resolves_customer_first(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = data
            return m

        # find_customer → empty list
        mock_req.side_effect = [
            _resp({"customers": []}),
            # create_customer
            _resp(
                {"id": "cust-1", "first_name": "Tom", "last_name": "Jones", "email": "tom@test.com"}
            ),
            # create job
            _resp(
                {
                    "id": "job-1",
                    "customer_id": "cust-1",
                    "schedule": {
                        "scheduled_start": "2026-05-01T10:00:00Z",
                        "scheduled_end": "2026-05-01T11:00:00Z",
                    },
                    "assigned_employees": [],
                    "line_items": [],
                }
            ),
        ]
        req = CreateBookingRequest(
            service_id="job",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Tom Jones", email="tom@test.com"),
        )
        booking = await svc.create_booking(req)
        assert mock_req.await_count == 3
        assert booking.id == "job-1"

    async def test_posts_to_jobs_endpoint(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = data
            return m

        mock_req.side_effect = [
            _resp(
                {
                    "customers": [
                        {
                            "id": "c-1",
                            "first_name": "Sam",
                            "last_name": "Lee",
                            "email": "sam@test.com",
                            "mobile_number": "",
                        }
                    ]
                }
            ),
            _resp(
                {
                    "id": "j-1",
                    "customer_id": "c-1",
                    "schedule": {"scheduled_start": "2026-05-01T10:00:00Z"},
                    "assigned_employees": [],
                    "line_items": [],
                }
            ),
        ]
        req = CreateBookingRequest(
            service_id="job",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Sam Lee", email="sam@test.com"),
        )
        await svc.create_booking(req)
        job_call = mock_req.await_args_list[-1]
        assert job_call.args[0] == "POST"
        assert job_call.args[1] == f"{HCP_API_BASE}/api/v1/jobs"


class TestListBookings:
    async def test_page_based_pagination(self):
        svc, mock_req = _make_service()

        def _page(jobs):
            m = MagicMock()
            m.json.return_value = {"jobs": jobs}
            return m

        job = {
            "id": "j-1",
            "customer_id": "c-1",
            "schedule": {"scheduled_start": "2026-05-01T10:00:00Z"},
            "assigned_employees": [],
            "line_items": [],
        }
        mock_req.side_effect = [_page([job, job]), _page([])]
        items = []
        async for b in svc.list_bookings(ListBookingsRequest(page_size=2)):
            items.append(b)
        assert len(items) == 2
        assert mock_req.await_count == 2


class TestCancelBooking:
    async def test_deletes_job(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {}
        await svc.cancel_booking("job-99")
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "DELETE"
        assert "job-99" in call.args[1]
