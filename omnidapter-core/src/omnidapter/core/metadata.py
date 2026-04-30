"""
Provider metadata models for introspection.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ServiceKind(str, Enum):
    """Top-level service categories."""

    CALENDAR = "calendar"
    BOOKING = "booking"
    CRM = "crm"


class AuthKind(str, Enum):
    """Supported authentication kinds."""

    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BASIC = "basic"


class OAuthScopeGroup(BaseModel):
    """A named group of OAuth scopes."""

    name: str
    description: str
    scopes: list[str]
    service_kind: ServiceKind | None = None  # None = always included; non-None = service-scoped


class OAuthMetadata(BaseModel):
    """OAuth-specific metadata for a provider."""

    authorization_endpoint: str
    token_endpoint: str
    supports_pkce: bool = False
    scope_groups: list[OAuthScopeGroup] = []
    default_scopes: list[str] = []


class ConnectionConfigField(BaseModel):
    """Describes a required/optional field for provider-specific connection config."""

    name: str
    label: str | None = None  # display label; falls back to name title-cased if None
    description: str = ""  # help text shown below the field
    type: str = "text"  # text / password / url / email / select
    required: bool = True
    placeholder: str | None = None
    example: str | None = None  # kept for SDK documentation
    options: list[dict[str, str]] | None = None  # [{"value": ..., "label": ...}] for select


class ProviderMetadata(BaseModel):
    """Full provider metadata for introspection."""

    provider_key: str
    display_name: str
    services: list[ServiceKind]
    auth_kinds: list[AuthKind]
    oauth: OAuthMetadata | None = None
    capabilities: dict[str, list[str]] = {}  # service_kind -> capability names
    connection_config_fields: list[ConnectionConfigField] = []
    extra: dict[str, Any] = {}
