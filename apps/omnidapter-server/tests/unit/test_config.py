"""Unit tests for settings normalization and local plaintext warnings."""

from __future__ import annotations

import logging

import omnidapter_server.config as config_module
import pytest
from omnidapter_server.config import Settings
from pydantic import ValidationError


def test_settings_defaults_to_dev() -> None:
    settings = Settings(omnidapter_encryption_key="dummy")
    assert settings.omnidapter_env == "DEV"
    assert settings.host == "0.0.0.0"
    assert settings.port == 8000


def test_settings_accept_custom_bind_host_and_port() -> None:
    settings = Settings.model_validate(
        {
            "omnidapter_encryption_key": "dummy",
            "host": "127.0.0.1",
            "port": "9001",
        }
    )

    assert settings.host == "127.0.0.1"
    assert settings.port == 9001


@pytest.mark.parametrize(
    ("raw_env", "expected"),
    [
        ("dev", "DEV"),
        ("development", "DEV"),
        ("local", "LOCAL"),
        ("prod", "PROD"),
        ("production", "PROD"),
    ],
)
def test_settings_normalize_env_values(raw_env: str, expected: str) -> None:
    settings = Settings(omnidapter_env=raw_env, omnidapter_encryption_key="dummy")
    assert settings.omnidapter_env == expected


def test_settings_reject_invalid_env() -> None:
    with pytest.raises(ValidationError, match="OMNIDAPTER_ENV must be one of DEV, LOCAL, PROD"):
        Settings(omnidapter_env="staging", omnidapter_encryption_key="dummy")


def test_settings_require_encryption_key_outside_local() -> None:
    with pytest.raises(
        ValidationError,
        match="OMNIDAPTER_ENCRYPTION_KEY is required unless OMNIDAPTER_ENV=LOCAL",
    ):
        Settings(omnidapter_env="PROD", omnidapter_encryption_key="")


def test_settings_ignore_extra_fields() -> None:
    settings = Settings.model_validate(
        {
            "omnidapter_encryption_key": "dummy",
            "unexpected_setting": "value",
        }
    )

    assert settings.omnidapter_encryption_key == "dummy"
    assert not hasattr(settings, "unexpected_setting")


def test_settings_warn_local_without_encryption_key(caplog: pytest.LogCaptureFixture) -> None:
    config_module._warned_local_plaintext_mode = False

    with caplog.at_level(logging.WARNING, logger="omnidapter_server.config"):
        settings = Settings(omnidapter_env="LOCAL", omnidapter_encryption_key="")

    assert settings.omnidapter_env == "LOCAL"
    assert "SECURITY WARNING" in caplog.text
    assert "plaintext" in caplog.text.lower()

    config_module._warned_local_plaintext_mode = False
