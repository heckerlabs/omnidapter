"""Unit tests for CalendlyBookingService."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.auth.models import OAuth2Credentials
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.core.metadata import AuthKind
from omnidapter.providers.calendly.booking import CalendlyBookingService
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.stores.credentials import StoredCredential


def _stored(access_token: str = "cly-tok") -> StoredCredential:
    return StoredCredential(
        provider_key="calendly",
        auth_kind=AuthKind.OAUTH2,
        credentials=OAuth2Credentials(access_token=access_token),
    )


def _make_service() -> tuple[CalendlyBookingService, AsyncMock]:
    svc = CalendlyBookingService("conn-1", _stored())
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"collection": []}
    svc._http.request = AsyncMock(return_value=mock_resp)
    return svc, svc._http.request


class TestCapabilities:
    def test_limited_capability_set(self):
        svc, _ = _make_service()
        assert svc.supports(BookingCapability.LIST_SERVICES)
        assert svc.supports(BookingCapability.GET_AVAILABILITY)
        assert not svc.supports(BookingCapability.CREATE_BOOKING)
        assert not svc.supports(BookingCapability.CUSTOMER_MANAGEMENT)

    def test_webhooks_not_in_capabilities(self):
        svc, _ = _make_service()
        assert BookingCapability.WEBHOOKS not in svc.capabilities

    def test_create_booking_raises_unsupported(self):
        svc, _ = _make_service()
        with pytest.raises(UnsupportedCapabilityError):
            svc._require_capability(BookingCapability.CREATE_BOOKING)


class TestGetUserUri:
    async def test_caches_after_first_call(self):
        svc, mock_req = _make_service()
        mock_req.return_value.json.return_value = {
            "resource": {
                "uri": "https://api.calendly.com/users/user-1",
                "current_organization": "https://api.calendly.com/organizations/org-1",
            }
        }
        uri1 = await svc._get_user_uri()
        uri2 = await svc._get_user_uri()
        assert uri1 == uri2
        assert mock_req.await_count == 1  # cached after first call


class TestListServices:
    async def test_filters_by_user_uri(self):
        svc, mock_req = _make_service()
        # First call: /users/me
        me_resp = MagicMock()
        me_resp.json.return_value = {
            "resource": {
                "uri": "https://api.calendly.com/users/u1",
                "current_organization": "https://api.calendly.com/organizations/o1",
            }
        }
        # Second call: /event_types
        et_resp = MagicMock()
        et_resp.json.return_value = {
            "collection": [
                {
                    "uri": "https://api.calendly.com/event_types/et-1",
                    "name": "30min",
                    "duration": 30,
                }
            ]
        }
        mock_req.side_effect = [me_resp, et_resp]
        services = await svc.list_services()
        assert len(services) == 1
        assert services[0].name == "30min"
        et_call = mock_req.await_args_list[-1]
        assert "user" in et_call.kwargs["params"]


class TestManagementUrls:
    async def test_cancel_and_reschedule_urls_populated(self):
        from omnidapter.providers.calendly.mappers import to_booking_from_invitee

        event = {
            "uri": "https://api.calendly.com/scheduled_events/ev-1",
            "event_type": "https://api.calendly.com/event_types/et-1",
            "start_time": "2026-05-01T10:00:00Z",
            "end_time": "2026-05-01T10:30:00Z",
            "status": "active",
        }
        invitee = {
            "uri": "https://api.calendly.com/scheduled_events/ev-1/invitees/inv-1",
            "name": "Jane",
            "email": "jane@test.com",
            "status": "active",
            "cancel_url": "https://calendly.com/cancellations/inv-1",
            "reschedule_url": "https://calendly.com/reschedulings/inv-1",
            "timezone": "UTC",
        }
        booking = to_booking_from_invitee(event, invitee)
        assert booking.management_urls is not None
        assert "cancel" in booking.management_urls
        assert "reschedule" in booking.management_urls
