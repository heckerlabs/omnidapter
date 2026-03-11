"""
Microsoft provider registration class.
"""

from __future__ import annotations

import os
from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider
from omnidapter.providers.microsoft.metadata import MICROSOFT_METADATA
from omnidapter.providers.microsoft.oauth import MicrosoftOAuthMixin


class MicrosoftProvider(MicrosoftOAuthMixin, BaseProvider):
    """Microsoft Calendar provider implementation."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = (
            client_id if client_id is not None else os.environ.get("MICROSOFT_CLIENT_ID")
        )
        self._client_secret = (
            client_secret
            if client_secret is not None
            else os.environ.get("MICROSOFT_CLIENT_SECRET")
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return MICROSOFT_METADATA

    def get_calendar_service(
        self,
        connection_id: str,
        stored_credential: Any,
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
