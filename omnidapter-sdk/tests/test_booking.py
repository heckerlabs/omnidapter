"""Integration smoke tests for BookingApi — verifies routing and error parsing.

Each test hits the live server with a non-existent connection UUID and
asserts that the server responds with 404 (connection_not_found). This
confirms that every booking endpoint is correctly wired into the router,
that the SDK's BookingApi sends requests to the right paths, and that
ApiException is raised with the correct HTTP status.

Docker (openapi-generator-cli) is required to generate the SDK before
these tests can run. If the SDK is not generated, the sdk_client fixture
skips the entire suite.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import (
    BookingCustomer,
    CreateBookingRequest,
    RescheduleBookingRequest,
    UpdateBookingRequest,
)

pytestmark = pytest.mark.integration

FAKE_CONNECTION = "00000000-0000-0000-0000-000000000000"
FAKE_SERVICE = "svc_fake"
FAKE_APPOINTMENT = "appt_fake"
FAKE_STAFF = "staff_fake"
FAKE_CUSTOMER = "cust_fake"

_NOW = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
_LATER = datetime(2026, 6, 1, 11, 0, 0, tzinfo=timezone.utc)


# ── Services ──────────────────────────────────────────────────────────────────


def test_list_booking_services_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.list_booking_services(FAKE_CONNECTION)
    assert exc_info.value.status == 404


def test_get_booking_service_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.get_booking_service(FAKE_CONNECTION, FAKE_SERVICE)
    assert exc_info.value.status == 404


# ── Staff ─────────────────────────────────────────────────────────────────────


def test_list_booking_staff_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.list_booking_staff(FAKE_CONNECTION)
    assert exc_info.value.status == 404


def test_get_booking_staff_member_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.get_booking_staff_member(FAKE_CONNECTION, FAKE_STAFF)
    assert exc_info.value.status == 404


# ── Locations ─────────────────────────────────────────────────────────────────


def test_list_booking_locations_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.list_booking_locations(FAKE_CONNECTION)
    assert exc_info.value.status == 404


# ── Availability ──────────────────────────────────────────────────────────────


def test_get_booking_availability_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.get_booking_availability(
            FAKE_CONNECTION,
            service_id=FAKE_SERVICE,
            start=_NOW,
            end=_LATER,
        )
    assert exc_info.value.status == 404


# ── Appointments ──────────────────────────────────────────────────────────────


def test_create_booking_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.create_booking(
            FAKE_CONNECTION,
            CreateBookingRequest(
                service_id=FAKE_SERVICE,
                start=_NOW,
                customer=BookingCustomer(name="Test User", email="test@example.com"),
            ),
        )
    assert exc_info.value.status == 404


def test_list_bookings_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.list_bookings(FAKE_CONNECTION)
    assert exc_info.value.status == 404


def test_get_booking_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.get_booking(FAKE_CONNECTION, FAKE_APPOINTMENT)
    assert exc_info.value.status == 404


def test_update_booking_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.update_booking(
            FAKE_CONNECTION,
            FAKE_APPOINTMENT,
            UpdateBookingRequest(booking_id=FAKE_APPOINTMENT, start=_LATER),
        )
    assert exc_info.value.status == 404


def test_cancel_booking_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.cancel_booking(FAKE_CONNECTION, FAKE_APPOINTMENT)
    assert exc_info.value.status == 404


def test_reschedule_booking_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.reschedule_booking(
            FAKE_CONNECTION,
            FAKE_APPOINTMENT,
            RescheduleBookingRequest(booking_id=FAKE_APPOINTMENT, new_start=_LATER),
        )
    assert exc_info.value.status == 404


# ── Customers ─────────────────────────────────────────────────────────────────


def test_find_booking_customer_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.find_booking_customer(FAKE_CONNECTION, email="nobody@example.invalid")
    assert exc_info.value.status == 404


def test_get_booking_customer_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.get_booking_customer(FAKE_CONNECTION, FAKE_CUSTOMER)
    assert exc_info.value.status == 404


def test_create_booking_customer_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.booking.create_booking_customer(
            FAKE_CONNECTION,
            BookingCustomer(name="Test User", email="test@example.com"),
        )
    assert exc_info.value.status == 404
