"""CRM request models."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from omnidapter.services.crm.models import (
    ActivityKind,
    ContactAddress,
    ContactEmail,
    ContactPhone,
    DealStage,
)


class ListContactsRequest(BaseModel):
    company_id: str | None = None
    tag: str | None = None
    search: str | None = None
    page_size: int | None = None


class CreateContactRequest(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    emails: list[ContactEmail] = []
    phones: list[ContactPhone] = []
    company_id: str | None = None
    company_name: str | None = None
    addresses: list[ContactAddress] = []
    tags: list[str] = []
    notes: str | None = None
    provider_data: dict | None = None


class UpdateContactRequest(BaseModel):
    contact_id: str
    first_name: str | None = None
    last_name: str | None = None
    emails: list[ContactEmail] | None = None
    phones: list[ContactPhone] | None = None
    company_id: str | None = None
    addresses: list[ContactAddress] | None = None
    tags: list[str] | None = None
    notes: str | None = None
    provider_data: dict | None = None


class ListCompaniesRequest(BaseModel):
    search: str | None = None
    tag: str | None = None
    page_size: int | None = None


class CreateCompanyRequest(BaseModel):
    name: str
    website: str | None = None
    industry: str | None = None
    phone: str | None = None
    email: str | None = None
    address: ContactAddress | None = None
    tags: list[str] = []
    provider_data: dict | None = None


class UpdateCompanyRequest(BaseModel):
    company_id: str
    name: str | None = None
    website: str | None = None
    industry: str | None = None
    phone: str | None = None
    email: str | None = None
    address: ContactAddress | None = None
    tags: list[str] | None = None
    provider_data: dict | None = None


class ListDealsRequest(BaseModel):
    contact_id: str | None = None
    company_id: str | None = None
    stage: DealStage | None = None
    owner_id: str | None = None
    page_size: int | None = None


class CreateDealRequest(BaseModel):
    name: str
    stage: DealStage | None = None
    stage_id: str | None = None  # provider-specific stage ID
    value: str | None = None
    currency: str | None = None
    contact_id: str | None = None
    company_id: str | None = None
    owner_id: str | None = None
    close_date: datetime | None = None
    notes: str | None = None
    provider_data: dict | None = None


class UpdateDealRequest(BaseModel):
    deal_id: str
    name: str | None = None
    stage: DealStage | None = None
    stage_id: str | None = None
    value: str | None = None
    close_date: datetime | None = None
    notes: str | None = None
    provider_data: dict | None = None


class ListActivitiesRequest(BaseModel):
    contact_id: str | None = None
    company_id: str | None = None
    deal_id: str | None = None
    kind: ActivityKind | None = None
    page_size: int | None = None


class CreateActivityRequest(BaseModel):
    kind: ActivityKind
    subject: str | None = None
    body: str | None = None
    contact_id: str | None = None
    company_id: str | None = None
    deal_id: str | None = None
    occurred_at: datetime | None = None
    provider_data: dict | None = None


class UpdateActivityRequest(BaseModel):
    activity_id: str
    subject: str | None = None
    body: str | None = None
    occurred_at: datetime | None = None
    provider_data: dict | None = None
