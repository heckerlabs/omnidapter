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
        self._client_id = client_id or os.environ.get("ZOHO_CLIENT_ID", "")
        self._client_secret = client_secret or os.environ.get("ZOHO_CLIENT_SECRET", "")

    @property
    def metadata(self) -> ProviderMetadata:
        return ZOHO_METADATA

    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: Any,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        from omnidapter.providers.zoho.calendar import ZohoCalendarService
        return ZohoCalendarService(
            connection_id=connection_id,
            stored_credential=stored_credential,
            retry_policy=retry_policy,
            hooks=hooks,
        )
