"""
Integration tests for Housecall Pro BookingService (API key auth).

Required env vars:
    OMNIDAPTER_TEST_HOUSECALLPRO_API_KEY

Optional:
    OMNIDAPTER_TEST_HOUSECALLPRO_SERVICE_ID   (HCP product/service ID)

Housecall Pro uses API key authentication (no OAuth). Unlike the other
booking providers, HCP requires an existing customer with an address before
a job (booking) can be created. The _resolve_customer() path handles
find-or-create automatically, and create_booking() resolves the address too.

Availability is computed via schedule subtraction (9 AM–5 PM by default).
Jobs map to Booking objects; Visits map to the appointment slot.

Capabilities: GET_AVAILABILITY, CREATE_BOOKING, CANCEL_BOOKING,
RESCHEDULE_BOOKING, LIST_BOOKINGS, CUSTOMER_LOOKUP, CUSTOMER_MANAGEMENT.
LIST_LOCATIONS is not supported.
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

_HCP_VARS = ("OMNIDAPTER_TEST_HOUSECALLPRO_API_KEY",)


# --------------------------------------------------------------------------- #
# Availability (schedule subtraction)                                          #
# --------------------------------------------------------------------------- #


async def test_get_availability(housecallpro_booking_service):
    """get_availability() returns computed free slots."""
    _require_env(*_HCP_VARS)
    now = datetime.now(timezone.utc)
    slots = await housecallpro_booking_service.get_availability(
        service_id=os.getenv("OMNIDAPTER_TEST_HOUSECALLPRO_SERVICE_ID", "default"),
        start=now,
        end=now + timedelta(days=14),
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Customer resolution                                                          #
# --------------------------------------------------------------------------- #


async def test_find_customer_unknown(housecallpro_booking_service):
    """find_customer() returns None for an email not in HCP."""
    _require_env(*_HCP_VARS)
    result = await housecallpro_booking_service.find_customer(
        FindCustomerRequest(email="no-such-user-omnidapter@example.invalid")
    )
    assert result is None


async def test_create_and_find_customer(housecallpro_booking_service):
    """create_customer() then find_customer() round-trip."""
    _require_env(*_HCP_VARS)
    test_email = "omnidapter-hcp-integration@example.invalid"

    # Don't fail if it already exists from a previous test run
    existing = await housecallpro_booking_service.find_customer(
        FindCustomerRequest(email=test_email)
    )
    if existing:
        assert existing.email == test_email
        return

    try:
        created = await housecallpro_booking_service.create_customer(
            BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=test_email,
            )
        )
        assert created.id
        assert created.email == test_email or created.name == BOOKING_TEST_CUSTOMER_NAME

        found = await housecallpro_booking_service.find_customer(
            FindCustomerRequest(email=test_email)
        )
        assert found is not None
        assert found.id == created.id

    except ProviderAPIError as exc:
        if exc.status_code in (409, 422):
            pytest.skip(f"Customer already exists: {exc}")
        raise


# --------------------------------------------------------------------------- #
# Booking CRUD                                                                 #
# --------------------------------------------------------------------------- #


async def test_create_and_cancel_booking(housecallpro_booking_service):
    """Create a job (booking) then cancel it. _resolve_customer handles address."""
    _require_env(*_HCP_VARS)
    now = datetime.now(timezone.utc)
    slots = await housecallpro_booking_service.get_availability(
        service_id=os.getenv("OMNIDAPTER_TEST_HOUSECALLPRO_SERVICE_ID", "default"),
        start=now,
        end=now + timedelta(days=14),
    )
    if not slots:
        pytest.skip("No computed free slots; cannot create a booking")

    booking_id: str | None = None
    try:
        req = CreateBookingRequest(
            service_id=os.getenv("OMNIDAPTER_TEST_HOUSECALLPRO_SERVICE_ID", "default"),
            start=slots[0].start,
            customer=BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=BOOKING_TEST_CUSTOMER_EMAIL,
            ),
            notes=f"{BOOKING_NOTE_PREFIX} create-and-cancel integration test",
        )
        booking = await housecallpro_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.customer.name == BOOKING_TEST_CUSTOMER_NAME

        fetched = await housecallpro_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await housecallpro_booking_service.cancel_booking(booking_id)


async def test_reschedule_booking(housecallpro_booking_service):
    """Create a booking then reschedule it."""
    _require_env(*_HCP_VARS)
    now = datetime.now(timezone.utc)
    slots = await housecallpro_booking_service.get_availability(
        service_id=os.getenv("OMNIDAPTER_TEST_HOUSECALLPRO_SERVICE_ID", "default"),
        start=now,
        end=now + timedelta(days=14),
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 free slots; cannot test reschedule")

    booking_id: str | None = None
    try:
        booking = await housecallpro_booking_service.create_booking(
            CreateBookingRequest(
                service_id=os.getenv("OMNIDAPTER_TEST_HOUSECALLPRO_SERVICE_ID", "default"),
                start=slots[0].start,
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
                notes=f"{BOOKING_NOTE_PREFIX} reschedule integration test",
            )
        )
        booking_id = booking.id

        rescheduled = await housecallpro_booking_service.reschedule_booking(
            RescheduleBookingRequest(booking_id=booking_id, new_start=slots[1].start)
        )
        assert rescheduled.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await housecallpro_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(housecallpro_booking_service):
    """list_bookings() paginates over jobs without error."""
    _require_env(*_HCP_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in housecallpro_booking_service.list_bookings(
        ListBookingsRequest(
            start=now - timedelta(days=30), end=now + timedelta(days=30), page_size=5
        )
    ):
        items.append(booking)
        if len(items) >= 20:
            break

    for b in items:
        assert b.id
        assert b.status in BookingStatus
