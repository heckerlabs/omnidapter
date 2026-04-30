"""Square Appointments provider registration class."""

from __future__ import annotations

import os
from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider
from omnidapter.providers.square.metadata import SQUARE_METADATA
from omnidapter.providers.square.oauth import SquareOAuthMixin


class SquareProvider(SquareOAuthMixin, BaseProvider):
    """Square Appointments provider."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id if client_id is not None else os.environ.get("SQUARE_CLIENT_ID")
        self._client_secret = (
            client_secret if client_secret is not None else os.environ.get("SQUARE_CLIENT_SECRET")
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return SQUARE_METADATA

    def get_service(
        self,
        kind: Any,
        connection_id: str,
        stored_credential: Any,
        retry_policy: Any = None,
        hooks: Any = None,
    ) -> Any:
        from omnidapter.core.metadata import ServiceKind

        if kind == ServiceKind.BOOKING:
            from omnidapter.providers.square.booking import SquareBookingService

            return SquareBookingService(
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
