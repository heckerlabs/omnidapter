"""Square Appointments ↔ Omnidapter model mappers."""

from __future__ import annotations

from datetime import datetime, timedelta

from omnidapter.services.booking.models import (
    AvailabilitySlot,
    Booking,
    BookingCustomer,
    BookingLocation,
    BookingStatus,
    ServiceType,
    StaffMember,
)


def parse_dt(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return datetime.fromisoformat(value)


def _status(raw: str) -> BookingStatus:
    s = raw.upper()
    if s in ("CANCELLED", "CANCELED_BY_CUSTOMER", "CANCELED_BY_SELLER", "NO_SHOW"):
        return BookingStatus.CANCELLED
    if s == "PENDING":
        return BookingStatus.PENDING
    return BookingStatus.CONFIRMED


def to_service_type(item_data: dict, variation: dict) -> ServiceType:
    """Map a Square CatalogItemVariation to a ServiceType."""
    vd = variation.get("item_variation_data", {})
    duration_ms = vd.get("service_duration")
    duration_minutes = int(duration_ms / 60000) if duration_ms else None
    price_money = vd.get("price_money", {})
    price_amount = price_money.get("amount")
    price_currency = price_money.get("currency", "USD")
    price = f"{price_amount / 100:.2f} {price_currency}" if price_amount is not None else None
    return ServiceType(
        id=str(variation["id"]),
        name=f"{item_data.get('name', '')} – {vd.get('name', '')}".strip(" –"),
        description=item_data.get("description") or None,
        duration_minutes=duration_minutes,
        price=price,
        provider_data={
            "item_id": item_data.get("id"),
            "variation_id": variation["id"],
            "service_variation_version": variation.get("version"),
        },
    )


def to_staff_member(data: dict) -> StaffMember:
    tm = data.get("team_member") or {}
    return StaffMember(
        id=str(data.get("team_member_id") or tm.get("id", "")),
        name=f"{tm.get('given_name', '')} {tm.get('family_name', '')}".strip()
        or tm.get("display_name", ""),
        email=tm.get("email_address") or None,
        service_ids=[],
        provider_data=data,
    )


def to_location(data: dict) -> BookingLocation:
    address = data.get("address", {})
    addr_str = (
        ", ".join(
            filter(
                None,
                [
                    address.get("address_line_1"),
                    address.get("locality"),
                    address.get("administrative_district_level_1"),
                    address.get("postal_code"),
                ],
            )
        )
        or None
    )
    return BookingLocation(
        id=str(data["id"]),
        name=data.get("name", ""),
        address=addr_str,
        provider_data=data,
    )


def to_booking(data: dict) -> Booking:
    segments = data.get("appointment_segments") or []
    service_id = segments[0].get("service_variation_id", "") if segments else ""
    staff_id = segments[0].get("team_member_id") if segments else None

    customer_note = data.get("customer_note") or None
    start_str = data.get("start_at", "")
    start = parse_dt(start_str) if start_str else datetime.now()
    duration_minutes = sum(s.get("duration_minutes", 0) for s in segments) or 30
    end = start + timedelta(minutes=duration_minutes)

    return Booking(
        id=str(data["id"]),
        service_id=str(service_id),
        start=start,
        end=end,
        status=_status(data.get("status", "ACCEPTED")),
        customer=BookingCustomer(
            id=data.get("customer_id"),
        ),
        staff_id=str(staff_id) if staff_id else None,
        location_id=data.get("location_id"),
        notes=customer_note,
        provider_data=data,
    )


def to_booking_customer(data: dict) -> BookingCustomer:
    given = data.get("given_name") or ""
    family = data.get("family_name") or ""
    name = f"{given} {family}".strip() or data.get("company_name") or None
    return BookingCustomer(
        id=str(data["id"]),
        name=name,
        email=data.get("email_address") or None,
        phone=data.get("phone_number") or None,
        provider_data=data,
    )


def to_availability_slot(avail: dict, service_id: str) -> AvailabilitySlot:
    start_str = avail.get("start_at", "")
    start = parse_dt(start_str) if start_str else datetime.now()
    segments = avail.get("appointment_segments") or []
    duration = sum(s.get("duration_minutes", 0) for s in segments) or 30
    staff_id = segments[0].get("team_member_id") if segments else None
    return AvailabilitySlot(
        start=start,
        end=start + timedelta(minutes=duration),
        service_id=service_id,
        staff_id=str(staff_id) if staff_id else None,
        location_id=avail.get("location_id"),
    )
