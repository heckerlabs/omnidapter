"""
Zoho provider registration class.
"""

from __future__ import annotations

import os
from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider
from omnidapter.providers.zoho.metadata import ZOHO_METADATA
from omnidapter.providers.zoho.oauth import ZohoOAuthMixin


class ZohoProvider(ZohoOAuthMixin, BaseProvider):
    """Zoho Calendar provider implementation."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id if client_id is not None else os.environ.get("ZOHO_CLIENT_ID")
        self._client_secret = (
            client_secret if client_secret is not None else os.environ.get("ZOHO_CLIENT_SECRET")
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return ZOHO_METADATA

    def get_service(
        self,
        kind: Any,
        connection_id: str,
        stored_credential: Any,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        from omnidapter.core.metadata import ServiceKind

        if kind == ServiceKind.CALENDAR:
            from omnidapter.providers.zoho.calendar import ZohoCalendarService

            return ZohoCalendarService(
                connection_id=connection_id,
                stored_credential=stored_credential,
                retry_policy=retry_policy,
                hooks=hooks,
            )
        if kind == ServiceKind.CRM:
            from omnidapter.providers.zoho.crm import ZohoCrmService

            return ZohoCrmService(
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
