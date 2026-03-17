"""
Provider registry — registration, lookup, and plugin architecture.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from omnidapter.core.logging import registry_logger

if TYPE_CHECKING:
    from omnidapter.core.metadata import ProviderMetadata
    from omnidapter.providers._base import BaseProvider


_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


def _env_flag_enabled(var_name: str) -> bool:
    value = os.environ.get(var_name)
    return value is not None and value.strip().lower() in _TRUTHY_ENV_VALUES


class ProviderRegistry:
    """Central registry for provider implementations.

    Built-in providers auto-register by default.
    Custom providers can be registered explicitly.
    """

    def __init__(self) -> None:
        self._providers: dict[str, BaseProvider] = {}

    def register(self, provider: BaseProvider) -> None:
        """Register a provider implementation.

        Args:
            provider: A provider instance implementing BaseProvider.
        """
        key = provider.metadata.provider_key
        if key in self._providers:
            registry_logger.warning("Overwriting already-registered provider %r", key)
        self._providers[key] = provider
        registry_logger.info("Registered provider %r (%s)", key, provider.metadata.display_name)

    def get(self, provider_key: str) -> BaseProvider:
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

    def describe(self, provider_key: str) -> ProviderMetadata:
        """Return metadata for a registered provider."""
        return self.get(provider_key).metadata

    def register_builtins(self, *, auto_register_by_env: bool = True) -> None:
        """Register built-in providers that are available by default.

        When ``auto_register_by_env`` is True (default):
        - OAuth providers are auto-registered only when their environment-based
          credentials are present.
        - Apple is auto-registered only when ``OMNIDAPTER_ENABLE_APPLE`` is
          set to a truthy value (1/true/yes/on).

        When ``auto_register_by_env`` is False, all built-in providers are
        registered regardless of environment configuration.
        """
        from omnidapter.core.errors import ProviderNotConfiguredError
        from omnidapter.core.metadata import AuthKind
        from omnidapter.providers.apple.provider import AppleProvider
        from omnidapter.providers.google.provider import GoogleProvider
        from omnidapter.providers.microsoft.provider import MicrosoftProvider
        from omnidapter.providers.zoho.provider import ZohoProvider

        registered_count = 0
        oauth_registered_count = 0

        for provider_cls in [GoogleProvider, MicrosoftProvider, ZohoProvider, AppleProvider]:
            try:
                provider = provider_cls()
                provider_key = provider.metadata.provider_key
                is_oauth = AuthKind.OAUTH2 in provider.metadata.auth_kinds

                if auto_register_by_env:
                    if is_oauth:
                        try:
                            oauth_config = provider.get_oauth_config()
                        except ProviderNotConfiguredError as exc:
                            registry_logger.info(
                                "Skipping built-in provider %r: missing OAuth configuration (%s)",
                                provider_key,
                                ", ".join(exc.missing_fields),
                            )
                            continue

                        if oauth_config is None:
                            registry_logger.info(
                                "Skipping built-in provider %r: OAuth configuration unavailable",
                                provider_key,
                            )
                            continue

                        oauth_registered_count += 1

                    elif provider_key == "apple" and not _env_flag_enabled(
                        "OMNIDAPTER_ENABLE_APPLE"
                    ):
                        registry_logger.info(
                            "Skipping built-in provider %r: set OMNIDAPTER_ENABLE_APPLE=1 "
                            "to enable auto-registration",
                            provider_key,
                        )
                        continue
                elif is_oauth:
                    try:
                        provider.get_oauth_config()
                        oauth_registered_count += 1
                    except ProviderNotConfiguredError as exc:
                        registry_logger.info(
                            "Registering built-in provider %r without OAuth configuration (%s) "
                            "because auto_register_by_env is disabled",
                            provider_key,
                            ", ".join(exc.missing_fields),
                        )

                self.register(provider)
                registered_count += 1
            except Exception as exc:  # pragma: no cover
                registry_logger.error(
                    "Failed to register built-in provider %s: %s",
                    provider_cls.__name__,
                    exc,
                )

        if registered_count == 0:
            if auto_register_by_env:
                registry_logger.warning(
                    "No built-in providers were auto-registered. "
                    "Configure provider env vars and/or set OMNIDAPTER_ENABLE_APPLE=1."
                )
            else:
                registry_logger.warning(
                    "No built-in providers were registered due to initialization errors."
                )
        elif auto_register_by_env and oauth_registered_count == 0:
            registry_logger.warning(
                "No OAuth providers were auto-registered. "
                "Set provider env vars to enable Google, Microsoft, or Zoho by default."
            )
