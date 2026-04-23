"""Integration tests for LinkTokensApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateLinkTokenRequest

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_create_link_token_minimal(sdk_client: OmnidapterClient):
    body = sdk_client.link_tokens.create_link_token(CreateLinkTokenRequest())
    assert body.data.token.startswith("lt_")
    assert body.data.expires_at is not None
    assert body.data.connect_url is not None


def test_create_link_token_with_options(sdk_client: OmnidapterClient):
    body = sdk_client.link_tokens.create_link_token(
        CreateLinkTokenRequest(
            end_user_id="user_123",
            allowed_providers=["google"],
            ttl_seconds=300,
        )
    )
    assert body.data.token.startswith("lt_")


def test_create_link_token_with_unknown_connection_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.link_tokens.create_link_token(CreateLinkTokenRequest(connection_id=NIL_UUID))
    assert exc_info.value.status == 404


def test_create_link_token_ttl_too_short_rejected(sdk_client: OmnidapterClient):
    from pydantic import ValidationError

    with pytest.raises((ApiException, ValidationError)):
        sdk_client.link_tokens.create_link_token(CreateLinkTokenRequest(ttl_seconds=10))
