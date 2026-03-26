"""Unit tests for the connect service — availability, schemas, non-OAuth flow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from omnidapter.core.metadata import AuthKind, ConnectionConfigField, ProviderMetadata, ServiceKind
from omnidapter_hosted.models.provider_config import HostedProviderConfig
from omnidapter_hosted.services.connect import (
    _build_stored_credential,
    _field_to_schema,
    build_credential_schema,
    create_credential_connection,
    is_provider_available,
    list_available_providers,
)
from omnidapter_server.models.connection import Connection


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
        connection_config_fields=[
            ConnectionConfigField(
                name="server_url",
                label="Server URL",
                description="CalDAV server",
                type="url",
                required=True,
            ),
            ConnectionConfigField(
                name="username",
                label="Username",
                description="",
                type="text",
                required=True,
            ),
            ConnectionConfigField(
                name="password",
                label="Password",
                description="",
                type="password",
                required=True,
            ),
        ],
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
# _field_to_schema
# ---------------------------------------------------------------------------


def test_field_to_schema_basic() -> None:
    field = ConnectionConfigField(
        name="server_url",
        label="Server URL",
        description="CalDAV server",
        type="url",
        required=True,
        placeholder="https://caldav.example.com/",
    )
    schema = _field_to_schema(field)
    assert schema["key"] == "server_url"
    assert schema["label"] == "Server URL"
    assert schema["type"] == "url"
    assert schema["required"] is True
    assert schema["placeholder"] == "https://caldav.example.com/"
    assert schema["help_text"] == "CalDAV server"


def test_field_to_schema_derives_label_from_name() -> None:
    field = ConnectionConfigField(name="api_key", description="", type="text", required=True)
    schema = _field_to_schema(field)
    assert schema["label"] == "Api Key"


def test_field_to_schema_no_help_text_when_empty_description() -> None:
    field = ConnectionConfigField(name="x", description="", type="text", required=False)
    schema = _field_to_schema(field)
    assert "help_text" not in schema


def test_field_to_schema_uses_example_as_placeholder_fallback() -> None:
    field = ConnectionConfigField(
        name="url",
        description="",
        type="url",
        required=True,
        example="https://example.com",
    )
    schema = _field_to_schema(field)
    assert schema["placeholder"] == "https://example.com"


# ---------------------------------------------------------------------------
# build_credential_schema
# ---------------------------------------------------------------------------


def test_build_credential_schema_oauth_returns_none() -> None:
    meta = _oauth_provider_meta("google")
    assert build_credential_schema(meta) is None


def test_build_credential_schema_basic_returns_schema() -> None:
    meta = _basic_provider_meta("caldav")
    schema = build_credential_schema(meta)
    assert schema is not None
    assert len(schema["fields"]) == 3
    keys = [f["key"] for f in schema["fields"]]
    assert keys == ["server_url", "username", "password"]
    pw = next(f for f in schema["fields"] if f["key"] == "password")
    assert pw["type"] == "password"


# ---------------------------------------------------------------------------
# is_provider_available
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
    # Config exists (is_enabled=True) but has no encrypted credentials, no fallback
    cfg = _provider_config(tenant_id, "google", is_enabled=True, has_creds=False)
    settings = _settings()
    assert not is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


# ---------------------------------------------------------------------------
# list_available_providers
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


# ---------------------------------------------------------------------------
# _build_stored_credential
# ---------------------------------------------------------------------------


def test_build_stored_credential_basic() -> None:
    creds = {"server_url": "https://caldav.example.com/", "username": "u", "password": "p"}
    stored = _build_stored_credential("caldav", "basic", creds)
    assert stored.auth_kind == AuthKind.BASIC
    assert stored.credentials.username == "u"  # type: ignore[union-attr]
    assert stored.credentials.password == "p"  # type: ignore[union-attr]
    assert stored.provider_config == {"server_url": "https://caldav.example.com/"}


def test_build_stored_credential_unsupported_kind() -> None:
    with pytest.raises(ValueError, match="Unsupported auth_kind"):
        _build_stored_credential("some_provider", "oauth2", {})


# ---------------------------------------------------------------------------
# create_credential_connection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_credential_connection_success() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    conn_id = uuid.uuid4()

    # Mock execute to return a result with scalar_one_or_none method
    mock_result = MagicMock()
    mock_result.scalar_one_or_none = MagicMock(return_value=conn_id)
    session.execute = AsyncMock(return_value=mock_result)

    encryption = MagicMock()
    encryption.encrypt.return_value = "enc_creds"

    async def _refresh_with_id(obj: Any) -> None:
        if isinstance(obj, Connection):
            obj.id = conn_id
            obj.created_at = _now()
            obj.updated_at = _now()

    session.refresh = AsyncMock(side_effect=_refresh_with_id)

    async def noop_persist(conn: Connection, s: Any) -> None:
        pass

    async def noop_validate(provider_key: str, creds: dict[str, str]) -> None:
        pass

    conn = await create_credential_connection(
        provider_key="caldav",
        auth_kind="basic",
        credentials={"server_url": "https://caldav.example.com/", "username": "u", "password": "p"},
        external_id="user_1",
        session=session,
        encryption=encryption,
        persist_post_create=noop_persist,
        validate=noop_validate,
    )

    assert conn.provider_key == "caldav"
    assert conn.external_id == "user_1"
    # execute called for the status UPDATE
    assert session.execute.await_count >= 1


@pytest.mark.asyncio
async def test_create_credential_connection_validation_failure() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    async def _refresh_with_id(obj: Any) -> None:
        if isinstance(obj, Connection):
            obj.id = uuid.uuid4()
            obj.created_at = _now()
            obj.updated_at = _now()

    session.refresh = AsyncMock(side_effect=_refresh_with_id)

    async def failing_validate(provider_key: str, creds: dict[str, str]) -> None:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_credentials", "message": "Bad creds"},
        )

    async def noop_persist(conn: Connection, s: Any) -> None:
        pass

    encryption = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await create_credential_connection(
            provider_key="caldav",
            auth_kind="basic",
            credentials={
                "server_url": "https://caldav.example.com/",
                "username": "u",
                "password": "bad",
            },
            external_id=None,
            session=session,
            encryption=encryption,
            persist_post_create=noop_persist,
            validate=failing_validate,
        )

    assert exc_info.value.status_code == 422
    # Verify we attempted to revoke the connection
    session.execute.assert_awaited()
