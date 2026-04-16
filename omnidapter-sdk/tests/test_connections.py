"""Integration tests for ConnectionsApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException
from omnidapter_sdk.models import CreateConnectionRequest

NIL_UUID = "00000000-0000-0000-0000-000000000000"


def test_list_connections_empty(sdk_client: OmnidapterClient):
    body = sdk_client.connections.list_connections()
    assert "data" in body
    assert body["data"] == []
    assert body["meta"]["pagination"]["total"] == 0


def test_list_connections_with_filters(sdk_client: OmnidapterClient):
    body = sdk_client.connections.list_connections(provider="google", status="active")
    assert body["data"] == []


def test_get_connection_unknown_id_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.connections.get_connection(NIL_UUID)
    assert exc_info.value.status == 404


def test_create_connection_unknown_provider_raises_error(sdk_client: OmnidapterClient):
    # CreateConnectionRequest uses `provider` (not `provider_key`) and requires `redirect_url`.
    # The server creates the connection then tries to build the OAuth URL; with no providers
    # configured it returns 400 (provider not found in registry), not 404.
    with pytest.raises(ApiException) as exc_info:
        sdk_client.connections.create_connection(
            CreateConnectionRequest(
                provider="nonexistent_provider_xyz",
                redirect_url="https://example.com/callback",
            )
        )
    assert exc_info.value.status in (400, 404)


def test_delete_connection_unknown_id_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.connections.delete_connection(NIL_UUID)
    assert exc_info.value.status == 404
