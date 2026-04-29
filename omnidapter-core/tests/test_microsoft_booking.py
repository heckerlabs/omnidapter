"""Unit tests for MicrosoftBookingService (Graph API)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.microsoft.booking import GRAPH_BASE, MicrosoftBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
)
from omnidapter.stores.credentials import StoredCredential


def _stored(
    access_token: str = "ms-tok", business_id: str = "business@example.com"
) -> StoredCredential:
    return StoredCredential(
        provider_key="microsoft",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
        provider_config={"business_id": business_id},
    )


def _make_service(
    business_id: str = "biz@example.com",
) -> tuple[MicrosoftBookingService, AsyncMock]:
    svc = MicrosoftBookingService("conn-1", _stored(business_id=business_id))
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"value": []}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestBase:
    async def test_base_url_includes_business_id(self):
        svc, _ = _make_service("shop@company.com")
        base = await svc._base()
        assert "shop@company.com" in base
        assert base.startswith(GRAPH_BASE)

    async def test_missing_business_id_raises(self):
        stored = StoredCredential(
            provider_key="microsoft",
            auth_kind=AuthKind.OAUTH2,
            credentials=OAuth2Credentials(access_token="tok"),
        )
        svc = MicrosoftBookingService("conn-1", stored)
        svc._http.request = AsyncMock()
        with pytest.raises(ValueError, match="business_id"):
            await svc._base()


class TestCapabilities:
    def test_multi_location_not_supported(self):
        svc, _ = _make_service()
        assert not svc.supports(BookingCapability.MULTI_LOCATION)

    def test_list_staff_supported(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.LIST_STAFF)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert BookingCapability.WEBHOOKS not in svc.capabilities


class TestListServices:
    async def test_gets_services_endpoint(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {"value": []}
        await svc.list_services()
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "GET"
        assert "/services" in call.args[1]


class TestCreateBooking:
    async def test_creates_customer_if_needed(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = data
            return m

        # find_customer → not found → create_customer → get_service_type → POST /appointments
        mock_req.side_effect = [
            _resp({"value": []}),  # GET /customers (find — not found)
            _resp(
                {"id": "cust-ms-1", "displayName": "Eva", "emailAddress": "eva@test.com"}
            ),  # POST /customers (create)
            _resp({"id": "svc-1", "displayName": "Consult", "defaultDuration": "PT30M"}),  # GET /services/svc-1
            _resp(
                {
                    "id": "appt-1",
                    "serviceId": "svc-1",
                    "startDateTime": {"dateTime": "2026-05-01T10:00:00", "timeZone": "UTC"},
                    "endDateTime": {"dateTime": "2026-05-01T10:30:00", "timeZone": "UTC"},
                    "status": "booked",
                    "customers": [],
                }
            ),  # POST /appointments
        ]
        req = CreateBookingRequest(
            service_id="svc-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Eva", email="eva@test.com"),
        )
        booking = await svc.create_booking(req)
        assert booking.id == "appt-1"
        assert mock_req.await_count == 4

    async def test_appointment_post_body(self):
        svc, mock_req = _make_service()

        def _resp(data):
            m = MagicMock()
            m.json.return_value = data
            return m

        mock_req.side_effect = [
            _resp({"value": [{"id": "c-1", "displayName": "Eva", "emailAddress": "eva@test.com"}]}),  # GET /customers (find — found)
            _resp({"id": "svc-1", "displayName": "Consult", "defaultDuration": "PT30M"}),  # GET /services/svc-1
            _resp(
                {
                    "id": "appt-1",
                    "serviceId": "svc-1",
                    "startDateTime": {"dateTime": "2026-05-01T10:00:00", "timeZone": "UTC"},
                    "endDateTime": {"dateTime": "2026-05-01T10:30:00", "timeZone": "UTC"},
                    "status": "booked",
                    "customers": [],
                }
            ),  # POST /appointments
        ]
        req = CreateBookingRequest(
            service_id="svc-1",
            start=datetime(2026, 5, 1, 10, 0, tzinfo=timezone.utc),
            customer=BookingCustomer(name="Eva", email="eva@test.com"),
        )
        await svc.create_booking(req)
        appt_call = mock_req.await_args_list[-1]
        assert appt_call.args[0] == "POST"
        assert "/appointments" in appt_call.args[1]
        body = appt_call.kwargs["json"]
        assert body["serviceId"] == "svc-1"


class TestCancelBooking:
    async def test_posts_to_cancel_with_reason(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {}
        await svc.cancel_booking("appt-1", reason="Conflict")
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "POST"
        assert "/cancel" in call.args[1]
        assert call.kwargs["json"]["cancellationMessage"] == "Conflict"

    async def test_deletes_without_reason(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {}
        await svc.cancel_booking("appt-1")
        call = mock_req.await_args_list[-1]
        assert call.args[0] == "DELETE"
        assert "appt-1" in call.args[1]
