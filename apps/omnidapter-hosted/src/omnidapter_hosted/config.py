"""Hosted application configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class HostedSettings(BaseSettings):
    """Hosted-specific configuration on top of server settings."""

    # Inherits server DB + encryption config via env vars

    # Stripe (billing)
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # WorkOS (user auth)
    workos_api_key: str = ""
    workos_client_id: str = ""

    # Rate limiting per plan (requests per 60s window)
    hosted_rate_limit_free: int = 60
    hosted_rate_limit_paid: int = 600
    hosted_rate_limit_redis_url: str = ""

    # Free tier call limit per tenant per month (calendar API calls)
    hosted_free_tier_calls: int = 1000

    # Reuse server database URL
    omnidapter_database_url: str = "postgresql+asyncpg://localhost/omnidapter"
    omnidapter_encryption_key: str = ""
    omnidapter_encryption_key_previous: str = ""
    omnidapter_oauth_state_redis_url: str = ""
    omnidapter_base_url: str = "http://localhost:8000"
    omnidapter_env: str = "development"
    omnidapter_allowed_origin_domains: str = "*"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


_settings: HostedSettings | None = None


def get_hosted_settings() -> HostedSettings:
    global _settings
    if _settings is None:
        _settings = HostedSettings()
    return _settings
