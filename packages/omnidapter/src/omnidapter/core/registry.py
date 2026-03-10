"""
Provider registry — registration, lookup, and plugin architecture.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from omnidapter.core.logging import registry_logger

if TYPE_CHECKING:
    from omnidapter.core.metadata import ProviderMetadata
    from omnidapter.providers._base import BaseProvider


class ProviderRegistry:
    """Central registry for provider implementations.

    Built-in providers auto-register by default.
    Custom providers can be registered explicitly.
    """

    def __init__(self) -> None:
        self._providers: dict[str, "BaseProvider"] = {}

    def register(self, provider: "BaseProvider") -> None:
        """Register a provider implementation.

        Args:
            provider: A provider instance implementing BaseProvider.
        """
        key = provider.metadata.provider_key
        if key in self._providers:
            registry_logger.warning("Overwriting already-registered provider %r", key)
        self._providers[key] = provider
        registry_logger.info("Registered provider %r (%s)", key, provider.metadata.display_name)

    def get(self, provider_key: str) -> "BaseProvider":
        """Retrieve a registered provider by key.

        Raises:
            KeyError: If the provider is not registered.
        """
        if provider_key not in self._providers:
            raise KeyError(f"Provider {provider_key!r} is not registered")
        return self._providers[provider_key]

    def list_keys(self) -> list[str]:
        """Return all registered provider keys."""
        return list(self._providers.keys())

    def describe(self, provider_key: str) -> "ProviderMetadata":
        """Return metadata for a registered provider."""
        return self.get(provider_key).metadata

    def register_builtins(self) -> None:
        """Register all built-in providers."""
        from omnidapter.providers.google.provider import GoogleProvider
        from omnidapter.providers.microsoft.provider import MicrosoftProvider
        from omnidapter.providers.caldav.provider import CalDAVProvider
        from omnidapter.providers.zoho.provider import ZohoProvider

        for provider_cls in [GoogleProvider, MicrosoftProvider, CalDAVProvider, ZohoProvider]:
            try:
                self.register(provider_cls())
            except Exception as exc:  # pragma: no cover
                registry_logger.error(
                    "Failed to register built-in provider %s: %s",
                    provider_cls.__name__,
                    exc,
                )
