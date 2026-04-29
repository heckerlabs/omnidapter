"""
Integration tests for Jobber BookingService (GraphQL).

Required env vars:
    OMNIDAPTER_TEST_JOBBER_CLIENT_ID
    OMNIDAPTER_TEST_JOBBER_CLIENT_SECRET
    OMNIDAPTER_TEST_JOBBER_REFRESH_TOKEN

Optional:
    OMNIDAPTER_TEST_JOBBER_SERVICE_ID   (Jobber product/service ID for line items)

Jobber maps Jobs + Visits to the Booking model. Creating a booking via
create_booking() creates a Job with one Visit. Cancelling sets the job
status to archived.

Availability is computed by subtracting existing Visits from 9 AM–5 PM
working hours (configurable via provider_config). The integration test
uses a 14-day window to find free slots.

Capabilities tested: GET_AVAILABILITY, CREATE_BOOKING, CANCEL_BOOKING,
RESCHEDULE_BOOKING, LIST_BOOKINGS, CUSTOMER_LOOKUP, CUSTOMER_MANAGEMENT.
LIST_SERVICES is supported (returns a synthetic entry from provider_config).
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

_JOBBER_VARS = (
    "OMNIDAPTER_TEST_JOBBER_CLIENT_ID",
    "OMNIDAPTER_TEST_JOBBER_CLIENT_SECRET",
    "OMNIDAPTER_TEST_JOBBER_REFRESH_TOKEN",
)


# --------------------------------------------------------------------------- #
# Availability (computed via schedule subtraction)                             #
# --------------------------------------------------------------------------- #


async def test_get_availability(jobber_booking_service):
    """get_availability() returns free slots derived from working hours."""
    _require_env(*_JOBBER_VARS)
    now = datetime.now(timezone.utc)
    slots = await jobber_booking_service.get_availability(
        service_id=os.getenv("OMNIDAPTER_TEST_JOBBER_SERVICE_ID", "default"),
        start=now,
        end=now + timedelta(days=14),
    )
    assert isinstance(slots, list)
    for slot in slots:
        assert slot.start < slot.end


# --------------------------------------------------------------------------- #
# Customer lookup                                                              #
# --------------------------------------------------------------------------- #


async def test_find_customer_unknown(jobber_booking_service):
    """find_customer() returns None for an email that isn't in Jobber."""
    _require_env(*_JOBBER_VARS)
    result = await jobber_booking_service.find_customer(
        FindCustomerRequest(email="no-such-user-omnidapter@example.invalid")
    )
    assert result is None


async def test_find_customer_round_trip(jobber_booking_service):
    """create_customer() then find_customer() returns the same record."""
    _require_env(*_JOBBER_VARS)
    test_email = "omnidapter-integration-test@example.invalid"
    customer_id: str | None = None

    try:
        created = await jobber_booking_service.create_customer(
            BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=test_email,
            )
        )
        customer_id = created.id
        assert created.id
        assert created.email == test_email or created.name == BOOKING_TEST_CUSTOMER_NAME

        found = await jobber_booking_service.find_customer(FindCustomerRequest(email=test_email))
        assert found is not None
        assert found.id == customer_id

    except ProviderAPIError as exc:
        # Duplicate email is a common Jobber constraint; skip gracefully
        if "duplicate" in str(exc).lower() or exc.status_code in (409, 422):
            pytest.skip(f"Test customer already exists: {exc}")
        raise


# --------------------------------------------------------------------------- #
# Booking CRUD                                                                 #
# --------------------------------------------------------------------------- #


async def test_create_and_cancel_booking(jobber_booking_service):
    """Create a job (booking) then cancel (archive) it."""
    _require_env(*_JOBBER_VARS)
    now = datetime.now(timezone.utc)
    slots = await jobber_booking_service.get_availability(
        service_id=os.getenv("OMNIDAPTER_TEST_JOBBER_SERVICE_ID", "default"),
        start=now,
        end=now + timedelta(days=14),
    )
    if not slots:
        pytest.skip("No computed free slots; cannot create a booking")

    booking_id: str | None = None
    try:
        req = CreateBookingRequest(
            service_id=os.getenv("OMNIDAPTER_TEST_JOBBER_SERVICE_ID", "default"),
            start=slots[0].start,
            customer=BookingCustomer(
                name=BOOKING_TEST_CUSTOMER_NAME,
                email=BOOKING_TEST_CUSTOMER_EMAIL,
            ),
            notes=f"{BOOKING_NOTE_PREFIX} create-and-cancel integration test",
        )
        booking = await jobber_booking_service.create_booking(req)
        booking_id = booking.id

        assert booking.id
        assert booking.customer.name == BOOKING_TEST_CUSTOMER_NAME

        fetched = await jobber_booking_service.get_booking(booking_id)
        assert fetched.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await jobber_booking_service.cancel_booking(booking_id)


async def test_reschedule_booking(jobber_booking_service):
    """Create a booking then reschedule its visit start time."""
    _require_env(*_JOBBER_VARS)
    now = datetime.now(timezone.utc)
    slots = await jobber_booking_service.get_availability(
        service_id=os.getenv("OMNIDAPTER_TEST_JOBBER_SERVICE_ID", "default"),
        start=now,
        end=now + timedelta(days=14),
    )
    if len(slots) < 2:
        pytest.skip("Fewer than 2 free slots; cannot test reschedule")

    booking_id: str | None = None
    try:
        booking = await jobber_booking_service.create_booking(
            CreateBookingRequest(
                service_id=os.getenv("OMNIDAPTER_TEST_JOBBER_SERVICE_ID", "default"),
                start=slots[0].start,
                customer=BookingCustomer(
                    name=BOOKING_TEST_CUSTOMER_NAME,
                    email=BOOKING_TEST_CUSTOMER_EMAIL,
                ),
                notes=f"{BOOKING_NOTE_PREFIX} reschedule integration test",
            )
        )
        booking_id = booking.id

        rescheduled = await jobber_booking_service.reschedule_booking(
            RescheduleBookingRequest(booking_id=booking_id, new_start=slots[1].start)
        )
        assert rescheduled.id == booking_id

    finally:
        if booking_id:
            with suppress(Exception):
                await jobber_booking_service.cancel_booking(booking_id)


# --------------------------------------------------------------------------- #
# Listing                                                                      #
# --------------------------------------------------------------------------- #


async def test_list_bookings(jobber_booking_service):
    """list_bookings() cursor-paginates over jobs without error."""
    _require_env(*_JOBBER_VARS)
    now = datetime.now(timezone.utc)
    items = []
    async for booking in jobber_booking_service.list_bookings(
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
