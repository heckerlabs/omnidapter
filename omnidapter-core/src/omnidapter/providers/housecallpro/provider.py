"""Housecall Pro provider registration class."""

from __future__ import annotations

from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider
from omnidapter.providers.housecallpro.metadata import HOUSECALLPRO_METADATA


class HousecallProProvider(BaseProvider):
    """Housecall Pro provider (API key authentication)."""

    @property
    def metadata(self) -> ProviderMetadata:
        return HOUSECALLPRO_METADATA

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
            from omnidapter.providers.housecallpro.booking import HousecallProBookingService

            return HousecallProBookingService(
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
