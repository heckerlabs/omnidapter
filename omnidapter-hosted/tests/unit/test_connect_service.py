"""Unit tests for the hosted connect service — tenant-scoped availability."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from omnidapter.core.metadata import AuthKind, ProviderMetadata, ServiceKind
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.services.connect import (
    is_provider_available,
    list_available_providers,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _settings(**kwargs: Any) -> MagicMock:
    s = MagicMock()
    s.omnidapter_google_client_id = kwargs.get("google_id", "")
    s.omnidapter_google_client_secret = kwargs.get("google_secret", "")
    s.omnidapter_microsoft_client_id = kwargs.get("ms_id", "")
    s.omnidapter_microsoft_client_secret = kwargs.get("ms_secret", "")
    s.omnidapter_zoho_client_id = kwargs.get("zoho_id", "")
    s.omnidapter_zoho_client_secret = kwargs.get("zoho_secret", "")
    return s


def _oauth_provider_meta(key: str) -> ProviderMetadata:
    return ProviderMetadata(
        provider_key=key,
        display_name=key.title(),
        services=[ServiceKind.CALENDAR],
        auth_kinds=[AuthKind.OAUTH2],
        connection_config_fields=[],
    )


def _basic_provider_meta(key: str) -> ProviderMetadata:
    return ProviderMetadata(
        provider_key=key,
        display_name=key.title(),
        services=[ServiceKind.CALENDAR],
        auth_kinds=[AuthKind.BASIC],
        connection_config_fields=[],
    )


def _provider_config(
    tenant_id: uuid.UUID,
    provider_key: str,
    *,
    is_enabled: bool = True,
    has_creds: bool = True,
) -> HostedProviderConfig:
    return HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider_key=provider_key,
        auth_kind="oauth2",
        client_id_encrypted="enc-id" if has_creds else None,
        client_secret_encrypted="enc-secret" if has_creds else None,
        scopes=None,
        is_enabled=is_enabled,
        created_at=_now(),
        updated_at=_now(),
    )


# ---------------------------------------------------------------------------
# is_provider_available — hosted version adds is_enabled check
# ---------------------------------------------------------------------------


def test_is_provider_available_explicit_disable() -> None:
    tenant_id = uuid.uuid4()
    cfg = _provider_config(tenant_id, "google", is_enabled=False)
    settings = _settings(google_id="id", google_secret="secret")
    assert not is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


def test_is_provider_available_own_creds_enabled() -> None:
    tenant_id = uuid.uuid4()
    cfg = _provider_config(tenant_id, "google", is_enabled=True, has_creds=True)
    settings = _settings()
    assert is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


def test_is_provider_available_fallback_used_when_no_config() -> None:
    settings = _settings(google_id="id", google_secret="secret")
    assert is_provider_available(
        provider_key="google", auth_kind="oauth2", config=None, settings=settings
    )


def test_is_provider_available_no_config_no_fallback() -> None:
    settings = _settings()
    assert not is_provider_available(
        provider_key="google", auth_kind="oauth2", config=None, settings=settings
    )


def test_is_provider_available_non_oauth_always_available_by_default() -> None:
    settings = _settings()
    assert is_provider_available(
        provider_key="caldav", auth_kind="basic", config=None, settings=settings
    )


def test_is_provider_available_non_oauth_disabled_explicitly() -> None:
    tenant_id = uuid.uuid4()
    cfg = _provider_config(tenant_id, "caldav", is_enabled=False)
    settings = _settings()
    assert not is_provider_available(
        provider_key="caldav", auth_kind="basic", config=cfg, settings=settings
    )


def test_is_provider_available_oauth_config_no_creds_no_fallback() -> None:
    tenant_id = uuid.uuid4()
    cfg = _provider_config(tenant_id, "google", is_enabled=True, has_creds=False)
    settings = _settings()
    assert not is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


# ---------------------------------------------------------------------------
# list_available_providers — tenant-scoped
# ---------------------------------------------------------------------------


class _ScalarAll:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> _ScalarAll:
        return self

    def all(self) -> list[Any]:
        return self._items


@pytest.mark.asyncio
async def test_list_available_providers_reconnect_returns_single() -> None:
    """Reconnect tokens always return exactly the locked provider."""
    session = AsyncMock()
    omni = MagicMock()
    meta = _oauth_provider_meta("google")
    omni.describe_provider.return_value = meta

    providers = await list_available_providers(
        session=session,
        tenant_id=uuid.uuid4(),
        allowed_providers=None,
        locked_provider_key="google",
        settings=_settings(google_id="id", google_secret="s"),
        omni=omni,
    )

    assert len(providers) == 1
    assert providers[0]["key"] == "google"
    assert providers[0]["credential_schema"] is None


@pytest.mark.asyncio
async def test_list_available_providers_filters_by_allowed() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarAll([]))
    omni = MagicMock()
    omni.list_providers.return_value = ["google", "microsoft", "caldav"]
    omni.describe_provider.side_effect = lambda k: {
        "google": _oauth_provider_meta("google"),
        "microsoft": _oauth_provider_meta("microsoft"),
        "caldav": _basic_provider_meta("caldav"),
    }[k]

    providers = await list_available_providers(
        session=session,
        tenant_id=uuid.uuid4(),
        allowed_providers=["caldav"],
        locked_provider_key=None,
        settings=_settings(),
        omni=omni,
    )

    assert len(providers) == 1
    assert providers[0]["key"] == "caldav"


@pytest.mark.asyncio
async def test_list_available_providers_excludes_disabled() -> None:
    tenant_id = uuid.uuid4()
    cfg = _provider_config(tenant_id, "google", is_enabled=False, has_creds=True)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarAll([cfg]))
    omni = MagicMock()
    omni.list_providers.return_value = ["google"]
    omni.describe_provider.return_value = _oauth_provider_meta("google")

    providers = await list_available_providers(
        session=session,
        tenant_id=tenant_id,
        allowed_providers=None,
        locked_provider_key=None,
        settings=_settings(),
        omni=omni,
    )

    assert providers == []


@pytest.mark.asyncio
async def test_list_available_providers_includes_fallback() -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarAll([]))
    omni = MagicMock()
    omni.list_providers.return_value = ["google"]
    omni.describe_provider.return_value = _oauth_provider_meta("google")

    providers = await list_available_providers(
        session=session,
        tenant_id=uuid.uuid4(),
        allowed_providers=None,
        locked_provider_key=None,
        settings=_settings(google_id="id", google_secret="s"),
        omni=omni,
    )

    assert len(providers) == 1
    assert providers[0]["key"] == "google"
