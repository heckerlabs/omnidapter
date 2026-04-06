"""Hosted application configuration."""

from __future__ import annotations

from omnidapter_server.config import Settings
from pydantic import model_validator


class HostedSettings(Settings):
    """Hosted-specific configuration extending server settings."""

    # Inherits server DB + encryption config via env vars

    # Stripe (billing)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # WorkOS (user auth)
    workos_api_key: str = ""
    workos_client_id: str = ""

    # JWT signing secret for dashboard sessions (HS256).
    # Auto-generated on startup if empty, but will rotate on each restart — set explicitly in prod.
    # Generate with: `openssl rand -base64 32`
    hosted_jwt_secret: str = ""
    # Dashboard session TTL in seconds (default 24 hours)
    hosted_jwt_ttl_seconds: int = 86400

    # Connection limit when using fallback (hosted-owned) OAuth app
    hosted_fallback_connection_limit: int = 5

    # Rate limiting per plan (requests per 60s window)
    hosted_rate_limit_free: int = 60
    hosted_rate_limit_paid: int = 600
    hosted_rate_limit_redis_url: str = ""

    # Free tier call limit per tenant per month (calendar API calls)
    hosted_free_tier_calls: int = 1000

    @model_validator(mode="after")
    def _require_jwt_secret_in_prod(self) -> HostedSettings:
        """Require HOSTED_JWT_SECRET to be set in production to prevent session invalidation on restart."""
        if self.omnidapter_env == "PROD" and not self.hosted_jwt_secret.strip():
            raise ValueError("HOSTED_JWT_SECRET is required when OMNIDAPTER_ENV=PROD")
        return self


_settings: HostedSettings | None = None


def get_hosted_settings() -> HostedSettings:
    global _settings
    if _settings is None:
        _settings = HostedSettings()
    return _settings
