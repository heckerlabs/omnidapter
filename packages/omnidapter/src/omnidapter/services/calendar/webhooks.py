"""
Calendar webhook helper utilities.

These helpers assist apps in building webhook handlers. Full webhook
management (persistence, delivery, retries) is the app's responsibility.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class WebhookParseResult(BaseModel):
    """Parsed webhook notification from a provider."""
    provider_key: str
    event_type: str | None = None
    calendar_id: str | None = None
    resource_id: str | None = None
    channel_id: str | None = None
    raw: dict[str, Any] = {}
