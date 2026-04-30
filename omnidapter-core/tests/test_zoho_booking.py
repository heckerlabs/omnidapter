"""Unit tests for ZohoBookingService."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.zoho.booking import ZohoBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    ListBookingsRequest,
    RescheduleBookingRequest,
    UpdateBookingRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "zoho-tok", workspace_id: str | None = "ws-1") -> StoredCredential:
    return StoredCredential(
        provider_key="zoho",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
        provider_config={"workspace_id": workspace_id} if workspace_id else {},
    )


def _make_service(workspace_id: str | None = "ws-1") -> tuple[ZohoBookingService, AsyncMock]:
    svc = ZohoBookingService("conn-1", _stored(workspace_id=workspace_id))
    mock_resp = MagicMock()
    mock_resp.json.return_value = {}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


def _resp(data: dict) -> MagicMock:
    m = MagicMock()
    m.json.return_value = data
    return m


class TestAuthHeaders:
    async def test_zoho_oauth_token_header(self):
        svc, _ = _make_service()
        headers = await svc._auth_headers()
        assert headers["Authorization"] == "Zoho-oauthtoken zoho-tok"


class TestCapabilities:
    def test_customer_management_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(BookingCapability.CUSTOMER_MANAGEMENT)

    def test_customer_lookup_supported(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.CUSTOMER_LOOKUP)

    def test_all_core_capabilities_present(self):
        svc, _ = _make_service()
        for cap in [
            BookingCapability.LIST_SERVICES,
            BookingCapability.GET_SERVICE,
            BookingCapability.LIST_STAFF,
            BookingCapability.GET_STAFF,
            BookingCapability.GET_AVAILABILITY,
            BookingCapability.CREATE_BOOKING,
            BookingCapability.CANCEL_BOOKING,
            BookingCapability.RESCHEDULE_BOOKING,
            BookingCapability.UPDATE_BOOKING,
            BookingCapability.LIST_BOOKINGS,
            BookingCapability.GET_BOOKING,
        ]:
            assert svc.supports(cap), f"{cap} should be supported"


class TestWorkspaceId:
    async def test_uses_config_workspace(self):
        svc, mock_req = _make_service(workspace_id="ws-42")
        wid = await svc._workspace_id()
        assert wid == "ws-42"
        mock_req.assert_not_called()

    async def test_fetches_workspace_when_not_configured(self):
        svc, mock_req = _make_service(workspace_id=None)
        mock_req.return_value = _resp({"response": {"workspaces": [{"id": "ws-auto"}]}})
        wid = await svc._workspace_id()
        assert wid == "ws-auto"
        mock_req.assert_called_once()

    async def test_returns_none_when_no_workspaces(self):
        svc, mock_req = _make_service(workspace_id=None)
        mock_req.return_value = _resp({"response": {"workspaces": []}})
        assert await svc._workspace_id() is None


class TestListServices:
    async def test_returns_services(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {"response": {"services": [{"id": "s-1", "name": "Haircut", "cost": "20"}]}}
        )
        services = await svc.list_services()
        assert len(services) == 1
        assert services[0].id == "s-1"
        assert services[0].name == "Haircut"
        assert services[0].price == "20"

    async def test_includes_workspace_id_param(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"services": []}})
        await svc.list_services()
        call = mock_req.await_args_list[0]
        assert call.kwargs["params"]["workspace_id"] == "ws-1"


class TestGetService:
    async def test_returns_service_by_id(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {"response": {"services": [{"id": "s-1", "name": "Massage"}]}}
        )
        svc_type = await svc.get_service_type("s-1")
        assert svc_type.id == "s-1"

    async def test_fallback_when_not_found(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"services": []}})
        svc_type = await svc.get_service_type("s-missing")
        assert svc_type.id == "s-missing"


class TestListStaff:
    async def test_returns_staff(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {"response": {"staffs": [{"id": "st-1", "name": "Alice", "email": "alice@test.com"}]}}
        )
        staff = await svc.list_staff()
        assert len(staff) == 1
        assert staff[0].id == "st-1"
        assert staff[0].email == "alice@test.com"

    async def test_passes_service_id_filter(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"staffs": []}})
        await svc.list_staff(service_id="s-1")
        call = mock_req.await_args_list[0]
        assert call.kwargs["params"].get("service_id") == "s-1"


class TestGetStaff:
    async def test_returns_staff_by_id(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"staffs": [{"id": "st-1", "name": "Bob"}]}})
        member = await svc.get_staff("st-1")
        assert member.id == "st-1"

    async def test_fallback_when_not_found(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"staffs": []}})
        member = await svc.get_staff("st-missing")
        assert member.id == "st-missing"


class TestGetAvailability:
    async def test_returns_slots_in_range(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"slots": ["09:00", "10:00", "11:00"]}})
        start = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        slots = await svc.get_availability("s-1", start, end)
        assert len(slots) == 3
        assert slots[0].service_id == "s-1"
        assert slots[0].start == start

    async def test_filters_slots_outside_range(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"slots": ["08:00", "09:00", "12:00"]}})
        start = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        slots = await svc.get_availability("s-1", start, end)
        assert len(slots) == 1
        assert slots[0].start.hour == 9

    async def test_passes_staff_id(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"slots": []}})
        start = datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc)
        end = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
        await svc.get_availability("s-1", start, end, staff_id="st-1")
        call = mock_req.await_args_list[0]
        assert call.kwargs["params"].get("staff_id") == "st-1"


class TestCreateBooking:
    async def test_posts_to_appointment_then_fetches(self):
        svc, mock_req = _make_service()
        appt = {
            "booking_id": "bk-1",
            "service_id": "s-1",
            "appointment_start_time": "01-May-2026 10:00:00",
            "appointment_end_time": "01-May-2026 11:00:00",
            "status": "scheduled",
            "customer_name": "Alice",
            "customer_email": "alice@test.com",
        }
        mock_req.side_effect = [
            _resp({"response": {"booking_id": "bk-1"}}),  # POST /appointment
            _resp({"response": appt}),  # GET /getappointment
        ]
        req = CreateBookingRequest(
            service_id="s-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Alice", email="alice@test.com"),
        )
        booking = await svc.create_booking(req)
        assert booking.id == "bk-1"
        assert mock_req.await_count == 2

    async def test_includes_customer_details(self):
        svc, mock_req = _make_service()
        appt = {
            "booking_id": "bk-2",
            "service_id": "s-1",
            "appointment_start_time": "01-May-2026 10:00:00",
            "status": "scheduled",
        }
        mock_req.side_effect = [
            _resp({"response": {"booking_id": "bk-2"}}),
            _resp({"response": appt}),
        ]
        req = CreateBookingRequest(
            service_id="s-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Bob", email="bob@test.com", phone="555-1234"),
        )
        await svc.create_booking(req)
        post_call = mock_req.await_args_list[0]
        body = post_call.kwargs["json"]
        assert body["customer_details"]["name"] == "Bob"
        assert body["customer_details"]["email"] == "bob@test.com"
        assert body["customer_details"]["phone_number"] == "555-1234"


class TestGetBooking:
    async def test_fetches_appointment(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {
                "response": {
                    "booking_id": "bk-99",
                    "service_id": "s-1",
                    "appointment_start_time": "01-May-2026 10:00:00",
                    "status": "scheduled",
                }
            }
        )
        booking = await svc.get_booking("bk-99")
        assert booking.id == "bk-99"
        call = mock_req.await_args_list[0]
        assert "getappointment" in call.args[1]
        assert call.kwargs["params"]["booking_id"] == "bk-99"


class TestListBookings:
    async def test_yields_bookings_with_pagination(self):
        svc, mock_req = _make_service()
        appt = {
            "booking_id": "bk-1",
            "service_id": "s-1",
            "appointment_start_time": "01-May-2026 10:00:00",
            "status": "scheduled",
        }
        mock_req.side_effect = [
            _resp({"response": {"appointments": [appt, appt], "next_page_available": True}}),
            _resp({"response": {"appointments": [appt], "next_page_available": False}}),
        ]
        items = []
        async for b in svc.list_bookings(ListBookingsRequest()):
            items.append(b)
        assert len(items) == 3
        assert mock_req.await_count == 2

    async def test_stops_when_no_next_page(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {"response": {"appointments": [], "next_page_available": False}}
        )
        items = [b async for b in svc.list_bookings(ListBookingsRequest())]
        assert items == []
        assert mock_req.await_count == 1


class TestCancelBooking:
    async def test_posts_cancel_action(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({})
        await svc.cancel_booking("bk-1")
        call = mock_req.await_args_list[0]
        assert call.args[0] == "POST"
        assert "updateappointment" in call.args[1]
        assert call.kwargs["json"]["action"] == "cancel"
        assert call.kwargs["json"]["booking_id"] == "bk-1"

    async def test_includes_reason(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({})
        await svc.cancel_booking("bk-1", reason="No longer needed")
        body = mock_req.await_args_list[0].kwargs["json"]
        assert body["reason"] == "No longer needed"


class TestUpdateBooking:
    async def test_posts_update_and_returns_booking(self):
        svc, mock_req = _make_service()
        appt = {
            "booking_id": "bk-1",
            "service_id": "s-1",
            "appointment_start_time": "01-May-2026 10:00:00",
            "status": "scheduled",
        }
        mock_req.side_effect = [
            _resp({"response": appt}),
        ]
        req = UpdateBookingRequest(booking_id="bk-1", notes="Updated notes")
        booking = await svc.update_booking(req)
        assert booking.id == "bk-1"

    async def test_falls_back_to_get_booking_when_no_id_in_response(self):
        svc, mock_req = _make_service()
        appt = {
            "booking_id": "bk-1",
            "service_id": "s-1",
            "appointment_start_time": "01-May-2026 10:00:00",
            "status": "scheduled",
        }
        mock_req.side_effect = [
            _resp({"response": {}}),  # updateappointment → no booking_id
            _resp({"response": appt}),  # fallback get_booking
        ]
        req = UpdateBookingRequest(booking_id="bk-1")
        booking = await svc.update_booking(req)
        assert booking.id == "bk-1"
        assert mock_req.await_count == 2


class TestRescheduleBooking:
    async def test_posts_to_reschedule_endpoint(self):
        svc, mock_req = _make_service()
        appt = {
            "booking_id": "bk-1",
            "service_id": "s-1",
            "appointment_start_time": "02-May-2026 10:00:00",
            "status": "scheduled",
        }
        mock_req.return_value = _resp({"response": appt})
        req = RescheduleBookingRequest(
            booking_id="bk-1",
            new_start=datetime(2026, 5, 2, 10, 0, tzinfo=timezone.utc),
        )
        booking = await svc.reschedule_booking(req)
        assert booking.id == "bk-1"
        call = mock_req.await_args_list[0]
        assert "rescheduleappointment" in call.args[1]
        assert "start_time" in call.kwargs["json"]


class TestFindCustomer:
    async def test_searches_by_email(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp(
            {
                "response": {
                    "appointments": [
                        {
                            "customer_email": "alice@test.com",
                            "customer_name": "Alice",
                            "booking_id": "bk-1",
                        }
                    ]
                }
            }
        )
        from omnidapter.services.booking.requests import FindCustomerRequest

        customer = await svc.find_customer(FindCustomerRequest(email="alice@test.com"))
        assert customer is not None
        assert customer.email == "alice@test.com"
        call = mock_req.await_args_list[0]
        assert call.kwargs["json"]["customer_email"] == "alice@test.com"

    async def test_returns_none_when_no_appointments(self):
        svc, mock_req = _make_service()
        mock_req.return_value = _resp({"response": {"appointments": []}})
        from omnidapter.services.booking.requests import FindCustomerRequest

        result = await svc.find_customer(FindCustomerRequest(email="x@test.com"))
        assert result is None

    async def test_returns_none_for_empty_request(self):
        svc, mock_req = _make_service()
        from omnidapter.services.booking.requests import FindCustomerRequest

        result = await svc.find_customer(FindCustomerRequest())
        assert result is None
        mock_req.assert_not_called()


class TestUnsupportedCustomerMethods:
    async def test_get_customer_raises(self):
        from omnidapter.core.errors import UnsupportedCapabilityError

        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            await svc.get_customer("c-1")

    async def test_create_customer_raises(self):
        from omnidapter.core.errors import UnsupportedCapabilityError

        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            await svc.create_customer(BookingCustomer(name="Alice"))
