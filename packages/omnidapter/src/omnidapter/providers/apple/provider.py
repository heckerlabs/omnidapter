"""
Apple Calendar provider registration class.
"""
from __future__ import annotations

from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider, OAuthConfig
from omnidapter.providers.apple.metadata import APPLE_METADATA
from omnidapter.stores.credentials import StoredCredential


class AppleProvider(BaseProvider):
    """Apple Calendar provider (iCloud CalDAV with pre-configured server URL)."""

    @property
    def metadata(self) -> ProviderMetadata:
        return APPLE_METADATA

    def get_oauth_config(self) -> OAuthConfig | None:
        return None  # Apple Calendar uses Basic auth with app-specific passwords

    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        from omnidapter.providers.apple.calendar import AppleCalendarService
        return AppleCalendarService(
            connection_id=connection_id,
            stored_credential=stored_credential,
            retry_policy=retry_policy,
            hooks=hooks,
        )
