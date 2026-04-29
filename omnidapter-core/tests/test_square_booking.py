"""Unit tests for SquareBookingService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.square.booking import SQUARE_API_BASE, SquareBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import CreateBookingRequest, UpdateBookingRequest
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "sq-tok") -> StoredCredential:
    return StoredCredential(
        provider_key="square",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[SquareBookingService, AsyncMock]:
    svc = SquareBookingService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestCapabilities:
    def test_list_locations_supported(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.LIST_LOCATIONS)

    def test_multi_service_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(BookingCapability.MULTI_SERVICE)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert BookingCapability.WEBHOOKS not in svc.capabilities


class TestListLocations:
    async def test_hits_locations_endpoint(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {"locations": []}
        await svc.list_locations()
        call_args = mock_req.await_args_list[-1]
        assert call_args.args[0] == "GET"
        assert call_args.args[1] == f"{SQUARE_API_BASE}/locations"


class TestCreateBooking:
    async def test_idempotency_key_present(self):
        svc, mock_req = _make_service()
        # First call: get_service_type to fetch variation_version
        svc_resp = MagicMock()
        svc_resp.json.return_value = {
            "object": {
                "type": "ITEM_VARIATION",
                "id": "var-1",
                "item_variation_data": {
                    "item_id": "item-1",
                    "name": "Haircut",
                    "service_duration": 1800000,
                    "price_money": {"amount": 5000, "currency": "USD"},
                    "version": 123,
                },
            }
        }
        parent_resp = MagicMock()
        parent_resp.json.return_value = {
            "object": {
                "item_data": {
                    "name": "Haircut",
                    "description": "",
                    "variations": [{"id": "var-1", "item_variation_data": {"version": 123}}],
                }
            }
        }
        # find_customer returns empty → create_customer
        search_resp = MagicMock()
        search_resp.json.return_value = {"customers": []}
        create_cust_resp = MagicMock()
        create_cust_resp.json.return_value = {
            "customer": {"id": "cust-1", "given_name": "Bob", "family_name": "Smith"}
        }
        booking_resp = MagicMock()
        booking_resp.json.return_value = {
            "booking": {
                "id": "bk-1",
                "start_at": "2026-05-01T10:00:00Z",
                "duration_minutes": 30,
                "status": "ACCEPTED",
                "customer_id": "cust-1",
                "appointment_segments": [{"service_variation_id": "var-1"}],
            }
        }
        # create_booking order: _resolve_customer first, then get_service_type, then POST /bookings
        mock_req.side_effect = [
            search_resp,  # find_customer → POST /customers/search
            create_cust_resp,  # create_customer → POST /customers
            svc_resp,  # get_service_type → GET /catalog/object/var-1
            parent_resp,  # get_service_type parent → GET /catalog/object/item-1
            booking_resp,  # POST /bookings
        ]
        req = CreateBookingRequest(
            service_id="var-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Bob Smith", email="bob@example.com"),
        )
        booking = await svc.create_booking(req)
        # Last call is the booking POST
        last_call = mock_req.await_args_list[-1]
        assert last_call.args[0] == "POST"
        assert last_call.args[1] == f"{SQUARE_API_BASE}/bookings"
        body = last_call.kwargs["json"]
        assert "idempotency_key" in body
        assert booking.id == "bk-1"


class TestCancelBooking:
    async def test_fetches_version_before_cancel(self):
        svc, mock_req = _make_service()
        get_resp = MagicMock()
        get_resp.json.return_value = {"booking": {"id": "bk-1", "version": 7, "status": "ACCEPTED"}}
        cancel_resp = MagicMock()
        cancel_resp.json.return_value = {}
        mock_req.side_effect = [get_resp, cancel_resp]
        await svc.cancel_booking("bk-1")
        assert mock_req.await_count == 2
        cancel_call = mock_req.await_args_list[-1]
        assert cancel_call.args[0] == "POST"
        assert "/cancel" in cancel_call.args[1]
        assert cancel_call.kwargs["json"]["booking_version"] == 7


class TestUpdateBooking:
    async def test_includes_version_in_put(self):
        svc, mock_req = _make_service()
        get_resp = MagicMock()
        get_resp.json.return_value = {"booking": {"id": "bk-2", "version": 3, "status": "ACCEPTED"}}
        upd_resp = MagicMock()
        upd_resp.json.return_value = {"booking": {"id": "bk-2", "version": 4, "status": "ACCEPTED"}}
        mock_req.side_effect = [get_resp, upd_resp]
        await svc.update_booking(
            UpdateBookingRequest(
                booking_id="bk-2",
                start=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
            )
        )
        put_call = mock_req.await_args_list[-1]
        assert put_call.args[0] == "PUT"
        assert put_call.kwargs["json"]["booking"]["version"] == 3
