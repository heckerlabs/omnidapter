"""Unit tests for common schemas and bootstrap script."""

from __future__ import annotations

import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from omnidapter_server.schemas.common import (
    ApiResponse,
    ErrorDetail,
    ErrorResponse,
    ListMeta,
    ListResponse,
    PaginationMeta,
    RequestMeta,
)
from omnidapter_server.scripts.bootstrap import create_api_key, main


class _SessionContext:
    def __init__(self, session: AsyncMock) -> None:
        self._session = session

    async def __aenter__(self) -> AsyncMock:
        return self._session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def test_common_response_models() -> None:
    pagination = PaginationMeta(total=10, limit=5, offset=0, has_more=True)
    list_meta = ListMeta(request_id="req_1", pagination=pagination)
    list_response = ListResponse(data=["a", "b"], meta=list_meta)
    single = ApiResponse(data={"ok": True}, meta=RequestMeta(request_id="req_2"))
    err = ErrorResponse(
        error=ErrorDetail(code="bad_request", message="nope", details={"field": "name"}),
        meta=RequestMeta(request_id="req_3"),
    )

    assert list_response.meta.pagination.total == 10
    assert single.data["ok"] is True
    assert err.error.code == "bad_request"


@pytest.mark.asyncio
async def test_create_api_key_bootstrap_flow() -> None:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()

    def _factory() -> _SessionContext:
        return _SessionContext(session)

    engine = MagicMock()
    engine.dispose = AsyncMock()

    with (
        patch(
            "omnidapter_server.config.get_settings",
            return_value=SimpleNamespace(
                omnidapter_database_url="postgresql+asyncpg://localhost/db"
            ),
        ),
        patch(
            "sqlalchemy.ext.asyncio.create_async_engine",
            return_value=engine,
        ),
        patch(
            "sqlalchemy.ext.asyncio.async_sessionmaker",
            return_value=_factory,
        ),
        patch(
            "omnidapter_server.services.auth.generate_api_key",
            return_value=("omni_live_raw", "hash", "omni_live_ra"),
        ),
        patch("builtins.print") as print_mock,
    ):
        await create_api_key("production", False)

    session.add.assert_called_once()
    session.commit.assert_awaited_once()
    engine.dispose.assert_awaited_once()
    assert print_mock.call_count == 3


def test_bootstrap_main_parses_args_and_runs_asyncio() -> None:
    with (
        patch("omnidapter_server.scripts.bootstrap.asyncio.run") as run_mock,
        patch(
            "sys.argv",
            ["omnidapter-bootstrap", "--name", "prod", "--test"],
        ),
    ):
        main()

    assert run_mock.call_count == 1
    coro = run_mock.call_args.args[0]
    assert inspect.iscoroutine(coro)
    coro.close()
