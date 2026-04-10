"""Unit tests for server provider registry assembly."""

from __future__ import annotations

import pytest
from omnidapter_server.config import Settings
from omnidapter_server.provider_registry import build_provider_registry


@pytest.fixture(autouse=True)
def clear_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in [
        "GOOGLE_CLIENT_ID",
        "GOOGLE_CLIENT_SECRET",
        "MICROSOFT_CLIENT_ID",
        "MICROSOFT_CLIENT_SECRET",
        "ZOHO_CLIENT_ID",
        "ZOHO_CLIENT_SECRET",
        "OMNIDAPTER_APPLE_ENABLED",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_build_provider_registry_registers_fallback_credentials() -> None:
    settings = Settings(
        omnidapter_google_client_id="fallback-google-id",
        omnidapter_google_client_secret="fallback-google-secret",
    )

    registry = build_provider_registry(settings)
    oauth = registry.get("google").get_oauth_config()

    assert oauth is not None
    assert oauth.client_id == "fallback-google-id"
    assert oauth.client_secret == "fallback-google-secret"
