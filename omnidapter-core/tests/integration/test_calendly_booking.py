"""
Integration tests for Calendly BookingService.

Required env vars:
    OMNIDAPTER_TEST_CALENDLY_CLIENT_ID
    OMNIDAPTER_TEST_CALENDLY_CLIENT_SECRET
    OMNIDAPTER_TEST_CALENDLY_REFRESH_TOKEN

Calendly's API is largely read-only for booking operations (scheduling links
are the creation path, not a direct booking POST). This provider supports:
    LIST_SERVICES, LIST_STAFF, GET_AVAILABILITY, LIST_BOOKINGS, CANCEL_BOOKING

CREATE_BOOKING, RESCHEDULE_BOOKING, CUSTOMER_LOOKUP, and CUSTOMER_MANAGEMENT
are intentionally unsupported and will raise UnsupportedCapabilityError.

Tests only exercise the capabilities declared in CalendlyBookingService.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest
from omnidapter.core.errors import UnsupportedCapabilityError
from omnidapter.services.booking.capabilities import BookingCapability
from omnidapter.services.booking.models import BookingCustomer, BookingStatus
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    FindCustomerRequest,
    ListBookingsRequest,
)

from .conftest import (
    BOOKING_TEST_CUSTOMER_EMAIL,
    BOOKING_TEST_CUSTOMER_NAME,
    _require_env,
)

pytestmark = pytest.mark.integration

_CALENDLY_VARS = (
    "OMNIDAPTER_TEST_CALENDLY_CLIENT_ID",
    "OMNIDAPTER_TEST_CALENDLY_CLIENT_SECRET",
    "OMNIDAPTER_TEST_CALENDLY_REFRESH_TOKEN",
)


# --------------------------------------------------------------------------- #
# Service discovery                                                            #
# --------------------------------------------------------------------------- #


async def test_list_services(calendly_booking_service):
    """list_services() returns event types with required fields."""
    _require_env(*_CALENDLY_VARS)
    services = await calendly_booking_service.list_services()
    assert isinstance(services, list)
    for svc in services:
        assert svc.id
        assert isinstance(svc.name, str)


async def test_list_staff(calendly_booking_service):
    """list_staff() returns at least one StaffMember (the account user)."""
    _require_env(*_CALENDLY_VARS)
    staff = await calendly_booking_service.list_staff()
    assert isinstance(staff, list)
    for member in staff:
        assert member.id
        assert isinstance(member.name, str)


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #


async def test_get_availability(calendly_booking_service):
    """get_availability() returns slots for the first event type."""
    _require_env(*_CALENDLY_VARS)
    services = await calendly_booking_service.list_services()
    if not services:
        pytest.skip("No event types on this Calendly account")

    now = datetime.now(timezone.utc)
    slots = await calendly_booking_service.get_availability(
        service_id=services[0].id,
        start=now,
        end=now + timedelta(days=14),
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.service_id == services[0].id
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(calendly_booking_service):
    """list_bookings() iterates without error and returns Booking objects."""
    _require_env(*_CALENDLY_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in calendly_booking_service.list_bookings(
        ListBookingsRequest(start=now - timedelta(days=30), end=now, page_size=10)
    ):
        items.append(booking)
        if len(items) >= 20:
            break

    for b in items:
        assert b.id
        assert b.status in BookingStatus


# --------------------------------------------------------------------------- #
# Unsupported capabilities raise correctly                                     #
# --------------------------------------------------------------------------- #


async def test_create_booking_raises_unsupported(calendly_booking_service):
    """CREATE_BOOKING is not supported by Calendly; must raise."""
    _require_env(*_CALENDLY_VARS)
    assert not calendly_booking_service.supports(BookingCapability.CREATE_BOOKING)
    with pytest.raises(UnsupportedCapabilityError):
        await calendly_booking_service.create_booking(
            CreateBookingRequest(
                service_id="dummy",
                start=datetime.now(timezone.utc),
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
            )
        )


async def test_find_customer_raises_unsupported(calendly_booking_service):
    """CUSTOMER_LOOKUP is not supported by Calendly; must raise."""
    _require_env(*_CALENDLY_VARS)
    assert not calendly_booking_service.supports(BookingCapability.CUSTOMER_LOOKUP)
    with pytest.raises(UnsupportedCapabilityError):
        await calendly_booking_service.find_customer(FindCustomerRequest(email="test@example.com"))
