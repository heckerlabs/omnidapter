"""Unit tests for origin and redirect policy helpers."""

from __future__ import annotations

import pytest
from omnidapter_server.origin_policy import (
    build_cors_settings,
    is_host_allowed,
    parse_allowed_origin_domains,
    validate_redirect_url,
)


def test_parse_allowed_origin_domains_defaults_to_wildcard() -> None:
    assert parse_allowed_origin_domains("") == ["*"]


def test_is_host_allowed_supports_exact_and_wildcard() -> None:
    patterns = ["example.com", "*.preview.example.com"]

    assert is_host_allowed("example.com", patterns) is True
    assert is_host_allowed("abc.preview.example.com", patterns) is True
    assert is_host_allowed("preview.example.com", patterns) is False
    assert is_host_allowed("evil.com", patterns) is False


def test_build_cors_settings_wildcard_disables_credentials() -> None:
    allow_origins, allow_origin_regex, allow_credentials = build_cors_settings(["*"])

    assert allow_origins == ["*"]
    assert allow_origin_regex is None
    assert allow_credentials is False


def test_build_cors_settings_generates_regex_for_patterns() -> None:
    allow_origins, allow_origin_regex, allow_credentials = build_cors_settings(
        ["example.com", "*.preview.example.com"]
    )

    assert allow_origins == []
    assert allow_origin_regex is not None
    assert allow_credentials is True


def test_validate_redirect_url_accepts_allowed_https_url() -> None:
    validate_redirect_url(
        "https://app.example.com/callback",
        request_host="api.example.com",
        allowed_domain_patterns=["*.example.com"],
        env="production",
    )


def test_validate_redirect_url_rejects_disallowed_host() -> None:
    with pytest.raises(ValueError, match="host is not allowed"):
        validate_redirect_url(
            "https://evil.com/callback",
            request_host="api.example.com",
            allowed_domain_patterns=["*.example.com"],
            env="production",
        )


def test_validate_redirect_url_requires_https_outside_development() -> None:
    with pytest.raises(ValueError, match="must use https"):
        validate_redirect_url(
            "http://app.example.com/callback",
            request_host="api.example.com",
            allowed_domain_patterns=["*.example.com"],
            env="production",
        )


def test_validate_redirect_url_allows_http_for_localhost() -> None:
    validate_redirect_url(
        "http://localhost:3000/callback",
        request_host="localhost",
        allowed_domain_patterns=["localhost"],
        env="production",
    )
