"""Hosted application configuration."""

from __future__ import annotations

from omnidapter_server.config import Settings


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
    # Generate with: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: str = ""
    # Dashboard session TTL in seconds (default 24 hours)
    jwt_ttl_seconds: int = 86400

    # Link token TTL in seconds (default 30 minutes)
    link_token_ttl_seconds: int = 1800

    # Rate limiting per plan (requests per 60s window)
    hosted_rate_limit_free: int = 60
    hosted_rate_limit_paid: int = 600
    hosted_rate_limit_redis_url: str = ""

    # Free tier call limit per tenant per month (calendar API calls)
    hosted_free_tier_calls: int = 1000


_settings: HostedSettings | None = None


def get_hosted_settings() -> HostedSettings:
    global _settings
    if _settings is None:
        _settings = HostedSettings()
    return _settings
