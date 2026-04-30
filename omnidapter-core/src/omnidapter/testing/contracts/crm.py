"""
Provider contract tests for CrmService implementations.

All built-in providers must pass this contract suite.
Contributor guide: implement your provider's CRM service, then run these
tests against it to verify compatibility.

Usage:
    from omnidapter.testing.contracts.crm import CrmProviderContract

    class TestMyProviderCrm(CrmProviderContract):
        @pytest.fixture
        def crm_service(self) -> CrmService:
            return MyProviderCrmService(...)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from omnidapter.services.crm.interface import CrmService

from omnidapter.services.crm.capabilities import CrmCapability


class CrmProviderContract:
    """Base contract test class for CrmService implementations.

    Subclass this and implement the `crm_service` fixture.
    """

    @pytest.fixture
    def crm_service(self) -> CrmService:
        """Return the CrmService under test."""
        raise NotImplementedError("Subclasses must implement the crm_service fixture")

    def test_capabilities_is_frozenset(self, crm_service):
        """Capabilities must be a frozenset."""
        caps = crm_service.capabilities
        assert isinstance(caps, frozenset), "capabilities must return a frozenset"

    def test_capabilities_contains_only_valid_values(self, crm_service):
        """All capability values must be valid CrmCapability enum members."""
        caps = crm_service.capabilities
        for cap in caps:
            assert isinstance(cap, CrmCapability), (
                f"Capability {cap!r} is not a valid CrmCapability"
            )

    def test_supports_method(self, crm_service):
        """supports() must be consistent with capabilities."""
        caps = crm_service.capabilities
        for cap in CrmCapability:
            if cap in caps:
                assert crm_service.supports(cap), (
                    f"supports({cap}) returned False but {cap} is in capabilities"
                )
            else:
                assert not crm_service.supports(cap), (
                    f"supports({cap}) returned True but {cap} is not in capabilities"
                )

    def test_unsupported_capability_raises(self, crm_service):
        """_require_capability() must raise UnsupportedCapabilityError for unsupported caps."""
        from omnidapter.core.errors import UnsupportedCapabilityError

        for cap in CrmCapability:
            if not crm_service.supports(cap):
                with pytest.raises(UnsupportedCapabilityError):
                    crm_service._require_capability(cap)
                return  # one unsupported cap is enough to confirm the guard works

    def test_provider_key_is_non_empty(self, crm_service):
        """_provider_key must be a non-empty string."""
        key = crm_service._provider_key
        assert isinstance(key, str) and key, "_provider_key must be a non-empty string"

    def test_webhooks_not_in_capabilities(self, crm_service):
        """WEBHOOKS must not be claimed — reserved for a future release."""
        assert CrmCapability.WEBHOOKS not in crm_service.capabilities, (
            "WEBHOOKS capability must not be claimed in v1"
        )
