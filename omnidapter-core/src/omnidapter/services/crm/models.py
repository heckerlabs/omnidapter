"""CRM domain models."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ContactAddress(BaseModel):
    street: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None


class ContactPhone(BaseModel):
    number: str
    label: str | None = None  # "mobile", "home", "work"


class ContactEmail(BaseModel):
    address: str
    label: str | None = None  # "personal", "work"


class Contact(BaseModel):
    id: str
    first_name: str | None = None
    last_name: str | None = None
    name: str | None = None  # display name (computed or explicit)
    emails: list[ContactEmail] = []
    phones: list[ContactPhone] = []
    company_id: str | None = None
    company_name: str | None = None
    addresses: list[ContactAddress] = []
    tags: list[str] = []
    notes: str | None = None
    provider_data: dict | None = None


class Company(BaseModel):
    id: str
    name: str
    website: str | None = None
    industry: str | None = None
    phone: str | None = None
    email: str | None = None
    address: ContactAddress | None = None
    tags: list[str] = []
    provider_data: dict | None = None


class DealStage(str, Enum):
    LEAD = "lead"
    QUALIFIED = "qualified"
    PROPOSAL = "proposal"
    NEGOTIATION = "negotiation"
    CLOSED_WON = "closed_won"
    CLOSED_LOST = "closed_lost"


class Deal(BaseModel):
    id: str
    name: str
    stage: DealStage | None = None
    stage_label: str | None = None  # provider-specific stage name when stage doesn't map cleanly
    value: str | None = None
    currency: str | None = None
    contact_id: str | None = None
    company_id: str | None = None
    owner_id: str | None = None
    close_date: datetime | None = None
    notes: str | None = None
    provider_data: dict | None = None


class ActivityKind(str, Enum):
    NOTE = "note"
    CALL = "call"
    EMAIL = "email"
    MEETING = "meeting"
    TASK = "task"


class Activity(BaseModel):
    id: str
    kind: ActivityKind
    subject: str | None = None
    body: str | None = None
    contact_id: str | None = None
    company_id: str | None = None
    deal_id: str | None = None
    occurred_at: datetime | None = None
    provider_data: dict | None = None
