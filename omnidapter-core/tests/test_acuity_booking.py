"""Unit tests for AcuityBookingService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.acuity.booking import AcuityBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import CreateBookingRequest, ListBookingsRequest
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "test-tok") -> StoredCredential:
    return StoredCredential(
        provider_key="acuity",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[AcuityBookingService, AsyncMock]:
    svc = AcuityBookingService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = []
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestAuthHeaders:
    async def test_bearer_token_sent(self):
        svc, mock_req = _make_service()
        headers = await svc._auth_headers()
        assert headers["Authorization"] == "Bearer test-tok"

    async def test_credential_resolver_invoked(self):
        svc = AcuityBookingService("conn-1", _stored("old"))
        refreshed = _stored("new")
        svc._credential_resolver = AsyncMock(return_value=refreshed)
        headers = await svc._auth_headers()
        assert headers["Authorization"] == "Bearer new"
        svc._credential_resolver.assert_awaited_once_with("conn-1")


class TestCapabilities:
    def test_capabilities_is_frozenset(self):
        svc, _ = _make_service()
        assert isinstance(svc.capabilities, frozenset)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert BookingCapability.WEBHOOKS not in svc.capabilities

    def test_supports_create_booking(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.CREATE_BOOKING)

    def test_list_locations_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(BookingCapability.LIST_LOCATIONS)


class TestListServices:
    async def test_gets_appointment_types(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = [
            {"id": 1, "name": "Consultation", "duration": 30, "price": "100.00"}
        ]
        services = await svc.list_services()
        assert len(services) == 1
        assert services[0].name == "Consultation"
        assert services[0].duration_minutes == 30

    async def test_request_goes_to_correct_endpoint(self):
        svc, mock_req = _make_service()
        await svc.list_services()
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "GET"
        assert "/appointment-types" in call.args[1]


class TestCreateBooking:
    async def test_post_payload(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {
            "id": 123,
            "appointmentTypeID": 1,
            "datetime": "2026-05-01T10:00:00-04:00",
            "endTime": "2026-05-01T10:30:00-04:00",
            "calendar": "Main",
            "type": "Consultation",
            "firstName": "Jane",
            "lastName": "Doe",
            "email": "jane@example.com",
            "phone": "",
            "confirmationPage": None,
        }
        req = CreateBookingRequest(
            service_id="1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Jane Doe", email="jane@example.com"),
        )
        booking = await svc.create_booking(req)
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "POST"
        assert "/appointments" in call.args[1]
        body = call.kwargs["json"]
        assert body["appointmentTypeID"] == 1
        assert body["email"] == "jane@example.com"
        assert booking.id == "123"


class TestCancelBooking:
    async def test_deletes_appointment(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {}
        await svc.cancel_booking("42")
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "DELETE"
        assert "/appointments/42" in call.args[1]


class TestListBookings:
    async def test_iterates_pages(self):
        svc, mock_req = _make_service()
        page1 = [
            {
                "id": i,
                "appointmentTypeID": 1,
                "datetime": "2026-05-01T10:00:00-04:00",
                "endTime": "2026-05-01T10:30:00-04:00",
                "firstName": "Jane",
                "lastName": "Doe",
                "email": "jane@example.com",
                "phone": "",
                "calendar": "Main",
                "type": "Consult",
                "confirmationPage": None,
            }
            for i in range(5)
        ]
        mock_req.return_value.json.return_value = page1
        req = ListBookingsRequest(page_size=5)
        items = []
        async for b in svc.list_bookings(req):
            items.append(b)
        assert len(items) == 5

    async def test_empty_page_stops_iteration(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = []
        items = []
        async for b in svc.list_bookings(ListBookingsRequest()):
            items.append(b)
        assert items == []
