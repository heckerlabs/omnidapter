"""Application configuration via environment variables."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All operational parameters from environment variables."""

    # Database
    omnidapter_database_url: str = "postgresql+asyncpg://localhost/omnidapter"

    # Encryption
    omnidapter_encryption_key: str = ""
    omnidapter_encryption_key_previous: str = ""  # for key rotation

    # Fallback OAuth apps
    omnidapter_google_client_id: str = ""
    omnidapter_google_client_secret: str = ""
    omnidapter_microsoft_client_id: str = ""
    omnidapter_microsoft_client_secret: str = ""
    omnidapter_zoho_client_id: str = ""
    omnidapter_zoho_client_secret: str = ""

    # Limits
    omnidapter_fallback_connection_limit: int = 5
    omnidapter_free_tier_calls: int = 1000
    omnidapter_reauth_threshold: int = 3
    omnidapter_rate_limit_free: int = 60
    omnidapter_rate_limit_paid: int = 300

    # Stripe
    stripe_secret_key: str = ""
    stripe_webhook_secret: str = ""

    # WorkOS (future dashboard auth)
    workos_client_id: str = ""
    workos_api_key: str = ""

    # App
    omnidapter_base_url: str = "https://omnidapter.heckerlabs.ai"
    omnidapter_env: str = "development"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
