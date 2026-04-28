"""Unit tests for CalcomBookingService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.calcom.booking import CALCOM_API_BASE, CalcomBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import CreateBookingRequest, ListBookingsRequest
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "tok") -> StoredCredential:
    return StoredCredential(
        provider_key="calcom",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[CalcomBookingService, AsyncMock]:
    svc = CalcomBookingService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"data": []}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestAuthHeaders:
    async def test_bearer_token_sent(self):
        svc, _ = _make_service()
        headers = await svc._auth_headers()
        assert headers["Authorization"] == "Bearer tok"


class TestCapabilities:
    def test_multi_service_supported(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.MULTI_SERVICE)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert BookingCapability.WEBHOOKS not in svc.capabilities


class TestCreateBooking:
    async def test_post_body_shape(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {
            "data": {
                "id": "bk-1",
                "uid": "uid-1",
                "eventTypeId": 42,
                "start": "2026-05-01T10:00:00Z",
                "end": "2026-05-01T10:30:00Z",
                "status": "accepted",
                "attendees": [{"name": "Alice", "email": "alice@test.com", "timeZone": "UTC"}],
            }
        }
        req = CreateBookingRequest(
            service_id="42",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Alice", email="alice@test.com"),
        )
        booking = await svc.create_booking(req)
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "POST"
        assert call.args[1] == f"{CALCOM_API_BASE}/bookings"
        body = call.kwargs["json"]
        assert body["eventTypeId"] == 42
        assert body["attendee"]["email"] == "alice@test.com"
        assert booking.id == "bk-1"


class TestListBookings:
    async def test_paginates_until_empty(self):
        svc, mock_req = _make_service()

        def _page(bookings):
            m = MagicMock()
            m.json.return_value = {"data": {"bookings": bookings}}
            return m

        items_page = [
            {
                "id": str(i),
                "uid": f"uid-{i}",
                "eventTypeId": 1,
                "start": "2026-05-01T10:00:00Z",
                "end": "2026-05-01T10:30:00Z",
                "status": "accepted",
                "attendees": [],
            }
            for i in range(3)
        ]
        mock_req.side_effect = [_page(items_page), _page([])]
        collected = []
        async for b in svc.list_bookings(ListBookingsRequest(page_size=3)):
            collected.append(b)
        assert len(collected) == 3

    async def test_cal_version_header_present(self):
        svc, _ = _make_service()
        assert "cal-api-version" in svc._http._default_headers


class TestRescheduleBooking:
    async def test_posts_to_reschedule_endpoint(self):
        from omnidapter.services.booking.requests import RescheduleBookingRequest

        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {
            "data": {
                "id": "bk-1",
                "uid": "uid-new",
                "eventTypeId": 1,
                "start": "2026-05-02T10:00:00Z",
                "end": "2026-05-02T10:30:00Z",
                "status": "accepted",
                "attendees": [],
            }
        }
        req = RescheduleBookingRequest(
            booking_id="bk-1",
            new_start=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
        )
        await svc.reschedule_booking(req)
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "POST"
        assert "/reschedule" in call.args[1]
