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

    # OAuth state store — priority: Redis > DB > in-memory (warns on in-memory)
    omnidapter_oauth_state_redis_url: str = ""
    omnidapter_oauth_state_db_url: str = ""  # defaults to omnidapter_database_url if empty

    # Fallback OAuth apps
    omnidapter_google_client_id: str = ""
    omnidapter_google_client_secret: str = ""
    omnidapter_microsoft_client_id: str = ""
    omnidapter_microsoft_client_secret: str = ""
    omnidapter_zoho_client_id: str = ""
    omnidapter_zoho_client_secret: str = ""

    # Connection limits when using fallback (server-owned) OAuth app
    omnidapter_fallback_connection_limit: int = 5

    # Reauth threshold: mark connection needs_reauth after this many consecutive refresh failures
    omnidapter_reauth_threshold: int = 3

    # App
    omnidapter_base_url: str = "http://localhost:8000"
    omnidapter_env: str = "development"
    omnidapter_allowed_origin_domains: str = "*"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
