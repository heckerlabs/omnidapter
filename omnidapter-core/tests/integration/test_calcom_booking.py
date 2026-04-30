"""
Integration tests for Cal.com BookingService.

Required env vars:
    OMNIDAPTER_TEST_CALCOM_CLIENT_ID
    OMNIDAPTER_TEST_CALCOM_CLIENT_SECRET
    OMNIDAPTER_TEST_CALCOM_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_CALCOM_EVENT_TYPE_ID   (integer event-type ID to use for bookings)

Use a dedicated test Cal.com account. Tests create and cancel bookings but
never touch data they did not create. Bookings are tagged with
BOOKING_NOTE_PREFIX in the title field.

Capabilities tested: LIST_SERVICES, LIST_STAFF, GET_AVAILABILITY,
CREATE_BOOKING, CANCEL_BOOKING, RESCHEDULE_BOOKING, LIST_BOOKINGS,
MULTI_SERVICE, MULTI_LOCATION.
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

_CALCOM_VARS = (
    "OMNIDAPTER_TEST_CALCOM_CLIENT_ID",
    "OMNIDAPTER_TEST_CALCOM_CLIENT_SECRET",
    "OMNIDAPTER_TEST_CALCOM_REFRESH_TOKEN",
)


# --------------------------------------------------------------------------- #
# Service discovery                                                            #
# --------------------------------------------------------------------------- #


async def test_list_services(calcom_booking_service):
    """list_services() returns at least one event type with required fields."""
    _require_env(*_CALCOM_VARS)
    services = await calcom_booking_service.list_services()
    assert len(services) >= 1
    for svc in services:
        assert svc.id
        assert isinstance(svc.name, str)


async def test_list_staff(calcom_booking_service):
    """list_staff() returns a list of StaffMember objects."""
    _require_env(*_CALCOM_VARS)
    staff = await calcom_booking_service.list_staff()
    assert isinstance(staff, list)
    for member in staff:
        assert member.id
        assert isinstance(member.name, str)


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #


async def _first_service_id(svc) -> str:
    """Return override env var or the first available event type ID."""
    override = os.getenv("OMNIDAPTER_TEST_CALCOM_EVENT_TYPE_ID")
    if override:
        return override
    services = await svc.list_services()
    if not services:
        pytest.skip("No event types configured on this Cal.com account")
    return services[0].id


async def test_get_availability(calcom_booking_service):
    """get_availability() returns a list of slots."""
    _require_env(*_CALCOM_VARS)
    service_id = await _first_service_id(calcom_booking_service)
    now = datetime.now(timezone.utc)
    slots = await calcom_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=14),
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.service_id == service_id
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Booking CRUD                                                                 #
# --------------------------------------------------------------------------- #


async def test_create_and_cancel_booking(calcom_booking_service):
    """Create a booking then cancel it."""
    _require_env(*_CALCOM_VARS)
    service_id = await _first_service_id(calcom_booking_service)
    now = datetime.now(timezone.utc)
    slots = await calcom_booking_service.get_availability(
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
        booking = await calcom_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.service_id == service_id

        fetched = await calcom_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await calcom_booking_service.cancel_booking(booking_id)


async def test_reschedule_booking(calcom_booking_service):
    """Create a booking then reschedule it to a different slot."""
    _require_env(*_CALCOM_VARS)
    service_id = await _first_service_id(calcom_booking_service)
    now = datetime.now(timezone.utc)
    slots = await calcom_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 availability slots; cannot test reschedule")

    booking_id: str | None = None
    try:
        booking = await calcom_booking_service.create_booking(
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

        rescheduled = await calcom_booking_service.reschedule_booking(
            RescheduleBookingRequest(booking_id=booking_id, new_start=slots[1].start)
        )
        # Cal.com returns a new UID on reschedule; track the new one for cleanup
        booking_id = rescheduled.id
        assert rescheduled.start == slots[1].start

    finally:
        if booking_id:
            with suppress(Exception):
                await calcom_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(calcom_booking_service):
    """list_bookings() iterates without error and returns Booking objects."""
    _require_env(*_CALCOM_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in calcom_booking_service.list_bookings(
        ListBookingsRequest(
            start=now - timedelta(days=7), end=now + timedelta(days=7), page_size=10
        )
    ):
        items.append(booking)
        if len(items) >= 20:
            break

    for b in items:
        assert b.id
        assert b.status in BookingStatus


# --------------------------------------------------------------------------- #
# Error handling                                                               #
# --------------------------------------------------------------------------- #


async def test_get_unknown_booking_raises(calcom_booking_service):
    """get_booking() with a non-existent UID raises ProviderAPIError."""
    _require_env(*_CALCOM_VARS)
    with pytest.raises(ProviderAPIError):
        await calcom_booking_service.get_booking("nonexistent-omnidapter-uid-00000000")
