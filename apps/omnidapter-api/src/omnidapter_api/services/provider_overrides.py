"""Helpers for registering provider-specific OAuth credentials."""

from __future__ import annotations

from omnidapter import Omnidapter
from omnidapter.providers.google.provider import GoogleProvider
from omnidapter.providers.microsoft.provider import MicrosoftProvider
from omnidapter.providers.zoho.provider import ZohoProvider

from omnidapter_api.config import Settings


def _build_oauth_provider(provider_key: str, client_id: str, client_secret: str):
    key = provider_key.lower()
    if key == "google":
        return GoogleProvider(client_id=client_id, client_secret=client_secret)
    if key == "microsoft":
        return MicrosoftProvider(client_id=client_id, client_secret=client_secret)
    if key == "zoho":
        return ZohoProvider(client_id=client_id, client_secret=client_secret)
    raise ValueError(f"Custom OAuth credentials are not supported for provider {provider_key!r}")


def register_provider_credentials(
    omni: Omnidapter,
    provider_key: str,
    client_id: str,
    client_secret: str,
) -> None:
    if not client_id or not client_secret:
        raise ValueError("Provider client_id and client_secret are required")
    omni.register_provider(_build_oauth_provider(provider_key, client_id, client_secret))


def register_fallback_provider_credentials(omni: Omnidapter, settings: Settings) -> None:
    fallback_credentials = {
        "google": (
            settings.omnidapter_google_client_id,
            settings.omnidapter_google_client_secret,
        ),
        "microsoft": (
            settings.omnidapter_microsoft_client_id,
            settings.omnidapter_microsoft_client_secret,
        ),
        "zoho": (
            settings.omnidapter_zoho_client_id,
            settings.omnidapter_zoho_client_secret,
        ),
    }

    for provider_key, (client_id, client_secret) in fallback_credentials.items():
        if client_id and client_secret:
            omni.register_provider(
                _build_oauth_provider(
                    provider_key=provider_key,
                    client_id=client_id,
                    client_secret=client_secret,
                )
            )
