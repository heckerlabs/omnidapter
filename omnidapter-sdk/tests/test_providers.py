"""Integration tests for ProvidersApi."""

import pytest
from omnidapter_sdk.client import OmnidapterClient
from omnidapter_sdk.exceptions import ApiException


def test_list_providers_returns_envelope(sdk_client: OmnidapterClient):
    body = sdk_client.providers.list_providers()
    assert isinstance(body.data, list)
    assert body.meta is not None


def test_get_unknown_provider_raises_404(sdk_client: OmnidapterClient):
    with pytest.raises(ApiException) as exc_info:
        sdk_client.providers.get_provider("nonexistent_provider_xyz")
    assert exc_info.value.status == 404
