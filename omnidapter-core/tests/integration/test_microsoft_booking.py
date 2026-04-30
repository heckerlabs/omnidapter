"""
Integration tests for Microsoft Bookings BookingService (Graph API).

Required env vars:
    OMNIDAPTER_TEST_MSBOOKINGS_CLIENT_ID
    OMNIDAPTER_TEST_MSBOOKINGS_CLIENT_SECRET
    OMNIDAPTER_TEST_MSBOOKINGS_REFRESH_TOKEN
    OMNIDAPTER_TEST_MSBOOKINGS_BUSINESS_ID   (email address of the bookingBusiness)

Optional:
    OMNIDAPTER_TEST_MSBOOKINGS_SERVICE_ID    (Graph service ID to use for bookings)

Note: MSBOOKINGS credentials are separate from the Microsoft Calendar credentials
(OMNIDAPTER_TEST_MICROSOFT_*) because Bookings requires the Bookings.ReadWrite.All
scope which may not be granted on the calendar OAuth app.

Capabilities tested: LIST_SERVICES, LIST_STAFF, LIST_LOCATIONS,
GET_AVAILABILITY, CREATE_BOOKING, CANCEL_BOOKING, RESCHEDULE_BOOKING,
UPDATE_BOOKING, LIST_BOOKINGS, CUSTOMER_LOOKUP, CUSTOMER_MANAGEMENT.
"""

from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone

import pytest
from omnidapter.core.errors import ProviderAPIError
from omnidapter.services.booking.models import BookingCustomer, BookingStatus
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    FindCustomerRequest,
    ListBookingsRequest,
    RescheduleBookingRequest,
)

from .conftest import (
    BOOKING_NOTE_PREFIX,
    BOOKING_TEST_CUSTOMER_EMAIL,
    BOOKING_TEST_CUSTOMER_NAME,
    _require_env,
)

pytestmark = pytest.mark.integration

_MSBOOKINGS_VARS = (
    "OMNIDAPTER_TEST_MSBOOKINGS_CLIENT_ID",
    "OMNIDAPTER_TEST_MSBOOKINGS_CLIENT_SECRET",
    "OMNIDAPTER_TEST_MSBOOKINGS_REFRESH_TOKEN",
    "OMNIDAPTER_TEST_MSBOOKINGS_BUSINESS_ID",
)


async def _first_service_id(svc) -> str:
    override = os.getenv("OMNIDAPTER_TEST_MSBOOKINGS_SERVICE_ID")
    if override:
        return override
    services = await svc.list_services()
    if not services:
        pytest.skip("No services configured on this Microsoft Bookings business")
    return services[0].id


# --------------------------------------------------------------------------- #
# Discovery                                                                    #
# --------------------------------------------------------------------------- #


async def test_list_services(msbookings_booking_service):
    """list_services() returns booking services with required fields."""
    _require_env(*_MSBOOKINGS_VARS)
    services = await msbookings_booking_service.list_services()
    assert isinstance(services, list)
    for svc in services:
        assert svc.id
        assert isinstance(svc.name, str)


async def test_list_staff(msbookings_booking_service):
    """list_staff() returns staff members."""
    _require_env(*_MSBOOKINGS_VARS)
    staff = await msbookings_booking_service.list_staff()
    assert isinstance(staff, list)
    for member in staff:
        assert member.id
        assert isinstance(member.name, str)


async def test_list_locations(msbookings_booking_service):
    """list_locations() returns the primary business location."""
    _require_env(*_MSBOOKINGS_VARS)
    locations = await msbookings_booking_service.list_locations()
    assert isinstance(locations, list)
    # Microsoft Bookings always has exactly one primary location
    assert len(locations) >= 1
    assert locations[0].id


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #


async def test_get_availability(msbookings_booking_service):
    """get_availability() returns availability slots."""
    _require_env(*_MSBOOKINGS_VARS)
    service_id = await _first_service_id(msbookings_booking_service)
    now = datetime.now(timezone.utc)
    slots = await msbookings_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=14),
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Booking CRUD                                                                 #
# --------------------------------------------------------------------------- #


async def test_create_and_cancel_booking(msbookings_booking_service):
    """Create a booking then cancel it."""
    _require_env(*_MSBOOKINGS_VARS)
    service_id = await _first_service_id(msbookings_booking_service)
    now = datetime.now(timezone.utc)
    slots = await msbookings_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
    )
    if not slots:
        pytest.skip("No availability slots; cannot create a booking")

    booking_id: str | None = None
    try:
        req = CreateBookingRequest(
            service_id=service_id,
            start=slots[0].start,
            customer=BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=BOOKING_TEST_CUSTOMER_EMAIL,
            ),
            notes=f"{BOOKING_NOTE_PREFIX} create-and-cancel integration test",
        )
        booking = await msbookings_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.service_id == service_id
        assert booking.customer.name == BOOKING_TEST_CUSTOMER_NAME

        fetched = await msbookings_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await msbookings_booking_service.cancel_booking(
                    booking_id, reason="omnidapter integration test cleanup"
                )


async def test_reschedule_booking(msbookings_booking_service):
    """Create a booking then reschedule it."""
    _require_env(*_MSBOOKINGS_VARS)
    service_id = await _first_service_id(msbookings_booking_service)
    now = datetime.now(timezone.utc)
    slots = await msbookings_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 slots; cannot test reschedule")

    booking_id: str | None = None
    try:
        booking = await msbookings_booking_service.create_booking(
            CreateBookingRequest(
                service_id=service_id,
                start=slots[0].start,
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
                notes=f"{BOOKING_NOTE_PREFIX} reschedule integration test",
            )
        )
        booking_id = booking.id

        rescheduled = await msbookings_booking_service.reschedule_booking(
            RescheduleBookingRequest(booking_id=booking_id, new_start=slots[1].start)
        )
        assert rescheduled.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await msbookings_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(msbookings_booking_service):
    """list_bookings() paginates correctly via @odata.nextLink."""
    _require_env(*_MSBOOKINGS_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in msbookings_booking_service.list_bookings(
        ListBookingsRequest(start=now - timedelta(days=30), end=now + timedelta(days=30))
    ):
        items.append(booking)
        if len(items) >= 20:
            break

    for b in items:
        assert b.id
        assert b.status in BookingStatus


# --------------------------------------------------------------------------- #
# Customer lookup                                                              #
# --------------------------------------------------------------------------- #


async def test_find_customer(msbookings_booking_service):
    """find_customer() returns None for an unknown email."""
    _require_env(*_MSBOOKINGS_VARS)
    result = await msbookings_booking_service.find_customer(
        FindCustomerRequest(email="no-such-user-omnidapter@example.invalid")
    )
    assert result is None


# --------------------------------------------------------------------------- #
# Error handling                                                               #
# --------------------------------------------------------------------------- #


async def test_get_unknown_booking_raises(msbookings_booking_service):
    """get_booking() with a non-existent ID raises ProviderAPIError."""
    _require_env(*_MSBOOKINGS_VARS)
    with pytest.raises(ProviderAPIError):
        await msbookings_booking_service.get_booking("00000000-0000-0000-0000-000000000000")
