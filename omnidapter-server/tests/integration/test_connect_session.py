"""Integration tests for POST /connect/session — bootstrap token exchange."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from omnidapter_server.models.link_token import LinkToken
from omnidapter_server.services.link_tokens import generate_link_token
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def public_client(postgres_url: str, session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """An unauthenticated client (no API key) for testing /connect/* endpoints."""
    from omnidapter_server.config import Settings
    from omnidapter_server.database import get_session
    from omnidapter_server.main import create_app

    test_settings = Settings(
        omnidapter_database_url=postgres_url,
        omnidapter_encryption_key="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
        omnidapter_env="DEV",
    )
    app = create_app(settings=test_settings)

    async def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session

    async with AsyncClient(transport=ASGITransport(app), base_url="http://testserver") as c:
        yield c

    app.dependency_overrides.clear()


async def _create_link_token(session: AsyncSession, *, ttl_seconds: int = 3600) -> str:
    """Insert a fresh LinkToken and return the raw lt_* string."""
    raw, token_hash, token_prefix = generate_link_token()
    lt = LinkToken(
        id=uuid.uuid4(),
        token_hash=token_hash,
        token_prefix=token_prefix,
        end_user_id="test_user",
        allowed_providers=None,
        redirect_uri="https://example.com/callback",
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
        is_active=True,
    )
    session.add(lt)
    await session.flush()
    return raw


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_connect_session_returns_cs_token(
    public_client: AsyncClient,
    session: AsyncSession,
):
    """Valid lt_* bootstrap token is exchanged for a cs_* session token."""
    raw_lt = await _create_link_token(session)

    response = await public_client.post("/connect/session", json={"token": raw_lt})
    assert response.status_code == 200

    body = response.json()
    data = body["data"]
    assert data["session_token"].startswith("cs_")
    assert data["expires_in"] > 0
    assert "meta" in body


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_connect_session_consumes_bootstrap_token(
    public_client: AsyncClient,
    session: AsyncSession,
):
    """The bootstrap token can only be exchanged once — second call returns token_already_used."""
    raw_lt = await _create_link_token(session)

    r1 = await public_client.post("/connect/session", json={"token": raw_lt})
    assert r1.status_code == 200

    r2 = await public_client.post("/connect/session", json={"token": raw_lt})
    assert r2.status_code == 401
    assert r2.json()["detail"]["code"] == "token_already_used"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_connect_session_rejects_invalid_token(public_client: AsyncClient):
    """Garbage token returns 401 session_expired."""
    response = await public_client.post("/connect/session", json={"token": "lt_notreal"})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_expired"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_connect_session_rejects_expired_token(
    public_client: AsyncClient,
    session: AsyncSession,
):
    """A link token past its expires_at is rejected."""
    raw_lt = await _create_link_token(session, ttl_seconds=-1)  # already expired

    response = await public_client.post("/connect/session", json={"token": raw_lt})
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "session_expired"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_raw_lt_token_rejected_on_connect_providers(
    public_client: AsyncClient,
    session: AsyncSession,
):
    """An unconsumed lt_* token is rejected on /connect/providers (cs_* required)."""
    raw_lt = await _create_link_token(session)

    response = await public_client.get(
        "/connect/providers",
        headers={"Authorization": f"Bearer {raw_lt}"},
    )
    assert response.status_code == 401
    assert response.json()["detail"]["code"] in ("unauthenticated", "session_expired")


@pytest.mark.asyncio
@pytest.mark.integration
async def test_post_connect_session_returns_redirect_uri(
    public_client: AsyncClient,
    session: AsyncSession,
):
    """Session exchange response includes redirect_uri from the link token."""
    raw_lt = await _create_link_token(session)

    response = await public_client.post("/connect/session", json={"token": raw_lt})
    assert response.status_code == 200

    data = response.json()["data"]
    assert data["redirect_uri"] == "https://example.com/callback"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cs_token_accepted_on_connect_providers(
    public_client: AsyncClient,
    session: AsyncSession,
):
    """A cs_* session token (from exchange) is accepted on /connect/providers."""
    raw_lt = await _create_link_token(session)

    exchange = await public_client.post("/connect/session", json={"token": raw_lt})
    assert exchange.status_code == 200
    cs_token = exchange.json()["data"]["session_token"]

    response = await public_client.get(
        "/connect/providers",
        headers={"Authorization": f"Bearer {cs_token}"},
    )
    assert response.status_code == 200
    assert "providers" in response.json()
