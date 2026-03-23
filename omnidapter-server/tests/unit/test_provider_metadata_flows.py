"""Unit tests for provider metadata shared flows."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from omnidapter_server.services.provider_metadata_flows import (
    get_provider_flow,
    list_providers_flow,
)


def _meta() -> SimpleNamespace:
    return SimpleNamespace(
        provider_key="google",
        display_name="Google",
        services=[SimpleNamespace(value="calendar")],
        auth_kinds=[SimpleNamespace(value="oauth2")],
        capabilities={"events": True},
        connection_config_fields=[
            SimpleNamespace(name="x", description="desc", required=False),
        ],
    )


def test_list_providers_flow() -> None:
    omni = SimpleNamespace(
        list_providers=lambda: ["google"],
        describe_provider=lambda _: _meta(),
    )
    result = list_providers_flow(omni)  # type: ignore[arg-type]
    assert result[0]["provider_key"] == "google"


def test_get_provider_flow_404() -> None:
    omni = SimpleNamespace(describe_provider=lambda _: (_ for _ in ()).throw(KeyError("x")))
    with pytest.raises(HTTPException) as exc_info:
        get_provider_flow(omni, "missing")  # type: ignore[arg-type]
    assert exc_info.value.status_code == 404
