"""
CalDAV provider registration class.
"""

from __future__ import annotations

from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider, OAuthConfig
from omnidapter.providers.caldav.metadata import CALDAV_METADATA
from omnidapter.stores.credentials import StoredCredential


class CalDAVProvider(BaseProvider):
    """CalDAV protocol provider (configurable server URL)."""

    @property
    def metadata(self) -> ProviderMetadata:
        return CALDAV_METADATA

    def get_oauth_config(self) -> OAuthConfig | None:
        return None  # CalDAV uses Basic auth, not OAuth

    def get_service(
        self,
        kind: Any,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        from omnidapter.core.metadata import ServiceKind

        if kind == ServiceKind.CALENDAR:
            from omnidapter.providers.caldav.calendar import CalDAVCalendarService

            return CalDAVCalendarService(
                connection_id=connection_id,
                stored_credential=stored_credential,
                retry_policy=retry_policy,
                hooks=hooks,
            )
        from omnidapter.core.errors import UnsupportedCapabilityError

        raise UnsupportedCapabilityError(
            f"Provider {self.metadata.provider_key!r} does not support {kind.value!r}.",
            provider_key=self.metadata.provider_key,
            capability=kind,
        )
