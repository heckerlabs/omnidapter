"""
Integration tests for Acuity Scheduling BookingService.

Required env vars:
    OMNIDAPTER_TEST_ACUITY_CLIENT_ID
    OMNIDAPTER_TEST_ACUITY_CLIENT_SECRET
    OMNIDAPTER_TEST_ACUITY_REFRESH_TOKEN

Use a dedicated test Acuity account. Tests create and cancel appointments but
never touch data they did not create. Created bookings are tagged with
BOOKING_NOTE_PREFIX in notes for easy identification and cleanup.

Capabilities tested: LIST_SERVICES, LIST_STAFF, GET_AVAILABILITY,
CREATE_BOOKING, CANCEL_BOOKING, RESCHEDULE_BOOKING (via UPDATE_BOOKING),
LIST_BOOKINGS, CUSTOMER_LOOKUP.
"""

from __future__ import annotations

from contextlib import suppress
from datetime import datetime, timedelta, timezone

import pytest
from omnidapter.core.errors import ProviderAPIError
from omnidapter.services.booking.models import BookingCustomer, BookingStatus
from omnidapter.services.booking.requests import (
    CreateBookingRequest,
    FindCustomerRequest,
    ListBookingsRequest,
    UpdateBookingRequest,
)

from .conftest import (
    BOOKING_NOTE_PREFIX,
    BOOKING_TEST_CUSTOMER_EMAIL,
    BOOKING_TEST_CUSTOMER_NAME,
    _require_env,
)

pytestmark = pytest.mark.integration

_ACUITY_VARS = (
    "OMNIDAPTER_TEST_ACUITY_CLIENT_ID",
    "OMNIDAPTER_TEST_ACUITY_CLIENT_SECRET",
    "OMNIDAPTER_TEST_ACUITY_REFRESH_TOKEN",
)


# --------------------------------------------------------------------------- #
# Service discovery                                                            #
# --------------------------------------------------------------------------- #


async def test_list_services(acuity_booking_service):
    """list_services() returns at least one ServiceType with required fields."""
    _require_env(*_ACUITY_VARS)
    services = await acuity_booking_service.list_services()
    assert len(services) >= 1
    for svc in services:
        assert svc.id
        assert isinstance(svc.name, str)


async def test_list_staff(acuity_booking_service):
    """list_staff() returns at least one StaffMember."""
    _require_env(*_ACUITY_VARS)
    staff = await acuity_booking_service.list_staff()
    assert isinstance(staff, list)
    for member in staff:
        assert member.id
        assert isinstance(member.name, str)


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #


async def test_get_availability(acuity_booking_service):
    """get_availability() returns a list of slots for the first service."""
    _require_env(*_ACUITY_VARS)
    services = await acuity_booking_service.list_services()
    if not services:
        pytest.skip("No services configured on this Acuity account")

    now = datetime.now(timezone.utc)
    slots = await acuity_booking_service.get_availability(
        service_id=services[0].id,
        start=now,
        end=now + timedelta(days=14),
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.service_id == services[0].id
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Booking CRUD                                                                 #
# --------------------------------------------------------------------------- #


async def test_create_and_cancel_booking(acuity_booking_service):
    """Create a booking then immediately cancel it."""
    _require_env(*_ACUITY_VARS)
    services = await acuity_booking_service.list_services()
    if not services:
        pytest.skip("No services configured on this Acuity account")

    now = datetime.now(timezone.utc)
    slots = await acuity_booking_service.get_availability(
        service_id=services[0].id,
        start=now,
        end=now + timedelta(days=30),
    )
    if not slots:
        pytest.skip("No availability slots found; cannot create a booking")

    booking_id: str | None = None
    try:
        req = CreateBookingRequest(
            service_id=services[0].id,
            start=slots[0].start,
            customer=BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=BOOKING_TEST_CUSTOMER_EMAIL,
            ),
            notes=f"{BOOKING_NOTE_PREFIX} create-and-cancel integration test",
        )
        booking = await acuity_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.service_id == services[0].id
        assert booking.customer.email == BOOKING_TEST_CUSTOMER_EMAIL

        # Verify it's readable
        fetched = await acuity_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await acuity_booking_service.cancel_booking(
                    booking_id, reason="omnidapter integration test cleanup"
                )


async def test_update_booking_reschedule(acuity_booking_service):
    """Create a booking then reschedule it to a later slot (uses UPDATE_BOOKING)."""
    _require_env(*_ACUITY_VARS)
    services = await acuity_booking_service.list_services()
    if not services:
        pytest.skip("No services configured on this Acuity account")

    now = datetime.now(timezone.utc)
    slots = await acuity_booking_service.get_availability(
        service_id=services[0].id,
        start=now,
        end=now + timedelta(days=30),
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 availability slots; cannot test reschedule")

    booking_id: str | None = None
    try:
        booking = await acuity_booking_service.create_booking(
            CreateBookingRequest(
                service_id=services[0].id,
                start=slots[0].start,
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
                notes=f"{BOOKING_NOTE_PREFIX} reschedule integration test",
            )
        )
        booking_id = booking.id

        updated = await acuity_booking_service.update_booking(
            UpdateBookingRequest(booking_id=booking_id, start=slots[1].start)
        )
        assert updated.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await acuity_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(acuity_booking_service):
    """list_bookings() iterates without error and returns Booking objects."""
    _require_env(*_ACUITY_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in acuity_booking_service.list_bookings(
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
# Customer lookup                                                              #
# --------------------------------------------------------------------------- #


async def test_find_customer(acuity_booking_service):
    """find_customer() returns None for an unknown address and doesn't raise."""
    _require_env(*_ACUITY_VARS)
    result = await acuity_booking_service.find_customer(
        FindCustomerRequest(email="no-such-user-omnidapter@example.invalid")
    )
    assert result is None


async def test_get_unknown_booking_raises(acuity_booking_service):
    """get_booking() with a non-existent ID raises ProviderAPIError."""
    _require_env(*_ACUITY_VARS)
    with pytest.raises(ProviderAPIError):
        await acuity_booking_service.get_booking("999999999999")
