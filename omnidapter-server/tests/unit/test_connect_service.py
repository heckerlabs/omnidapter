"""Unit tests for the server connect service — availability, schemas, non-OAuth flow."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from omnidapter.core.metadata import AuthKind, ConnectionConfigField, ProviderMetadata, ServiceKind
from omnidapter_server.models.connection import Connection
from omnidapter_server.services.connect import (
    _build_stored_credential,
    _default_caldav_validator,
    _field_to_schema,
    build_credential_schema,
    create_credential_connection,
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
    provider_key: str,
    *,
    has_creds: bool = True,
) -> MagicMock:
    cfg = MagicMock()
    cfg.provider_key = provider_key
    cfg.client_id_encrypted = "enc-id" if has_creds else None
    cfg.client_secret_encrypted = "enc-secret" if has_creds else None
    return cfg


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
# is_provider_available (server version — no is_enabled check)
# ---------------------------------------------------------------------------


def test_is_provider_available_non_oauth_always_available() -> None:
    settings = _settings()
    assert is_provider_available(
        provider_key="caldav", auth_kind="basic", config=None, settings=settings
    )


def test_is_provider_available_oauth_own_creds() -> None:
    cfg = _provider_config("google", has_creds=True)
    settings = _settings()
    assert is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


def test_is_provider_available_oauth_no_creds_with_fallback() -> None:
    settings = _settings(google_id="id", google_secret="secret")
    assert is_provider_available(
        provider_key="google", auth_kind="oauth2", config=None, settings=settings
    )


def test_is_provider_available_oauth_no_creds_no_fallback() -> None:
    settings = _settings()
    assert not is_provider_available(
        provider_key="google", auth_kind="oauth2", config=None, settings=settings
    )


def test_is_provider_available_oauth_config_no_creds_with_fallback() -> None:
    cfg = _provider_config("google", has_creds=False)
    settings = _settings(google_id="id", google_secret="secret")
    assert is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


def test_is_provider_available_oauth_config_no_creds_no_fallback() -> None:
    cfg = _provider_config("google", has_creds=False)
    settings = _settings()
    assert not is_provider_available(
        provider_key="google", auth_kind="oauth2", config=cfg, settings=settings
    )


# ---------------------------------------------------------------------------
# list_available_providers (server version — callback-based)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_available_providers_reconnect_returns_single() -> None:
    omni = MagicMock()
    meta = _oauth_provider_meta("google")
    omni.describe_provider.return_value = meta
    settings = _settings(google_id="id", google_secret="s")

    providers = await list_available_providers(
        allowed_providers=None,
        locked_provider_key="google",
        settings=settings,
        omni=omni,
        load_provider_configs=AsyncMock(return_value={}),
        check_availability=lambda pk, ak, cfg: True,
    )

    assert len(providers) == 1
    assert providers[0]["key"] == "google"
    assert providers[0]["credential_schema"] is None


@pytest.mark.asyncio
async def test_list_available_providers_filters_by_allowed() -> None:
    omni = MagicMock()
    omni.list_providers.return_value = ["google", "microsoft", "caldav"]
    omni.describe_provider.side_effect = lambda k: {
        "google": _oauth_provider_meta("google"),
        "microsoft": _oauth_provider_meta("microsoft"),
        "caldav": _basic_provider_meta("caldav"),
    }[k]
    settings = _settings()

    providers = await list_available_providers(
        allowed_providers=["caldav"],
        locked_provider_key=None,
        settings=settings,
        omni=omni,
        load_provider_configs=AsyncMock(return_value={}),
        check_availability=lambda pk, ak, cfg: True,
    )

    assert len(providers) == 1
    assert providers[0]["key"] == "caldav"


@pytest.mark.asyncio
async def test_list_available_providers_check_availability_called() -> None:
    omni = MagicMock()
    omni.list_providers.return_value = ["google"]
    omni.describe_provider.return_value = _oauth_provider_meta("google")
    cfg = _provider_config("google")
    settings = _settings()

    checked: list[tuple[str, str, Any]] = []

    def _check(pk: str, ak: str, c: Any) -> bool:
        checked.append((pk, ak, c))
        return True

    await list_available_providers(
        allowed_providers=None,
        locked_provider_key=None,
        settings=settings,
        omni=omni,
        load_provider_configs=AsyncMock(return_value={"google": cfg}),
        check_availability=_check,
    )

    assert len(checked) == 1
    assert checked[0][0] == "google"
    assert checked[0][2] is cfg


@pytest.mark.asyncio
async def test_list_available_providers_excludes_unavailable() -> None:
    omni = MagicMock()
    omni.list_providers.return_value = ["google"]
    omni.describe_provider.return_value = _oauth_provider_meta("google")
    settings = _settings()

    providers = await list_available_providers(
        allowed_providers=None,
        locked_provider_key=None,
        settings=settings,
        omni=omni,
        load_provider_configs=AsyncMock(return_value={}),
        check_availability=lambda pk, ak, cfg: False,
    )

    assert providers == []


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

    async def noop_validate(provider_key: str, creds: dict[str, str]) -> None:
        pass

    conn = await create_credential_connection(
        provider_key="caldav",
        auth_kind="basic",
        credentials={"server_url": "https://caldav.example.com/", "username": "u", "password": "p"},
        external_id="user_1",
        session=session,
        encryption=encryption,
        validate=noop_validate,
    )

    assert conn.provider_key == "caldav"
    assert conn.external_id == "user_1"
    assert session.execute.await_count >= 1


@pytest.mark.asyncio
async def test_create_credential_connection_calls_persist_callback() -> None:
    session = AsyncMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.add = MagicMock()

    conn_id = uuid.uuid4()
    mock_result = MagicMock()
    session.execute = AsyncMock(return_value=mock_result)
    encryption = MagicMock()

    async def _refresh_with_id(obj: Any) -> None:
        if isinstance(obj, Connection):
            obj.id = conn_id
            obj.created_at = _now()
            obj.updated_at = _now()

    session.refresh = AsyncMock(side_effect=_refresh_with_id)

    callback_calls: list[tuple[Connection, Any]] = []

    async def _persist(conn: Connection, s: Any) -> None:
        callback_calls.append((conn, s))

    async def noop_validate(provider_key: str, creds: dict[str, str]) -> None:
        pass

    await create_credential_connection(
        provider_key="caldav",
        auth_kind="basic",
        credentials={"server_url": "https://caldav.example.com/", "username": "u", "password": "p"},
        external_id=None,
        session=session,
        encryption=encryption,
        persist_post_create=_persist,
        validate=noop_validate,
    )

    assert len(callback_calls) == 1
    assert isinstance(callback_calls[0][0], Connection)


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
            validate=failing_validate,
        )

    assert exc_info.value.status_code == 422
    session.execute.assert_awaited()


# ---------------------------------------------------------------------------
# _default_caldav_validator — DNS-based SSRF mitigation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_default_caldav_validator_blocks_domain_resolving_to_private_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket as socket_mod

    private_addrinfo = [(socket_mod.AF_INET, socket_mod.SOCK_STREAM, 0, "", ("192.168.1.1", 0))]
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **kw: private_addrinfo)

    with pytest.raises(HTTPException) as exc_info:
        await _default_caldav_validator(
            "caldav",
            {
                "server_url": "https://caldav.attacker.example.com/",
                "username": "u",
                "password": "p",
            },
        )

    assert exc_info.value.status_code == 422
    detail = cast(dict[str, Any], exc_info.value.detail)
    assert detail["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_default_caldav_validator_blocks_unresolvable_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket as socket_mod

    def _fail(*a: Any, **kw: Any) -> None:
        raise socket_mod.gaierror("Name or service not known")

    monkeypatch.setattr("socket.getaddrinfo", _fail)

    with pytest.raises(HTTPException) as exc_info:
        await _default_caldav_validator(
            "caldav",
            {
                "server_url": "https://does-not-exist.invalid/",
                "username": "u",
                "password": "p",
            },
        )

    assert exc_info.value.status_code == 422
    assert cast(dict[str, Any], exc_info.value.detail)["code"] == "invalid_credentials"


@pytest.mark.asyncio
async def test_default_caldav_validator_allows_public_hostname(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket as socket_mod

    import httpx

    public_addrinfo = [(socket_mod.AF_INET, socket_mod.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]
    monkeypatch.setattr("socket.getaddrinfo", lambda *a, **kw: public_addrinfo)

    mock_response = MagicMock()
    mock_response.status_code = 207

    class _MockClient:
        async def __aenter__(self) -> _MockClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            pass

        async def request(self, *a: Any, **kw: Any) -> MagicMock:
            return mock_response

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _MockClient())

    # Should not raise
    await _default_caldav_validator(
        "caldav",
        {
            "server_url": "https://caldav.example.com/",
            "username": "u",
            "password": "p",
        },
    )
