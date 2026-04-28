"""
Booking capability enumeration.
"""

from __future__ import annotations

from enum import Enum


class BookingCapability(str, Enum):
    """Capabilities that a booking provider may or may not support."""

    LIST_SERVICES = "list_services"
    LIST_STAFF = "list_staff"
    LIST_LOCATIONS = "list_locations"
    GET_AVAILABILITY = "get_availability"
    CREATE_BOOKING = "create_booking"
    CANCEL_BOOKING = "cancel_booking"
    RESCHEDULE_BOOKING = "reschedule_booking"
    UPDATE_BOOKING = "update_booking"
    LIST_BOOKINGS = "list_bookings"
    CUSTOMER_LOOKUP = "customer_lookup"
    CUSTOMER_MANAGEMENT = "customer_management"
    MULTI_LOCATION = "multi_location"
    MULTI_STAFF = "multi_staff"
    MULTI_SERVICE = "multi_service"
    WEBHOOKS = "webhooks"  # reserved — not supported in v1
