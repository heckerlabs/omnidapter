"""Unit tests for the GET /v1/providers management endpoint."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from omnidapter.core.metadata import AuthKind, ProviderMetadata, ServiceKind
from omnidapter_hosted.dependencies import HostedAuthContext
from omnidapter_hosted.models.api_key import HostedAPIKey
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.routers.providers import (
    _config_status,
    _effective_is_enabled,
    _has_fallback,
    list_providers_management,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _auth() -> HostedAuthContext:
    tenant = Tenant(
        id=uuid.uuid4(),
        name="Acme",
        plan="free",
        is_active=True,
        created_at=_now(),
        updated_at=_now(),
    )
    api_key = HostedAPIKey(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        name="key",
        key_hash="hash",
        key_prefix="omni_key_abcd",
        created_at=_now(),
        last_used_at=None,
    )
    return HostedAuthContext(api_key=api_key, tenant=tenant)


def _settings(**kwargs: Any) -> MagicMock:
    s = MagicMock()
    s.omnidapter_google_client_id = kwargs.get("google_id", "")
    s.omnidapter_google_client_secret = kwargs.get("google_secret", "")
    s.omnidapter_microsoft_client_id = kwargs.get("ms_id", "")
    s.omnidapter_microsoft_client_secret = kwargs.get("ms_secret", "")
    s.omnidapter_zoho_client_id = kwargs.get("zoho_id", "")
    s.omnidapter_zoho_client_secret = kwargs.get("zoho_secret", "")
    return s


def _config(
    tenant_id: uuid.UUID,
    provider_key: str,
    *,
    has_creds: bool = True,
    is_enabled: bool = True,
) -> HostedProviderConfig:
    return HostedProviderConfig(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        provider_key=provider_key,
        auth_kind="oauth2",
        client_id_encrypted="enc" if has_creds else None,
        client_secret_encrypted="enc" if has_creds else None,
        scopes=None,
        is_enabled=is_enabled,
        created_at=_now(),
        updated_at=_now(),
    )


class _ScalarAll:
    def __init__(self, items: list[Any]) -> None:
        self._items = items

    def scalars(self) -> _ScalarAll:
        return self

    def all(self) -> list[Any]:
        return self._items


# ---------------------------------------------------------------------------
# _has_fallback
# ---------------------------------------------------------------------------


def test_has_fallback_google_true() -> None:
    settings = _settings(google_id="id", google_secret="secret")
    assert _has_fallback("google", settings)


def test_has_fallback_google_false_when_empty() -> None:
    settings = _settings()
    assert not _has_fallback("google", settings)


def test_has_fallback_unknown_provider() -> None:
    settings = _settings(google_id="id", google_secret="s")
    assert not _has_fallback("caldav", settings)


def test_has_fallback_microsoft() -> None:
    settings = _settings(ms_id="id", ms_secret="s")
    assert _has_fallback("microsoft", settings)


# ---------------------------------------------------------------------------
# _config_status
# ---------------------------------------------------------------------------


def test_config_status_configured() -> None:
    tenant_id = uuid.uuid4()
    cfg = _config(tenant_id, "google", has_creds=True)
    assert _config_status("google", "oauth2", cfg, False) == "configured"


def test_config_status_fallback_when_no_own_creds() -> None:
    assert _config_status("google", "oauth2", None, True) == "fallback"


def test_config_status_not_configured() -> None:
    assert _config_status("google", "oauth2", None, False) == "not_configured"


def test_config_status_non_oauth_always_configured() -> None:
    assert _config_status("caldav", "basic", None, False) == "configured"


# ---------------------------------------------------------------------------
# _effective_is_enabled
# ---------------------------------------------------------------------------


def test_effective_is_enabled_uses_config_flag() -> None:
    tenant_id = uuid.uuid4()
    cfg = _config(tenant_id, "google", is_enabled=False)
    assert not _effective_is_enabled(cfg, "oauth2", True)


def test_effective_is_enabled_no_config_oauth_fallback_available() -> None:
    assert _effective_is_enabled(None, "oauth2", True)


def test_effective_is_enabled_no_config_oauth_no_fallback() -> None:
    assert not _effective_is_enabled(None, "oauth2", False)


def test_effective_is_enabled_no_config_non_oauth() -> None:
    assert _effective_is_enabled(None, "basic", False)


# ---------------------------------------------------------------------------
# list_providers_management
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_providers_management_structure() -> None:
    auth = _auth()
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarAll([]))
    settings = _settings(google_id="id", google_secret="s")
    settings.omnidapter_google_client_id = "id"
    settings.omnidapter_google_client_secret = "s"

    omni = MagicMock()
    omni.list_providers.return_value = ["google", "caldav"]

    def _describe(key: str) -> ProviderMetadata:
        if key == "google":
            return ProviderMetadata(
                provider_key="google",
                display_name="Google Calendar",
                services=[ServiceKind.CALENDAR],
                auth_kinds=[AuthKind.OAUTH2],
            )
        return ProviderMetadata(
            provider_key="caldav",
            display_name="CalDAV",
            services=[ServiceKind.CALENDAR],
            auth_kinds=[AuthKind.BASIC],
        )

    omni.describe_provider.side_effect = _describe

    with (
        patch("omnidapter_hosted.routers.providers.Omnidapter", return_value=omni),
    ):
        resp = await list_providers_management(
            auth=auth,
            session=session,
            settings=settings,
            request_id="req_1",
        )

    assert "data" in resp
    keys = [p["provider_key"] for p in resp["data"]]
    assert "google" in keys
    assert "caldav" in keys

    google_row = next(p for p in resp["data"] if p["provider_key"] == "google")
    assert google_row["fallback_available"] is True
    assert google_row["config_status"] == "fallback"


@pytest.mark.asyncio
async def test_list_providers_management_configured_provider() -> None:
    auth = _auth()
    cfg = _config(auth.tenant_id, "google", has_creds=True, is_enabled=True)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=_ScalarAll([cfg]))
    settings = _settings()

    omni = MagicMock()
    omni.list_providers.return_value = ["google"]
    omni.describe_provider.return_value = ProviderMetadata(
        provider_key="google",
        display_name="Google Calendar",
        services=[ServiceKind.CALENDAR],
        auth_kinds=[AuthKind.OAUTH2],
    )

    with (
        patch("omnidapter_hosted.routers.providers.Omnidapter", return_value=omni),
    ):
        resp = await list_providers_management(
            auth=auth,
            session=session,
            settings=settings,
            request_id="req_2",
        )

    google = resp["data"][0]
    assert google["config_status"] == "configured"
    assert google["is_enabled"] is True
