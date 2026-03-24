"""Unit tests for provider config shared flows."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from omnidapter_server.schemas.provider_config import UpsertProviderConfigRequest
from omnidapter_server.services.provider_config_flows import (
    delete_provider_config_flow,
    get_provider_config_flow,
    list_provider_configs_flow,
    upsert_provider_config_flow,
)


class _Cfg:
    def __init__(self) -> None:
        self.id = uuid.uuid4()
        self.provider_key = "google"
        self.auth_kind = "oauth2"
        self.scopes = ["a"]
        self.is_fallback = False
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = datetime.now(timezone.utc)
        self.client_id_encrypted = ""
        self.client_secret_encrypted = ""


@pytest.mark.asyncio
async def test_list_provider_configs_flow_maps_models() -> None:
    rows = [_Cfg()]
    result = await list_provider_configs_flow(
        session=AsyncMock(),
        list_configs=AsyncMock(return_value=rows),
    )
    assert result[0].provider_key == "google"


@pytest.mark.asyncio
async def test_get_provider_config_flow_404() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await get_provider_config_flow(
            provider_key="google",
            session=AsyncMock(),
            load_config=AsyncMock(return_value=None),
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_upsert_provider_config_flow_create() -> None:
    session = AsyncMock()
    session.add = lambda _: None
    session.commit = AsyncMock()
    session.refresh = AsyncMock()

    encryption = MagicMock()
    encryption.encrypt.side_effect = ["enc-id", "enc-secret"]

    created = _Cfg()
    response = await upsert_provider_config_flow(
        provider_key="google",
        body=UpsertProviderConfigRequest(client_id="id", client_secret="secret", scopes=["a"]),
        encryption=encryption,
        session=session,
        load_config=AsyncMock(return_value=None),
        create_config=lambda *_: created,
    )

    assert response.provider_key == "google"
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_provider_config_flow_calls_delete() -> None:
    delete_config = AsyncMock()
    session = AsyncMock()
    session.commit = AsyncMock()

    await delete_provider_config_flow(
        provider_key="google",
        session=session,
        load_config=AsyncMock(return_value=_Cfg()),
        delete_config=delete_config,
    )

    delete_config.assert_awaited_once()
    session.commit.assert_awaited_once()
