from __future__ import annotations

from pydantic import BaseModel, Field

from omnidapter.auth.kinds import AuthKind
from omnidapter.services.calendar.capabilities import CalendarCapability


class OAuthSupport(BaseModel):
    supported: bool
    scope_groups: dict[str, list[str]] = Field(default_factory=dict)


class ProviderMetadata(BaseModel):
    key: str
    display_name: str
    services: list[str]
    auth_kinds: list[AuthKind]
    capabilities: dict[str, list[CalendarCapability]] = Field(default_factory=dict)
    oauth: OAuthSupport = Field(default_factory=lambda: OAuthSupport(supported=False))
    config_requirements: list[str] = Field(default_factory=list)
