"""Pipedrive ↔ Omnidapter model mappers."""

from __future__ import annotations

import contextlib
from datetime import datetime

from omnidapter.services.crm.models import (
    Activity,
    ActivityKind,
    Company,
    Contact,
    ContactEmail,
    ContactPhone,
    Deal,
    DealStage,
)

_PD_STATUS_TO_STAGE: dict[str, DealStage] = {
    "won": DealStage.CLOSED_WON,
    "lost": DealStage.CLOSED_LOST,
}

_PD_ACTIVITY_KIND: dict[str, ActivityKind] = {
    "call": ActivityKind.CALL,
    "meeting": ActivityKind.MEETING,
    "task": ActivityKind.TASK,
    "deadline": ActivityKind.TASK,
    "email": ActivityKind.EMAIL,
    "lunch": ActivityKind.MEETING,
}

_STAGE_TO_PD_STATUS: dict[DealStage, str] = {
    DealStage.CLOSED_WON: "won",
    DealStage.CLOSED_LOST: "lost",
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError, TypeError):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    return None


def _extract_emails(raw: list[dict] | None) -> list[ContactEmail]:
    if not raw:
        return []
    return [ContactEmail(address=e["value"], label=e.get("label")) for e in raw if e.get("value")]


def _extract_phones(raw: list[dict] | None) -> list[ContactPhone]:
    if not raw:
        return []
    return [ContactPhone(number=p["value"], label=p.get("label")) for p in raw if p.get("value")]


def to_contact(data: dict) -> Contact:
    name = data.get("name") or None
    first_name, last_name = None, None
    if name and " " in name:
        parts = name.split(" ", 1)
        first_name, last_name = parts[0], parts[1]
    org = data.get("org_id") or {}
    return Contact(
        id=str(data.get("id", "")),
        first_name=first_name,
        last_name=last_name,
        name=name,
        emails=_extract_emails(data.get("email")),
        phones=_extract_phones(data.get("phone")),
        company_id=str(org["value"]) if isinstance(org, dict) and org.get("value") else None,
        company_name=org.get("name") if isinstance(org, dict) else None,
        tags=[label["name"] for label in (data.get("label_ids") or []) if isinstance(label, dict)],
        notes=data.get("notes_count") and None,
        provider_data=data,
    )


def to_company(data: dict) -> Company:
    return Company(
        id=str(data.get("id", "")),
        name=data.get("name") or "",
        website=data.get("web_site_or_url") or None,
        industry=data.get("industry") or None,
        phone=None,
        email=None,
        provider_data=data,
    )


def to_deal(data: dict) -> Deal:
    status = (data.get("status") or "open").lower()
    stage = _PD_STATUS_TO_STAGE.get(status, DealStage.LEAD)
    stage_label = data.get("stage_name") or None
    value = data.get("value")
    person = data.get("person_id") or {}
    org = data.get("org_id") or {}
    return Deal(
        id=str(data.get("id", "")),
        name=data.get("title") or "",
        stage=stage,
        stage_label=stage_label,
        value=str(value) if value is not None else None,
        currency=data.get("currency") or None,
        contact_id=str(person["value"])
        if isinstance(person, dict) and person.get("value")
        else None,
        company_id=str(org["value"]) if isinstance(org, dict) and org.get("value") else None,
        owner_id=str(data["user_id"]["id"]) if isinstance(data.get("user_id"), dict) else None,
        close_date=_parse_dt(
            data.get("won_time") or data.get("lost_time") or data.get("expected_close_date")
        ),
        notes=data.get("notes_count") and None,
        provider_data=data,
    )


def to_note_activity(data: dict) -> Activity:
    return Activity(
        id=str(data.get("id", "")),
        kind=ActivityKind.NOTE,
        subject=None,
        body=data.get("content") or None,
        contact_id=str(data["person_id"]) if data.get("person_id") else None,
        company_id=str(data["org_id"]) if data.get("org_id") else None,
        deal_id=str(data["deal_id"]) if data.get("deal_id") else None,
        occurred_at=_parse_dt(data.get("add_time")),
        provider_data=data,
    )


def to_activity(data: dict) -> Activity:
    kind = _PD_ACTIVITY_KIND.get((data.get("type") or "task").lower(), ActivityKind.TASK)
    due_dt = None
    if data.get("due_date") and data.get("due_time"):
        with contextlib.suppress(ValueError, TypeError):
            due_dt = datetime.fromisoformat(f"{data['due_date']}T{data['due_time']}")
    return Activity(
        id=str(data.get("id", "")),
        kind=kind,
        subject=data.get("subject") or None,
        body=data.get("note") or None,
        contact_id=str(data["person_id"]) if data.get("person_id") else None,
        company_id=str(data["org_id"]) if data.get("org_id") else None,
        deal_id=str(data["deal_id"]) if data.get("deal_id") else None,
        occurred_at=due_dt or _parse_dt(data.get("add_time")),
        provider_data=data,
    )
