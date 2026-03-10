"""
Microsoft provider registration class.
"""
from __future__ import annotations

import os
from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider, OAuthConfig
from omnidapter.providers.microsoft.metadata import MICROSOFT_METADATA
from omnidapter.providers.microsoft.oauth import (
    build_microsoft_oauth_config,
    exchange_microsoft_code,
    refresh_microsoft_token,
)
from omnidapter.stores.credentials import StoredCredential


class MicrosoftProvider(BaseProvider):
    """Microsoft Calendar provider implementation."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id or os.environ.get("MICROSOFT_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("MICROSOFT_CLIENT_SECRET", "")

    @property
    def metadata(self) -> ProviderMetadata:
        return MICROSOFT_METADATA

    def get_oauth_config(self) -> OAuthConfig | None:
        if not self._client_id:
            return None
        return build_microsoft_oauth_config(self._client_id, self._client_secret)

    async def exchange_code_for_tokens(
        self,
        connection_id: str,
        code: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> StoredCredential:
        return await exchange_microsoft_code(
            self._client_id, self._client_secret, code, redirect_uri, code_verifier=code_verifier
        )

    async def refresh_token(self, stored: StoredCredential) -> StoredCredential:
        return await refresh_microsoft_token(self._client_id, self._client_secret, stored)

    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        from omnidapter.providers.microsoft.calendar import MicrosoftCalendarService
        return MicrosoftCalendarService(
            connection_id=connection_id,
            stored_credential=stored_credential,
            retry_policy=retry_policy,
            hooks=hooks,
        )
