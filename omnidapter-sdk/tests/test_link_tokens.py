"""Integration tests for LinkTokensApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateLinkTokenRequest

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_create_link_token_minimal(sdk_client: OmnidapterClient):
    body = sdk_client.link_tokens.create_link_token(CreateLinkTokenRequest())
    assert "data" in body
    token_data = body["data"]
    assert token_data["token"].startswith("lt_")
    assert "expires_at" in token_data
    assert "connect_url" in token_data


def test_create_link_token_with_options(sdk_client: OmnidapterClient):
    body = sdk_client.link_tokens.create_link_token(
        CreateLinkTokenRequest(
            end_user_id="user_123",
            allowed_providers=["google"],
            ttl_seconds=300,
        )
    )
    assert body["data"]["token"].startswith("lt_")


def test_create_link_token_with_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.link_tokens.create_link_token(
            CreateLinkTokenRequest(connection_id=NIL_UUID)
        )
    assert exc_info.value.status == 404


def test_create_link_token_ttl_too_short_rejected(sdk_client: OmnidapterClient):
    # The SDK model validates ttl_seconds >= 60 client-side, so a ValidationError
    # is raised before the request is sent.
    from pydantic import ValidationError
    with pytest.raises((ApiException, ValidationError)):
        sdk_client.link_tokens.create_link_token(
            CreateLinkTokenRequest(ttl_seconds=10)
        )
