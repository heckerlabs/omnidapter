"""Application configuration via environment variables."""

from __future__ import annotations

import logging

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_ENV_ALIASES = {
    "DEVELOPMENT": "DEV",
    "PRODUCTION": "PROD",
}
_VALID_ENVS = frozenset({"DEV", "LOCAL", "PROD"})
_warned_local_plaintext_mode = False


def normalize_omnidapter_env(value: str | None) -> str:
    normalized = (value or "DEV").strip().upper()
    normalized = _ENV_ALIASES.get(normalized, normalized)
    if normalized not in _VALID_ENVS:
        raise ValueError("OMNIDAPTER_ENV must be one of DEV, LOCAL, PROD")
    return normalized


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
    host: str = "0.0.0.0"
    port: int = 8000
    omnidapter_base_url: str = "http://localhost:8000"
    omnidapter_env: str = "DEV"
    omnidapter_allowed_origin_domains: str = "*"

    # Seed an initial API key on startup (set to a raw key like "omni_live_...")
    # If set and no matching prefix exists, the key is created automatically.
    omnidapter_initial_api_key: str = ""

    @field_validator("omnidapter_env", mode="before")
    @classmethod
    def _normalize_env(cls, value: str | None) -> str:
        return normalize_omnidapter_env(value)

    @model_validator(mode="after")
    def _warn_local_plaintext_mode(self) -> Settings:
        global _warned_local_plaintext_mode

        if self.omnidapter_env != "LOCAL" and not self.omnidapter_encryption_key.strip():
            raise ValueError("OMNIDAPTER_ENCRYPTION_KEY is required unless OMNIDAPTER_ENV=LOCAL")

        if (
            self.omnidapter_env == "LOCAL"
            and not self.omnidapter_encryption_key.strip()
            and not _warned_local_plaintext_mode
        ):
            logger.warning(
                "!!! SECURITY WARNING !!! OMNIDAPTER_ENCRYPTION_KEY is not set and "
                "OMNIDAPTER_ENV=LOCAL. Sensitive credentials will be stored in plaintext. "
                "Use LOCAL only for local development."
            )
            _warned_local_plaintext_mode = True

        return self

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
