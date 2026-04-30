"""
Provider contract tests for BookingService implementations.

All built-in providers must pass this contract suite.
Contributor guide: implement your provider's booking service, then run these
tests against it to verify compatibility.

Usage:
    from omnidapter.testing.contracts.booking import BookingProviderContract

    class TestMyProviderBooking(BookingProviderContract):
        @pytest.fixture
        def booking_service(self) -> BookingService:
            return MyProviderBookingService(...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from omnidapter.services.booking.interface import BookingService

from omnidapter.services.booking.capabilities import BookingCapability


class BookingProviderContract:
    """Base contract test class for BookingService implementations.

    Subclass this and implement the `booking_service` fixture.
    """

    @pytest.fixture
    def booking_service(self) -> BookingService:
        """Return the BookingService under test."""
        raise NotImplementedError("Subclasses must implement the booking_service fixture")

    def test_capabilities_is_frozenset(self, booking_service):
        """Capabilities must be a frozenset."""
        caps = booking_service.capabilities
        assert isinstance(caps, frozenset), "capabilities must return a frozenset"

    def test_capabilities_contains_only_valid_values(self, booking_service):
        """All capability values must be valid BookingCapability enum members."""
        caps = booking_service.capabilities
        for cap in caps:
            assert isinstance(cap, BookingCapability), (
                f"Capability {cap!r} is not a valid BookingCapability"
            )

    def test_supports_method(self, booking_service):
        """supports() must be consistent with capabilities."""
        caps = booking_service.capabilities
        for cap in BookingCapability:
            if cap in caps:
                assert booking_service.supports(cap), (
                    f"supports({cap}) returned False but {cap} is in capabilities"
                )
            else:
                assert not booking_service.supports(cap), (
                    f"supports({cap}) returned True but {cap} is not in capabilities"
                )

    def test_unsupported_capability_raises_typed_error(self, booking_service):
        """_require_capability must raise UnsupportedCapabilityError for unsupported caps."""
        from omnidapter.core.errors import UnsupportedCapabilityError

        unsupported = [cap for cap in BookingCapability if not booking_service.supports(cap)]
        if not unsupported:
            pytest.skip("Provider supports all standard capabilities")

        with pytest.raises(UnsupportedCapabilityError):
            booking_service._require_capability(unsupported[0])

    def test_provider_key_is_string(self, booking_service):
        """_provider_key must return a non-empty string."""
        key = booking_service._provider_key
        assert isinstance(key, str) and len(key) > 0

    def test_webhooks_not_in_capabilities(self, booking_service):
        """WEBHOOKS capability is not supported in v1 booking implementations."""
        caps = booking_service.capabilities
        assert BookingCapability.WEBHOOKS not in caps, (
            "WEBHOOKS capability should not be claimed in v1 booking implementations"
        )
