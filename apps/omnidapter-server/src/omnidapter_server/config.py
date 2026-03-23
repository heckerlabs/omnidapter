"""Application configuration via environment variables."""

from __future__ import annotations

import logging
from typing import Literal

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)

_ENV_ALIASES = {
    "DEVELOPMENT": "DEV",
    "PRODUCTION": "PROD",
}
_VALID_ENVS = frozenset({"DEV", "LOCAL", "PROD"})
_VALID_AUTH_MODES = frozenset({"required", "disabled"})
_warned_local_plaintext_mode = False


def normalize_omnidapter_env(value: str | None) -> str:
    normalized = (value or "DEV").strip().upper()
    normalized = _ENV_ALIASES.get(normalized, normalized)
    if normalized not in _VALID_ENVS:
        raise ValueError("OMNIDAPTER_ENV must be one of DEV, LOCAL, PROD")
    return normalized


def normalize_omnidapter_auth_mode(value: str | None) -> str:
    normalized = (value or "required").strip().lower()
    if normalized not in _VALID_AUTH_MODES:
        raise ValueError("OMNIDAPTER_AUTH_MODE must be one of required, disabled")
    return normalized


class Settings(BaseSettings):
    """All operational parameters from environment variables."""

    # Database
    omnidapter_database_url: str = "postgresql+asyncpg://localhost/omnidapter"

    # Encryption
    omnidapter_encryption_key: str = ""
    omnidapter_encryption_key_previous: str = ""  # for key rotation

    # OAuth state store — Redis preferred, in-memory fallback with warning
    omnidapter_oauth_state_redis_url: str = ""

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
    omnidapter_auth_mode: Literal["required", "disabled"] = "required"
    omnidapter_allowed_origin_domains: str = "*"

    # Managed API key for server authentication.
    omnidapter_api_key: str = ""

    @field_validator("omnidapter_env", mode="before")
    @classmethod
    def _normalize_env(cls, value: str | None) -> str:
        return normalize_omnidapter_env(value)

    @field_validator("omnidapter_auth_mode", mode="before")
    @classmethod
    def _normalize_auth_mode(cls, value: str | None) -> str:
        return normalize_omnidapter_auth_mode(value)

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

        if self.omnidapter_auth_mode == "disabled" and self.omnidapter_env != "LOCAL":
            raise ValueError(
                "OMNIDAPTER_AUTH_MODE=disabled is only allowed when OMNIDAPTER_ENV=LOCAL"
            )

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
