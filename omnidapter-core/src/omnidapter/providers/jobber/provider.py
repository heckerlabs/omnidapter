"""Jobber provider registration class."""

from __future__ import annotations

import os
from typing import Any

from omnidapter.core.metadata import ProviderMetadata
from omnidapter.providers._base import BaseProvider
from omnidapter.providers.jobber.metadata import JOBBER_METADATA
from omnidapter.providers.jobber.oauth import JobberOAuthMixin


class JobberProvider(JobberOAuthMixin, BaseProvider):
    """Jobber provider."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> None:
        self._client_id = client_id if client_id is not None else os.environ.get("JOBBER_CLIENT_ID")
        self._client_secret = (
            client_secret if client_secret is not None else os.environ.get("JOBBER_CLIENT_SECRET")
        )

    @property
    def metadata(self) -> ProviderMetadata:
        return JOBBER_METADATA

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
            from omnidapter.providers.jobber.booking import JobberBookingService

            return JobberBookingService(
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
