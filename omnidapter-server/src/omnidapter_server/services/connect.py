"""Connect UI service — provider availability, credential schemas, non-OAuth flows."""

from __future__ import annotations

import asyncio
import base64
import ipaddress
import socket
import urllib.parse
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import HTTPException
from omnidapter.auth.models import BasicCredentials
from omnidapter.core.metadata import AuthKind, ConnectionConfigField, ProviderMetadata
from omnidapter.stores.credentials import StoredCredential
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.connection import Connection, ConnectionStatus
from omnidapter_server.stores.credential_store import DatabaseCredentialStore

# CalDAV SSRF prevention: well-known private hostnames that must always be blocked
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "ip6-localhost",
        "ip6-loopback",
        "broadcasthost",
    }
)
_BLOCKED_SUFFIXES = (".local", ".localhost", ".internal", ".corp", ".home", ".lan", ".intranet")

# CalDAV validation retry policy for transient failures
_TRANSIENT_STATUS_CODES = frozenset({502, 503})
_MAX_CALDAV_RETRIES = 2
_CALDAV_RETRY_DELAY_SECONDS = 0.5

# ---------------------------------------------------------------------------
# Credential schema building
# ---------------------------------------------------------------------------


def _field_to_schema(field: ConnectionConfigField) -> dict[str, Any]:
    """Convert a ConnectionConfigField to a connect UI schema field."""
    label = field.label or field.name.replace("_", " ").title()
    schema: dict[str, Any] = {
        "key": field.name,
        "label": label,
        "type": field.type,
        "required": field.required,
    }
    if field.placeholder is not None:
        schema["placeholder"] = field.placeholder
    elif field.example is not None:
        schema["placeholder"] = field.example
    if field.description:
        schema["help_text"] = field.description
    if field.options is not None:
        schema["options"] = field.options
    return schema


def build_credential_schema(meta: ProviderMetadata) -> dict[str, Any] | None:
    """Return a credential_schema dict for non-OAuth providers, or None for OAuth."""
    is_oauth = any(k == AuthKind.OAUTH2 for k in meta.auth_kinds)
    if is_oauth:
        return None
    if not meta.connection_config_fields:
        return None
    return {"fields": [_field_to_schema(f) for f in meta.connection_config_fields]}


# ---------------------------------------------------------------------------
# Provider availability
# ---------------------------------------------------------------------------


def _has_fallback(provider_key: str, settings: Settings) -> bool:
    if provider_key == "google":
        return bool(
            settings.omnidapter_google_client_id and settings.omnidapter_google_client_secret
        )
    if provider_key == "microsoft":
        return bool(
            settings.omnidapter_microsoft_client_id and settings.omnidapter_microsoft_client_secret
        )
    if provider_key == "zoho":
        return bool(settings.omnidapter_zoho_client_id and settings.omnidapter_zoho_client_secret)
    return False


def is_provider_available(
    *,
    provider_key: str,
    auth_kind: str,
    config: Any | None,
    settings: Settings,
) -> bool:
    """Return True if the provider is available for end-user connections.

    Server version — no ``is_enabled`` check (server's ProviderConfig has no such flag).
    - Non-OAuth provider → always available.
    - OAuth provider with own credentials in config → available.
    - OAuth provider with env-level fallback credentials → available.
    """
    if auth_kind != "oauth2":
        return True  # non-OAuth providers are self-service; no OAuth app needed

    has_own_creds = (
        config is not None
        and bool(config.client_id_encrypted)
        and bool(config.client_secret_encrypted)
    )
    return has_own_creds or _has_fallback(provider_key, settings)


ProviderConfigsLoader = Callable[[], Awaitable[dict[str, Any]]]
AvailabilityChecker = Callable[[str, str, Any | None], bool]


async def list_available_providers(
    *,
    allowed_providers: list[str] | None,
    locked_provider_key: str | None,
    settings: Settings,
    omni: Any,
    load_provider_configs: ProviderConfigsLoader,
    check_availability: AvailabilityChecker,
) -> list[dict[str, Any]]:
    """Return the list of providers available for this connect session.

    If ``locked_provider_key`` is set (reconnect token), only that provider is
    returned regardless of ``allowed_providers`` or availability.

    ``load_provider_configs`` is a no-arg async callable returning a
    ``{provider_key: config}`` dict. ``check_availability`` is called for each
    candidate with ``(provider_key, auth_kind, config)``.  Both are injected so
    hosted can supply tenant-scoped implementations while server uses the
    defaults from the connect router.
    """
    # Reconnect — return only the locked provider
    if locked_provider_key is not None:
        try:
            meta = omni.describe_provider(locked_provider_key)
        except KeyError:
            return []
        auth_kind = meta.auth_kinds[0].value if meta.auth_kinds else "oauth2"
        return [
            {
                "key": locked_provider_key,
                "name": meta.display_name,
                "auth_kind": auth_kind,
                "credential_schema": build_credential_schema(meta),
            }
        ]

    configs = await load_provider_configs()

    allowed_set = set(allowed_providers) if allowed_providers is not None else None
    available: list[dict[str, Any]] = []

    for provider_key in omni.list_providers():
        if allowed_set is not None and provider_key not in allowed_set:
            continue

        try:
            meta = omni.describe_provider(provider_key)
        except KeyError:
            continue

        auth_kind = meta.auth_kinds[0].value if meta.auth_kinds else "oauth2"
        config = configs.get(provider_key)

        if not check_availability(provider_key, auth_kind, config):
            continue

        available.append(
            {
                "key": provider_key,
                "name": meta.display_name,
                "auth_kind": auth_kind,
                "credential_schema": build_credential_schema(meta),
            }
        )

    return available


# ---------------------------------------------------------------------------
# Non-OAuth credential connection flow
# ---------------------------------------------------------------------------


CredentialValidator = Callable[[str, dict[str, str]], Awaitable[None]]
ConnectionPostCreate = Callable[[Connection, AsyncSession], Awaitable[None]]


async def _default_caldav_validator(provider_key: str, credentials: dict[str, str]) -> None:
    """Validate CalDAV credentials with a lightweight PROPFIND request.

    Raises ``HTTPException(422)`` on invalid credentials or unreachable server.
    This is deliberately lenient for non-CalDAV providers — the connection is
    created optimistically and marked active.
    """
    if provider_key != "caldav":
        return  # other non-OAuth providers: trust credentials at creation time

    server_url = credentials.get("server_url", "").rstrip("/")
    username = credentials.get("username", "")
    password = credentials.get("password", "")
    if not server_url or not username or not password:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_credentials", "message": "Missing required credential fields"},
        )

    # Validate URL to prevent SSRF
    try:
        parsed = urllib.parse.urlparse(server_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("invalid scheme")
        hostname = parsed.hostname or ""
        if not hostname:
            raise ValueError("missing hostname")

        # Block well-known private hostnames that don't parse as IPs
        hostname_lower = hostname.lower()
        if hostname_lower in _BLOCKED_HOSTNAMES or any(
            hostname_lower.endswith(s) for s in _BLOCKED_SUFFIXES
        ):
            raise ValueError("blocked hostname")

        try:
            addr = ipaddress.ip_address(hostname)
            if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
                raise ValueError("private address")
        except ValueError as exc:
            if (
                "private address" in str(exc)
                or "blocked hostname" in str(exc)
                or "invalid scheme" in str(exc)
                or "missing hostname" in str(exc)
            ):
                raise HTTPException(
                    status_code=422,
                    detail={"code": "invalid_credentials", "message": "Invalid server URL"},
                ) from exc
            # hostname is a public domain name — resolve DNS and verify IPs
            loop = asyncio.get_event_loop()
            try:
                addr_infos = await loop.run_in_executor(
                    None, lambda: socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)
                )
            except OSError as dns_exc:
                raise HTTPException(
                    status_code=422,
                    detail={"code": "invalid_credentials", "message": "Invalid server URL"},
                ) from dns_exc
            for info in addr_infos:
                ip_str = info[4][0]
                try:
                    resolved = ipaddress.ip_address(ip_str)
                    if (
                        resolved.is_private
                        or resolved.is_loopback
                        or resolved.is_link_local
                        or resolved.is_reserved
                    ):
                        raise HTTPException(
                            status_code=422,
                            detail={"code": "invalid_credentials", "message": "Invalid server URL"},
                        )
                except ValueError:
                    # Reject invalid IP addresses (e.g., IPv6 with scope IDs)
                    raise HTTPException(
                        status_code=422,
                        detail={"code": "invalid_credentials", "message": "Invalid server URL"},
                    ) from None
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=422,
            detail={"code": "invalid_credentials", "message": "Invalid server URL"},
        ) from exc

    basic = base64.b64encode(f"{username}:{password}".encode()).decode()

    # Retry loop for transient failures (timeouts, connection errors, 502/503)
    attempts = 0
    while attempts <= _MAX_CALDAV_RETRIES:
        try:
            async with httpx.AsyncClient(timeout=10.0, follow_redirects=False) as client:
                response = await client.request(
                    "PROPFIND",
                    server_url,
                    headers={
                        "Authorization": f"Basic {basic}",
                        "Depth": "0",
                        "Content-Type": "application/xml",
                    },
                    content=b'<?xml version="1.0"?><propfind xmlns="DAV:"><prop><resourcetype/></prop></propfind>',
                )
            if response.status_code == 401:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "invalid_credentials",
                        "message": "Invalid username or password",
                    },
                )
            if response.status_code >= 400 and response.status_code not in (404, 405):
                # Check if this is a transient error that we should retry
                if (
                    response.status_code in _TRANSIENT_STATUS_CODES
                    and attempts < _MAX_CALDAV_RETRIES
                ):
                    attempts += 1
                    await asyncio.sleep(_CALDAV_RETRY_DELAY_SECONDS)
                    continue
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code": "invalid_credentials",
                        "message": "Could not connect to CalDAV server",
                    },
                )
            # Success
            break
        except HTTPException:
            raise
        except Exception as exc:
            # Transient network error — retry if we have attempts left
            if attempts < _MAX_CALDAV_RETRIES:
                attempts += 1
                await asyncio.sleep(_CALDAV_RETRY_DELAY_SECONDS)
                continue
            # All retries exhausted
            import logging

            logging.getLogger(__name__).warning(
                "CalDAV validation failed after %d attempts: %s", attempts + 1, exc
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "server_unreachable",
                    "message": "Could not reach CalDAV server. Please check the server URL and try again.",
                },
            ) from exc


def _build_stored_credential(
    provider_key: str, auth_kind: str, credentials: dict[str, str]
) -> StoredCredential:
    """Build a StoredCredential from raw form data."""
    if auth_kind == AuthKind.BASIC.value:
        basic_creds = BasicCredentials(
            username=credentials.get("username", ""),
            password=credentials.get("password", ""),
        )
        # Non-username/password fields go into provider_config
        extra = {k: v for k, v in credentials.items() if k not in ("username", "password")}
        return StoredCredential(
            provider_key=provider_key,
            auth_kind=AuthKind.BASIC,
            credentials=basic_creds,
            provider_config=extra or None,
        )
    raise ValueError(f"Unsupported auth_kind for credential connection: {auth_kind}")


async def create_credential_connection(
    *,
    provider_key: str,
    auth_kind: str,
    credentials: dict[str, str],
    external_id: str | None,
    session: AsyncSession,
    encryption: EncryptionService,
    persist_post_create: ConnectionPostCreate | None = None,
    validate: CredentialValidator | None = None,
) -> Connection:
    """Create and activate a connection using inline credentials (non-OAuth flow).

    Steps:
    1. Create connection record in PENDING state.
    2. Run optional credential validation.
    3. Store credentials encrypted in the credential store.
    4. Mark connection ACTIVE.
    """
    conn = Connection(
        id=uuid.uuid4(),
        provider_key=provider_key,
        external_id=external_id,
        status=ConnectionStatus.PENDING,
        provider_config=None,
    )
    session.add(conn)
    await session.flush()
    if persist_post_create is not None:
        await persist_post_create(conn, session)
    await session.commit()
    await session.refresh(conn)

    validator = validate if validate is not None else _default_caldav_validator
    try:
        await validator(provider_key, credentials)
    except HTTPException:
        # Validation failed — clean up the connection record
        await session.execute(
            update(Connection)
            .where(Connection.id == conn.id)
            .values(status=ConnectionStatus.REVOKED, status_reason="credential_validation_failed")
        )
        await session.commit()
        raise

    stored = _build_stored_credential(provider_key, auth_kind, credentials)
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    await cred_store.save_credentials(str(conn.id), stored)

    await session.execute(
        update(Connection)
        .where(Connection.id == conn.id)
        .values(status=ConnectionStatus.ACTIVE, updated_at=datetime.now(timezone.utc))
    )
    await session.commit()
    await session.refresh(conn)
    return conn


async def update_credential_connection(
    *,
    connection_id: uuid.UUID,
    credentials: dict[str, str],
    session: AsyncSession,
    encryption: EncryptionService,
    validate: CredentialValidator | None = None,
) -> Connection:
    """Update credentials on an existing connection (reconnect non-OAuth flow).

    Validates the new credentials and, on success, stores them and resets the
    connection to ACTIVE with refresh_failure_count = 0.
    """
    conn_result = await session.execute(select(Connection).where(Connection.id == connection_id))
    conn = conn_result.scalar_one_or_none()
    if conn is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "connection_not_found", "message": "Connection not found"},
        )

    auth_kind_str = "basic"  # CalDAV; extend when other non-OAuth providers added
    validator = validate if validate is not None else _default_caldav_validator
    await validator(conn.provider_key, credentials)

    stored = _build_stored_credential(conn.provider_key, auth_kind_str, credentials)
    cred_store = DatabaseCredentialStore(session=session, encryption=encryption)
    await cred_store.save_credentials(str(conn.id), stored)

    await session.execute(
        update(Connection)
        .where(Connection.id == connection_id)
        .values(
            status=ConnectionStatus.ACTIVE,
            status_reason=None,
            refresh_failure_count=0,
            updated_at=datetime.now(timezone.utc),
        )
    )
    await session.commit()
    await session.refresh(conn)
    return conn
