"""Salesforce ↔ Omnidapter model mappers."""

from __future__ import annotations

import contextlib
from datetime import date, datetime

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

_SF_STAGE_MAP: dict[str, DealStage] = {
    "prospecting": DealStage.LEAD,
    "qualification": DealStage.QUALIFIED,
    "proposal/price quote": DealStage.PROPOSAL,
    "negotiation": DealStage.NEGOTIATION,
    "closed won": DealStage.CLOSED_WON,
    "closed lost": DealStage.CLOSED_LOST,
    "value proposition": DealStage.QUALIFIED,
    "id. decision makers": DealStage.QUALIFIED,
    "perception analysis": DealStage.PROPOSAL,
    "needs analysis": DealStage.QUALIFIED,
}

_SF_STAGE_TO_LABEL: dict[DealStage, str] = {
    DealStage.LEAD: "Prospecting",
    DealStage.QUALIFIED: "Qualification",
    DealStage.PROPOSAL: "Proposal/Price Quote",
    DealStage.NEGOTIATION: "Negotiation",
    DealStage.CLOSED_WON: "Closed Won",
    DealStage.CLOSED_LOST: "Closed Lost",
}

_SF_ACTIVITY_KIND_MAP: dict[str, ActivityKind] = {
    "Call": ActivityKind.CALL,
    "Email": ActivityKind.EMAIL,
    "Meeting": ActivityKind.MEETING,
}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError, TypeError):
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    return None


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    with contextlib.suppress(ValueError, TypeError):
        d = date.fromisoformat(value)
        return datetime(d.year, d.month, d.day)
    return None


def _map_stage(sf_stage: str) -> tuple[DealStage | None, str | None]:
    mapped = _SF_STAGE_MAP.get(sf_stage.lower())
    label = sf_stage if mapped is None else None
    return mapped, label


def stage_to_sf_label(stage: DealStage) -> str:
    return _SF_STAGE_TO_LABEL.get(stage, stage.value.replace("_", " ").title())


def to_contact(data: dict) -> Contact:
    emails = []
    if data.get("Email"):
        emails = [ContactEmail(address=data["Email"])]
    phones = []
    if data.get("Phone"):
        phones.append(ContactPhone(number=data["Phone"], label="work"))
    if data.get("MobilePhone"):
        phones.append(ContactPhone(number=data["MobilePhone"], label="mobile"))
    name = data.get("Name") or (
        f"{data.get('FirstName', '')} {data.get('LastName', '')}".strip() or None
    )
    return Contact(
        id=str(data.get("Id", "")),
        first_name=data.get("FirstName") or None,
        last_name=data.get("LastName") or None,
        name=name,
        emails=emails,
        phones=phones,
        company_id=data.get("AccountId") or None,
        company_name=data.get("Account", {}).get("Name")
        if isinstance(data.get("Account"), dict)
        else None,
        tags=data.get("Tags__c", "").split(";") if data.get("Tags__c") else [],
        notes=data.get("Description") or None,
        provider_data=data,
    )


def to_company(data: dict) -> Company:
    phones = []
    if data.get("Phone"):
        phones.append(data["Phone"])
    return Company(
        id=str(data.get("Id", "")),
        name=data.get("Name") or "",
        website=data.get("Website") or None,
        industry=data.get("Industry") or None,
        phone=data.get("Phone") or None,
        email=data.get("Email__c") or None,
        provider_data=data,
    )


def to_deal(data: dict) -> Deal:
    stage_raw = data.get("StageName") or ""
    stage, stage_label = _map_stage(stage_raw)
    return Deal(
        id=str(data.get("Id", "")),
        name=data.get("Name") or "",
        stage=stage,
        stage_label=stage_label or (stage_raw if stage is not None else None),
        value=str(data["Amount"]) if data.get("Amount") is not None else None,
        currency=data.get("CurrencyIsoCode") or None,
        contact_id=data.get("ContactId") or None,
        company_id=data.get("AccountId") or None,
        owner_id=data.get("OwnerId") or None,
        close_date=_parse_date(data.get("CloseDate")),
        notes=data.get("Description") or None,
        provider_data=data,
    )


def to_activity(data: dict, kind: ActivityKind = ActivityKind.NOTE) -> Activity:
    if data.get("ActivityType"):
        kind = _SF_ACTIVITY_KIND_MAP.get(data["ActivityType"], ActivityKind.TASK)
    elif data.get("Subject", "").lower().startswith("call"):
        kind = ActivityKind.CALL
    occurred = _parse_dt(data.get("CreatedDate")) or _parse_dt(data.get("ActivityDateTime"))
    return Activity(
        id=str(data.get("Id", "")),
        kind=kind,
        subject=data.get("Subject") or None,
        body=data.get("Description") or data.get("Body") or None,
        contact_id=data.get("WhoId") or None,
        company_id=data.get("AccountId") or None,
        deal_id=data.get("WhatId") or None,
        occurred_at=occurred,
        provider_data=data,
    )
