"""Provider registry helpers for server request handling."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from omnidapter.core.registry import ProviderRegistry
from omnidapter.providers.apple.provider import AppleProvider
from omnidapter.providers.caldav.provider import CalDAVProvider
from omnidapter.providers.google.provider import GoogleProvider
from omnidapter.providers.microsoft.provider import MicrosoftProvider
from omnidapter.providers.zoho.provider import ZohoProvider

if TYPE_CHECKING:
    from omnidapter_server.config import Settings
    from omnidapter_server.encryption import EncryptionService


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


def build_provider_registry(
    settings: Settings,
    *,
    provider_config: Any | None = None,
    encryption: EncryptionService | None = None,
) -> ProviderRegistry:
    """Build a provider registry for a request-scoped Omnidapter instance.

    Priority:
    1) Built-ins from core environment variables (`GOOGLE_CLIENT_ID`, etc.).
    2) Server fallback credentials from settings (`OMNIDAPTER_*`).
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

    if provider_config and not getattr(provider_config, "is_fallback", False):
        if encryption is None:
            raise ValueError("Encryption service is required for provider_config overrides")

        c_id_enc = getattr(provider_config, "client_id_encrypted", None)
        c_secret_enc = getattr(provider_config, "client_secret_encrypted", None)
        p_key = getattr(provider_config, "provider_key", None)

        if not c_id_enc or not c_secret_enc or not p_key:
            raise ValueError(
                "Provider config is missing required OAuth credentials or provider_key"
            )

        _register_oauth_provider(
            registry,
            p_key,
            encryption.decrypt(c_id_enc),
            encryption.decrypt(c_secret_enc),
        )

    return registry
