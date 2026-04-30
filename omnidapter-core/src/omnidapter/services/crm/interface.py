"""Abstract CRM service interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from omnidapter.services.crm.capabilities import CrmCapability
from omnidapter.services.crm.models import Activity, Company, Contact, Deal
from omnidapter.services.crm.requests import (
    CreateActivityRequest,
    CreateCompanyRequest,
    CreateContactRequest,
    CreateDealRequest,
    ListActivitiesRequest,
    ListCompaniesRequest,
    ListContactsRequest,
    ListDealsRequest,
    UpdateActivityRequest,
    UpdateCompanyRequest,
    UpdateContactRequest,
    UpdateDealRequest,
)


class CrmService(ABC):
    """Abstract CRM service interface."""

    @property
    @abstractmethod
    def capabilities(self) -> frozenset[CrmCapability]:
        """Return the set of capabilities supported by this provider."""
        ...

    def supports(self, capability: CrmCapability) -> bool:
        """Return True if this provider supports the given capability."""
        return capability in self.capabilities

    def _require_capability(self, capability: CrmCapability) -> None:
        """Raise UnsupportedCapabilityError if capability is not supported."""
        if not self.supports(capability):
            from omnidapter.core.errors import UnsupportedCapabilityError

            raise UnsupportedCapabilityError(
                f"Capability {capability.value!r} is not supported by this provider",
                provider_key=self._provider_key,
                capability=capability,
            )

    @property
    @abstractmethod
    def _provider_key(self) -> str:
        """Return the provider key for error context."""
        ...

    # ── Contacts ──────────────────────────────────────────────────────────────

    @abstractmethod
    def list_contacts(self, request: ListContactsRequest) -> AsyncIterator[Contact]:
        """Return an async iterator over contacts matching the given criteria."""
        ...

    @abstractmethod
    async def get_contact(self, contact_id: str) -> Contact:
        """Retrieve a contact by ID."""
        ...

    @abstractmethod
    async def create_contact(self, request: CreateContactRequest) -> Contact:
        """Create a new contact."""
        ...

    @abstractmethod
    async def update_contact(self, request: UpdateContactRequest) -> Contact:
        """Update an existing contact (partial update)."""
        ...

    @abstractmethod
    async def delete_contact(self, contact_id: str) -> None:
        """Delete a contact."""
        ...

    @abstractmethod
    async def search_contacts(self, query: str, limit: int = 50) -> list[Contact]:
        """Search contacts by name, email, or phone."""
        ...

    # ── Companies ─────────────────────────────────────────────────────────────

    @abstractmethod
    def list_companies(self, request: ListCompaniesRequest) -> AsyncIterator[Company]:
        """Return an async iterator over companies matching the given criteria."""
        ...

    @abstractmethod
    async def get_company(self, company_id: str) -> Company:
        """Retrieve a company by ID."""
        ...

    @abstractmethod
    async def create_company(self, request: CreateCompanyRequest) -> Company:
        """Create a new company."""
        ...

    @abstractmethod
    async def update_company(self, request: UpdateCompanyRequest) -> Company:
        """Update an existing company (partial update)."""
        ...

    @abstractmethod
    async def delete_company(self, company_id: str) -> None:
        """Delete a company."""
        ...

    # ── Deals ─────────────────────────────────────────────────────────────────

    @abstractmethod
    def list_deals(self, request: ListDealsRequest) -> AsyncIterator[Deal]:
        """Return an async iterator over deals matching the given criteria."""
        ...

    @abstractmethod
    async def get_deal(self, deal_id: str) -> Deal:
        """Retrieve a deal by ID."""
        ...

    @abstractmethod
    async def create_deal(self, request: CreateDealRequest) -> Deal:
        """Create a new deal."""
        ...

    @abstractmethod
    async def update_deal(self, request: UpdateDealRequest) -> Deal:
        """Update an existing deal (partial update)."""
        ...

    @abstractmethod
    async def delete_deal(self, deal_id: str) -> None:
        """Delete a deal."""
        ...

    # ── Activities ────────────────────────────────────────────────────────────

    @abstractmethod
    def list_activities(self, request: ListActivitiesRequest) -> AsyncIterator[Activity]:
        """Return an async iterator over activities matching the given criteria."""
        ...

    @abstractmethod
    async def create_activity(self, request: CreateActivityRequest) -> Activity:
        """Create a new activity (note, call, email, meeting, or task)."""
        ...

    @abstractmethod
    async def update_activity(self, request: UpdateActivityRequest) -> Activity:
        """Update an existing activity."""
        ...

    @abstractmethod
    async def delete_activity(self, activity_id: str) -> None:
        """Delete an activity."""
        ...
