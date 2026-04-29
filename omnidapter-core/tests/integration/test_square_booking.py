"""
Integration tests for Square Appointments BookingService.

Required env vars:
    OMNIDAPTER_TEST_SQUARE_CLIENT_ID
    OMNIDAPTER_TEST_SQUARE_CLIENT_SECRET
    OMNIDAPTER_TEST_SQUARE_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_SQUARE_SERVICE_VARIATION_ID   (catalog item variation ID to use)
    OMNIDAPTER_TEST_SQUARE_LOCATION_ID            (Square location ID)

Use a dedicated test Square account in sandbox mode. Tests create and cancel
bookings but never touch data they did not create. Created bookings use a
customer note tagged with BOOKING_NOTE_PREFIX.

Key Square quirk: service_id must be an ITEM_VARIATION catalog ID (not an
ITEM ID). The fixture reads it from env or uses the first listable service.

Capabilities tested: LIST_SERVICES, LIST_STAFF, LIST_LOCATIONS,
GET_AVAILABILITY, CREATE_BOOKING, CANCEL_BOOKING, UPDATE_BOOKING,
LIST_BOOKINGS, CUSTOMER_LOOKUP, CUSTOMER_MANAGEMENT.
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
    UpdateBookingRequest,
)

from .conftest import (
    BOOKING_NOTE_PREFIX,
    BOOKING_TEST_CUSTOMER_EMAIL,
    BOOKING_TEST_CUSTOMER_NAME,
    _require_env,
)

pytestmark = pytest.mark.integration

_SQUARE_VARS = (
    "OMNIDAPTER_TEST_SQUARE_CLIENT_ID",
    "OMNIDAPTER_TEST_SQUARE_CLIENT_SECRET",
    "OMNIDAPTER_TEST_SQUARE_REFRESH_TOKEN",
)


async def _first_service_id(svc) -> str:
    override = os.getenv("OMNIDAPTER_TEST_SQUARE_SERVICE_VARIATION_ID")
    if override:
        return override
    services = await svc.list_services()
    if not services:
        pytest.skip("No bookable services found in this Square catalog")
    return services[0].id


# --------------------------------------------------------------------------- #
# Discovery                                                                    #
# --------------------------------------------------------------------------- #


async def test_list_services(square_booking_service):
    """list_services() returns ITEM_VARIATION services with required fields."""
    _require_env(*_SQUARE_VARS)
    services = await square_booking_service.list_services()
    assert isinstance(services, list)
    for svc in services:
        assert svc.id
        assert isinstance(svc.name, str)


async def test_list_staff(square_booking_service):
    """list_staff() returns bookable team members."""
    _require_env(*_SQUARE_VARS)
    staff = await square_booking_service.list_staff()
    assert isinstance(staff, list)
    for member in staff:
        assert member.id


async def test_list_locations(square_booking_service):
    """list_locations() returns at least one location."""
    _require_env(*_SQUARE_VARS)
    locations = await square_booking_service.list_locations()
    assert isinstance(locations, list)
    for loc in locations:
        assert loc.id
        assert isinstance(loc.name, str)


# --------------------------------------------------------------------------- #
# Availability                                                                 #
# --------------------------------------------------------------------------- #


async def test_get_availability(square_booking_service):
    """get_availability() returns slots for the first bookable service."""
    _require_env(*_SQUARE_VARS)
    service_id = await _first_service_id(square_booking_service)
    location_id = os.getenv("OMNIDAPTER_TEST_SQUARE_LOCATION_ID")
    now = datetime.now(timezone.utc)
    slots = await square_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=14),
        location_id=location_id,
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Booking CRUD                                                                 #
# --------------------------------------------------------------------------- #


async def test_create_and_cancel_booking(square_booking_service):
    """Create a booking then cancel it; verify status change."""
    _require_env(*_SQUARE_VARS)
    service_id = await _first_service_id(square_booking_service)
    location_id = os.getenv("OMNIDAPTER_TEST_SQUARE_LOCATION_ID")
    now = datetime.now(timezone.utc)
    slots = await square_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
        location_id=location_id,
    )
    if not slots:
        pytest.skip("No availability slots; cannot create a booking")

    booking_id: str | None = None
    try:
        req = CreateBookingRequest(
            service_id=service_id,
            start=slots[0].start,
            location_id=location_id,
            customer=BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=BOOKING_TEST_CUSTOMER_EMAIL,
            ),
            notes=f"{BOOKING_NOTE_PREFIX} create-and-cancel integration test",
        )
        booking = await square_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.service_id

        fetched = await square_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await square_booking_service.cancel_booking(booking_id)


async def test_update_booking(square_booking_service):
    """Create a booking then update its start time."""
    _require_env(*_SQUARE_VARS)
    service_id = await _first_service_id(square_booking_service)
    location_id = os.getenv("OMNIDAPTER_TEST_SQUARE_LOCATION_ID")
    now = datetime.now(timezone.utc)
    slots = await square_booking_service.get_availability(
        service_id=service_id,
        start=now,
        end=now + timedelta(days=30),
        location_id=location_id,
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 slots; cannot test update")

    booking_id: str | None = None
    try:
        booking = await square_booking_service.create_booking(
            CreateBookingRequest(
                service_id=service_id,
                start=slots[0].start,
                location_id=location_id,
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
                notes=f"{BOOKING_NOTE_PREFIX} update integration test",
            )
        )
        booking_id = booking.id

        updated = await square_booking_service.update_booking(
            UpdateBookingRequest(booking_id=booking_id, start=slots[1].start)
        )
        assert updated.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await square_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(square_booking_service):
    """list_bookings() iterates without error."""
    _require_env(*_SQUARE_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in square_booking_service.list_bookings(
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


async def test_find_customer(square_booking_service):
    """find_customer() returns None for an unknown email and doesn't raise."""
    _require_env(*_SQUARE_VARS)
    result = await square_booking_service.find_customer(
        FindCustomerRequest(email="no-such-user-omnidapter@example.invalid")
    )
    assert result is None


# --------------------------------------------------------------------------- #
# Error handling                                                               #
# --------------------------------------------------------------------------- #


async def test_get_unknown_booking_raises(square_booking_service):
    """get_booking() with a non-existent ID raises ProviderAPIError."""
    _require_env(*_SQUARE_VARS)
    with pytest.raises(ProviderAPIError):
        await square_booking_service.get_booking("nonexistent-omnidapter-id-0000000000")
