"""Provider registry helpers for server request handling."""

from __future__ import annotations

from typing import TYPE_CHECKING

from omnidapter.core.registry import ProviderRegistry
from omnidapter.providers.apple.provider import AppleProvider
from omnidapter.providers.caldav.provider import CalDAVProvider
from omnidapter.providers.google.provider import GoogleProvider
from omnidapter.providers.microsoft.provider import MicrosoftProvider
from omnidapter.providers.zoho.provider import ZohoProvider

if TYPE_CHECKING:
    from omnidapter_server.config import Settings


_OAUTH_PROVIDER_FACTORIES = {
    "google": GoogleProvider,
    "microsoft": MicrosoftProvider,
    "zoho": ZohoProvider,
}


def _register_oauth_provider(
    registry: ProviderRegistry,
    provider_key: str,
    client_id: str,
    client_secret: str,
) -> None:
    provider_factory = _OAUTH_PROVIDER_FACTORIES.get(provider_key)
    if provider_factory is None:
        return
    registry.register(provider_factory(client_id=client_id, client_secret=client_secret))


def build_provider_registry(settings: Settings) -> ProviderRegistry:
    """Build a provider registry for a request-scoped Omnidapter instance.

    Registers:
    1) Non-OAuth built-ins (Apple, CalDAV) if enabled in settings.
    2) OAuth providers from server fallback credentials (`OMNIDAPTER_*`).
    """

    registry = ProviderRegistry()

    # Register non-OAuth built-ins if enabled in settings
    if settings.omnidapter_apple_enabled:
        registry.register(AppleProvider())
    if settings.omnidapter_caldav_enabled:
        registry.register(CalDAVProvider())

    fallback_pairs = (
        ("google", settings.omnidapter_google_client_id, settings.omnidapter_google_client_secret),
        (
            "microsoft",
            settings.omnidapter_microsoft_client_id,
            settings.omnidapter_microsoft_client_secret,
        ),
        ("zoho", settings.omnidapter_zoho_client_id, settings.omnidapter_zoho_client_secret),
    )
    for provider_key, client_id, client_secret in fallback_pairs:
        if client_id and client_secret:
            _register_oauth_provider(registry, provider_key, client_id, client_secret)

    return registry
