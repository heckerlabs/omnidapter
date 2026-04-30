"""
Integration tests for Zoho Bookings BookingService.

Required env vars:
    OMNIDAPTER_TEST_ZOHO_CLIENT_ID
    OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET
    OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_ZOHO_BOOKING_WORKSPACE_ID  (defaults to first workspace)
    OMNIDAPTER_TEST_ZOHO_BOOKING_SERVICE_ID    (defaults to first configured service)

Use a dedicated test Zoho Bookings account. Tests create and cancel appointments
but never touch data they did not create. Bookings are tagged with
BOOKING_NOTE_PREFIX in the notes field.

Capabilities tested: LIST_SERVICES, LIST_STAFF, GET_AVAILABILITY,
CREATE_BOOKING, GET_BOOKING, CANCEL_BOOKING, RESCHEDULE_BOOKING, LIST_BOOKINGS,
CUSTOMER_LOOKUP.
"""

from __future__ import annotations

import os
from contextlib import suppress
from datetime import datetime, timedelta, timezone

import pytest
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

_ZOHO_VARS = (
    "OMNIDAPTER_TEST_ZOHO_CLIENT_ID",
    "OMNIDAPTER_TEST_ZOHO_CLIENT_SECRET",
    "OMNIDAPTER_TEST_ZOHO_REFRESH_TOKEN",
)


async def _first_service_id(svc) -> str:
    """Return override env var or the ID of the first configured Zoho Bookings service."""
    override = os.getenv("OMNIDAPTER_TEST_ZOHO_BOOKING_SERVICE_ID")
    if override:
        return override
    services = await svc.list_services()
    if not services:
        pytest.skip("No services configured on this Zoho Bookings account")
    return services[0].id


# --------------------------------------------------------------------------- #
# Service discovery                                                            #
# --------------------------------------------------------------------------- #


async def test_list_services(zoho_booking_service):
    """list_services() returns at least one service with required fields."""
    _require_env(*_ZOHO_VARS)
    services = await zoho_booking_service.list_services()
    assert len(services) >= 1
    for svc in services:
        assert svc.id
        assert isinstance(svc.name, str)


async def test_list_staff(zoho_booking_service):
    """list_staff() returns a list of StaffMember objects."""
    _require_env(*_ZOHO_VARS)
    staff = await zoho_booking_service.list_staff()
    assert isinstance(staff, list)
    for member in staff:
        assert member.id
        assert isinstance(member.name, str)


async def test_list_staff_filtered_by_service(zoho_booking_service):
    """list_staff(service_id=...) returns staff for that service."""
    _require_env(*_ZOHO_VARS)
    service_id = await _first_service_id(zoho_booking_service)
    staff = await zoho_booking_service.list_staff(service_id=service_id)
    assert isinstance(staff, list)


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #


async def test_get_availability(zoho_booking_service):
    """get_availability() returns a list of slots."""
    _require_env(*_ZOHO_VARS)
    service_id = await _first_service_id(zoho_booking_service)
    now = datetime.now(timezone.utc)
    slots = await zoho_booking_service.get_availability(
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


async def test_create_and_cancel_booking(zoho_booking_service):
    """Create a booking then cancel it."""
    _require_env(*_ZOHO_VARS)
    service_id = await _first_service_id(zoho_booking_service)
    now = datetime.now(timezone.utc)
    slots = await zoho_booking_service.get_availability(
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
        booking = await zoho_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.service_id

        fetched = await zoho_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await zoho_booking_service.cancel_booking(booking_id)


async def test_reschedule_booking(zoho_booking_service):
    """Create a booking then reschedule it to a later slot."""
    _require_env(*_ZOHO_VARS)
    service_id = await _first_service_id(zoho_booking_service)
    now = datetime.now(timezone.utc)
    slots = await zoho_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 availability slots; cannot test reschedule")

    booking_id: str | None = None
    try:
        booking = await zoho_booking_service.create_booking(
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

        rescheduled = await zoho_booking_service.reschedule_booking(
            RescheduleBookingRequest(booking_id=booking_id, new_start=slots[1].start)
        )
        assert rescheduled.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await zoho_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(zoho_booking_service):
    """list_bookings() iterates without error and returns Booking objects."""
    _require_env(*_ZOHO_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in zoho_booking_service.list_bookings(
        ListBookingsRequest(
            start=now - timedelta(days=30), end=now + timedelta(days=30), page_size=10
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


async def test_find_customer_unknown_returns_none(zoho_booking_service):
    """find_customer() returns None for an email with no appointments."""
    _require_env(*_ZOHO_VARS)
    result = await zoho_booking_service.find_customer(
        FindCustomerRequest(email="no-such-user-omnidapter@example.invalid")
    )
    assert result is None


async def test_find_customer_by_email(zoho_booking_service):
    """After creating a booking, find_customer() locates the customer by email."""
    _require_env(*_ZOHO_VARS)
    service_id = await _first_service_id(zoho_booking_service)
    now = datetime.now(timezone.utc)
    slots = await zoho_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
    )
    if not slots:
        pytest.skip("No availability slots; cannot test customer lookup")

    booking_id: str | None = None
    try:
        booking = await zoho_booking_service.create_booking(
            CreateBookingRequest(
                service_id=service_id,
                start=slots[0].start,
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
                notes=f"{BOOKING_NOTE_PREFIX} customer-lookup integration test",
            )
        )
        booking_id = booking.id

        customer = await zoho_booking_service.find_customer(
            FindCustomerRequest(email=BOOKING_TEST_CUSTOMER_EMAIL)
        )
        assert customer is not None
        assert customer.email == BOOKING_TEST_CUSTOMER_EMAIL

    finally:
        if booking_id:
            with suppress(Exception):
                await zoho_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Unsupported operations                                                       #
# --------------------------------------------------------------------------- #


async def test_get_customer_raises_unsupported(zoho_booking_service):
    """get_customer() raises UnsupportedCapabilityError — no standalone endpoint."""
    _require_env(*_ZOHO_VARS)
    from omnidapter.core.errors import UnsupportedCapabilityError

    with pytest.raises(UnsupportedCapabilityError):
        await zoho_booking_service.get_customer("any-id")


async def test_create_customer_raises_unsupported(zoho_booking_service):
    """create_customer() raises UnsupportedCapabilityError — created implicitly via booking."""
    _require_env(*_ZOHO_VARS)
    from omnidapter.core.errors import UnsupportedCapabilityError

    with pytest.raises(UnsupportedCapabilityError):
        await zoho_booking_service.create_customer(
            BookingCustomer(name="Test", email="test@example.com")
        )
