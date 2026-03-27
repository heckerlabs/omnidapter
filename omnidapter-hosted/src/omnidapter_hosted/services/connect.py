"""Connect UI service — hosted extensions with tenant-scoped provider availability."""

from __future__ import annotations

import uuid
from typing import Any

from omnidapter_server.services.connect import (
    AvailabilityChecker as AvailabilityChecker,  # re-export
)
from omnidapter_server.services.connect import (
    ConnectionPostCreate as ConnectionPostCreate,  # re-export
)
from omnidapter_server.services.connect import (
    CredentialValidator as CredentialValidator,  # re-export
)
from omnidapter_server.services.connect import (
    ProviderConfigsLoader as ProviderConfigsLoader,  # re-export
)
from omnidapter_server.services.connect import (
    _default_caldav_validator as _default_caldav_validator,  # re-export
)
from omnidapter_server.services.connect import (
    build_credential_schema as build_credential_schema,  # re-export
)
from omnidapter_server.services.connect import (
    create_credential_connection as create_credential_connection,  # re-export
)
from omnidapter_server.services.connect import (
    is_provider_available as _server_is_provider_available,
)
from omnidapter_server.services.connect import (
    list_available_providers as _server_list_available_providers,
)
from omnidapter_server.services.connect import (
    update_credential_connection as update_credential_connection,  # re-export
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.models.provider_config import HostedProviderConfig

# ---------------------------------------------------------------------------
# Provider availability — hosted adds is_enabled check
# ---------------------------------------------------------------------------


def is_provider_available(
    *,
    provider_key: str,
    auth_kind: str,
    config: HostedProviderConfig | None,
    settings: HostedSettings,
) -> bool:
    """Return True if the provider is available for end-user connections.

    Extends the server version by honouring the ``is_enabled`` flag on
    ``HostedProviderConfig``.
    """
    if config is not None and not config.is_enabled:
        return False  # explicitly disabled by tenant
    return _server_is_provider_available(
        provider_key=provider_key,
        auth_kind=auth_kind,
        config=config,
        settings=settings,
    )


async def list_available_providers(
    *,
    session: AsyncSession,
    tenant_id: uuid.UUID,
    allowed_providers: list[str] | None,
    locked_provider_key: str | None,
    settings: HostedSettings,
    omni: Any,
) -> list[dict[str, Any]]:
    """Return the list of providers available for this connect session.

    Delegates to the server's ``list_available_providers`` with
    tenant-scoped callbacks so the ``is_enabled`` flag per tenant is honoured.
    """

    async def _load_configs() -> dict[str, HostedProviderConfig]:
        result = await session.execute(
            select(HostedProviderConfig).where(HostedProviderConfig.tenant_id == tenant_id)
        )
        return {c.provider_key: c for c in result.scalars().all()}

    def _check(provider_key: str, auth_kind: str, config: HostedProviderConfig | None) -> bool:
        return is_provider_available(
            provider_key=provider_key,
            auth_kind=auth_kind,
            config=config,
            settings=settings,
        )

    # HostedSettings is a subclass of Settings so it satisfies the type
    return await _server_list_available_providers(
        allowed_providers=allowed_providers,
        locked_provider_key=locked_provider_key,
        settings=settings,
        omni=omni,
        load_provider_configs=_load_configs,
        check_availability=_check,
    )
