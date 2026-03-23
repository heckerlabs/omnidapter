"""Unit tests for OAuth router utility helpers."""

from __future__ import annotations

from omnidapter_server.routers.oauth import _append_query_params


def test_append_query_params_adds_and_encodes_values() -> None:
    url = _append_query_params(
        "https://app.example/callback",
        error="access denied",
        error_description="user denied",
        connection_id="abc123",
    )

    assert "error=access+denied" in url
    assert "error_description=user+denied" in url
    assert "connection_id=abc123" in url


def test_append_query_params_merges_existing_query_string() -> None:
    url = _append_query_params(
        "https://app.example/callback?foo=bar",
        connection_id="conn_1",
    )

    assert "foo=bar" in url
    assert "connection_id=conn_1" in url
