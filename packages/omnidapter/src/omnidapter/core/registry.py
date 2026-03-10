from __future__ import annotations

from typing import Protocol

from omnidapter.auth.models import OAuthTokenResult
from omnidapter.core.metadata import ProviderMetadata
from omnidapter.services.calendar.interface import CalendarService
from omnidapter.stores.credentials import StoredCredential


class OAuthProviderAdapter(Protocol):
    async def build_authorization_url(self, connection_id: str, state: str, redirect_uri: str, code_verifier: str) -> str: ...

    async def exchange_code(self, code: str, redirect_uri: str, code_verifier: str) -> OAuthTokenResult: ...

    async def refresh(self, credential: StoredCredential) -> StoredCredential: ...


class Provider(Protocol):
    key: str

    def metadata(self) -> ProviderMetadata: ...

    def calendar_service(self, connection_id: str, credential: StoredCredential) -> CalendarService: ...

    def oauth_adapter(self) -> OAuthProviderAdapter | None: ...


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: dict[str, Provider] = {}

    def register(self, provider: Provider) -> None:
        self._providers[provider.key] = provider

    def get(self, provider_key: str) -> Provider:
        return self._providers[provider_key]

    def describe(self, provider_key: str) -> ProviderMetadata:
        return self.get(provider_key).metadata()

    def keys(self) -> list[str]:
        return sorted(self._providers.keys())
