"""
Provider contract tests for CalendarService implementations.

All built-in providers must pass this contract suite.
Contributor guide: implement your provider's calendar service, then run these
tests against it to verify compatibility.

Usage:
    from omnidapter.testing.contracts.calendar import CalendarProviderContract
    from omnidapter.testing.fakes.stores import InMemoryCredentialStore

    class TestMyProviderCalendar(CalendarProviderContract):
        @pytest.fixture
        def calendar_service(self) -> CalendarService:
            return MyProviderCalendarService(...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from omnidapter.services.calendar.interface import CalendarService

from omnidapter.services.calendar.capabilities import CalendarCapability


class CalendarProviderContract:
    """Base contract test class for CalendarService implementations.

    Subclass this and implement the `calendar_service` fixture.
    """

    @pytest.fixture
    def calendar_service(self) -> CalendarService:
        """Return the CalendarService under test."""
        raise NotImplementedError("Subclasses must implement the calendar_service fixture")

    def test_capabilities_is_frozenset(self, calendar_service):
        """Capabilities must be a frozenset."""
        caps = calendar_service.capabilities
        assert isinstance(caps, frozenset), "capabilities must return a frozenset"

    def test_capabilities_contains_only_valid_values(self, calendar_service):
        """All capability values must be valid CalendarCapability enum members."""
        caps = calendar_service.capabilities
        for cap in caps:
            assert isinstance(cap, CalendarCapability), (
                f"Capability {cap!r} is not a valid CalendarCapability"
            )

    def test_supports_method(self, calendar_service):
        """supports() must be consistent with capabilities."""
        caps = calendar_service.capabilities
        for cap in CalendarCapability:
            if cap in caps:
                assert calendar_service.supports(cap), (
                    f"supports({cap}) returned False but {cap} is in capabilities"
                )
            else:
                assert not calendar_service.supports(cap), (
                    f"supports({cap}) returned True but {cap} is not in capabilities"
                )

    def test_unsupported_capability_raises_typed_error(self, calendar_service):
        """_require_capability must raise UnsupportedCapabilityError for unsupported caps."""
        from omnidapter.core.errors import UnsupportedCapabilityError

        unsupported = [
            cap
            for cap in CalendarCapability
            if not calendar_service.supports(cap)
            and cap
            not in (
                CalendarCapability.BATCH_CREATE,
                CalendarCapability.BATCH_UPDATE,
                CalendarCapability.BATCH_DELETE,
            )
        ]
        if not unsupported:
            pytest.skip("Provider supports all standard capabilities")

        with pytest.raises(UnsupportedCapabilityError):
            calendar_service._require_capability(unsupported[0])

    def test_provider_key_is_string(self, calendar_service):
        """_provider_key must return a non-empty string."""
        key = calendar_service._provider_key
        assert isinstance(key, str) and len(key) > 0

    def test_batch_capabilities_not_in_supported_v1(self, calendar_service):
        """Batch capabilities are reserved and should not be claimed as supported in v1."""
        caps = calendar_service.capabilities
        batch_caps = {
            CalendarCapability.BATCH_CREATE,
            CalendarCapability.BATCH_UPDATE,
            CalendarCapability.BATCH_DELETE,
        }
        claimed_batch = caps & batch_caps
        assert not claimed_batch, (
            f"Provider should not claim batch capabilities in v1: {claimed_batch}"
        )
