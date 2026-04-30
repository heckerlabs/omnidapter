"""HubSpot ↔ Omnidapter model mappers."""

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

_HS_STAGE_MAP: dict[str, DealStage] = {
    "appointmentscheduled": DealStage.LEAD,
    "qualifiedtobuy": DealStage.QUALIFIED,
    "presentationscheduled": DealStage.PROPOSAL,
    "decisionmakerboughtin": DealStage.NEGOTIATION,
    "contractsent": DealStage.NEGOTIATION,
    "closedwon": DealStage.CLOSED_WON,
    "closedlost": DealStage.CLOSED_LOST,
}

_DEAL_STAGE_TO_HS: dict[DealStage, str] = {
    DealStage.LEAD: "appointmentscheduled",
    DealStage.QUALIFIED: "qualifiedtobuy",
    DealStage.PROPOSAL: "presentationscheduled",
    DealStage.NEGOTIATION: "contractsent",
    DealStage.CLOSED_WON: "closedwon",
    DealStage.CLOSED_LOST: "closedlost",
}

_HS_ACTIVITY_KIND_MAP: dict[str, ActivityKind] = {
    "calls": ActivityKind.CALL,
    "emails": ActivityKind.EMAIL,
    "meetings": ActivityKind.MEETING,
    "tasks": ActivityKind.TASK,
    "notes": ActivityKind.NOTE,
}


def _parse_dt(value: str | int | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError, TypeError):
        if isinstance(value, int):
            return datetime.fromtimestamp(value / 1000)
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    return None


def _map_stage(hs_stage: str) -> tuple[DealStage | None, str | None]:
    mapped = _HS_STAGE_MAP.get(hs_stage.lower())
    label = hs_stage if mapped is None else None
    return mapped, label


def stage_to_hs_id(stage: DealStage) -> str:
    return _DEAL_STAGE_TO_HS.get(stage, "appointmentscheduled")


def to_contact(data: dict) -> Contact:
    props = data.get("properties") or data
    emails = []
    if props.get("email"):
        emails = [ContactEmail(address=props["email"])]
    phones = []
    if props.get("phone"):
        phones.append(ContactPhone(number=props["phone"], label="work"))
    if props.get("mobilephone"):
        phones.append(ContactPhone(number=props["mobilephone"], label="mobile"))
    name = props.get("name") or (
        f"{props.get('firstname', '')} {props.get('lastname', '')}".strip() or None
    )
    return Contact(
        id=str(data.get("id", "")),
        first_name=props.get("firstname") or None,
        last_name=props.get("lastname") or None,
        name=name,
        emails=emails,
        phones=phones,
        company_id=str(props["associatedcompanyid"]) if props.get("associatedcompanyid") else None,
        company_name=props.get("company") or None,
        tags=[t.strip() for t in (props.get("hs_tags") or "").split(";") if t.strip()],
        notes=props.get("hs_content_membership_notes") or None,
        provider_data=data,
    )


def to_company(data: dict) -> Company:
    props = data.get("properties") or data
    return Company(
        id=str(data.get("id", "")),
        name=props.get("name") or "",
        website=props.get("website") or None,
        industry=props.get("industry") or None,
        phone=props.get("phone") or None,
        email=props.get("email") or None,
        provider_data=data,
    )


def to_deal(data: dict) -> Deal:
    props = data.get("properties") or data
    stage_raw = props.get("dealstage") or ""
    stage, stage_label = _map_stage(stage_raw)
    amount = props.get("amount")
    return Deal(
        id=str(data.get("id", "")),
        name=props.get("dealname") or "",
        stage=stage,
        stage_label=stage_label or (stage_raw if stage is not None else None),
        value=str(amount) if amount is not None else None,
        currency=None,
        contact_id=None,
        company_id=None,
        owner_id=props.get("hubspot_owner_id") or None,
        close_date=_parse_dt(props.get("closedate")),
        notes=props.get("description") or None,
        provider_data=data,
    )


def to_activity(data: dict, object_type: str = "notes") -> Activity:
    props = data.get("properties") or data
    kind = _HS_ACTIVITY_KIND_MAP.get(object_type, ActivityKind.NOTE)
    occurred = _parse_dt(props.get("hs_timestamp") or props.get("createdate"))
    return Activity(
        id=str(data.get("id", "")),
        kind=kind,
        subject=props.get("hs_call_title") or props.get("subject") or None,
        body=props.get("hs_note_body")
        or props.get("hs_call_body")
        or props.get("hs_email_text")
        or None,
        contact_id=None,
        company_id=None,
        deal_id=None,
        occurred_at=occurred,
        provider_data=data,
    )
