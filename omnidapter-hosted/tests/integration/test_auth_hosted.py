from __future__ import annotations

import unittest.mock

import pytest
from httpx import ASGITransport, AsyncClient
from omnidapter_hosted.config import HostedSettings
from omnidapter_hosted.main import create_app
from omnidapter_hosted.models.membership import HostedMembership
from omnidapter_hosted.models.tenant import Tenant
from omnidapter_hosted.models.user import HostedUser
from omnidapter_server.database import get_session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.asyncio


async def test_auth_me(dashboard_client: AsyncClient, test_user: HostedUser, test_tenant: Tenant):
    """Test GET /v1/auth/me (authenticated)."""
    response = await dashboard_client.get("/v1/auth/me")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["id"] == str(test_user.id)
    assert data["tenant"]["id"] == str(test_tenant.id)


async def test_auth_login_redirect(db_session: AsyncSession):
    """Test GET /v1/auth/login returns a WorkOS URL."""
    async def _get_session_override():
        yield db_session

    settings = HostedSettings()
    settings.workos_api_key = "test_api_key"
    settings.workos_client_id = "test_client_id"
    settings.omnidapter_base_url = "http://testserver"

    app = create_app(settings=settings)
    app.dependency_overrides[get_session] = _get_session_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        response = await ac.get("/v1/auth/login")
    
    assert response.status_code == 200
    assert "url" in response.json()
    assert "workos.com" in response.json()["url"]


@unittest.mock.patch("omnidapter_hosted.routers.auth.AsyncWorkOSClient")
async def test_auth_callback_provisioning(
    mock_workos_class, 
    db_session: AsyncSession
):
    """Test GET /v1/auth/callback provisions a new user/tenant."""
    mock_workos = mock_workos_class.return_value
    
    # Mock WorkOS user response
    mock_user = unittest.mock.MagicMock()
    mock_user.id = "workos_user_123"
    mock_user.email = "newuser@example.com"
    mock_user.first_name = "New"
    mock_user.last_name = "User"
    
    mock_auth_response = unittest.mock.MagicMock()
    mock_auth_response.user = mock_user
    
    # Use AsyncMock for the async method
    mock_workos.user_management.authenticate_with_code = unittest.mock.AsyncMock(return_value=mock_auth_response)

    async def _get_session_override():
        yield db_session

    settings = HostedSettings()
    settings.workos_api_key = "test_api_key"
    settings.workos_client_id = "test_client_id"
    settings.jwt_secret = "a" * 32

    app = create_app(settings=settings)
    app.dependency_overrides[get_session] = _get_session_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        response = await ac.get("/v1/auth/callback?code=test_code")
        
    assert response.status_code == 200
    data = response.json()["data"]
    assert "access_token" in data
    assert data["user"]["email"] == "newuser@example.com"
    
    # Verify provisioning in DB
    result = await db_session.execute(
        select(HostedUser).where(HostedUser.email == "newuser@example.com")
    )
    user = result.scalar_one()
    assert user.workos_user_id == "workos_user_123"
    
    # Verify tenant/membership
    result = await db_session.execute(
        select(HostedMembership).where(HostedMembership.user_id == user.id)
    )
    membership = result.scalar_one()
    assert membership.tenant_id is not None


@unittest.mock.patch("omnidapter_hosted.routers.auth.AsyncWorkOSClient")
async def test_auth_callback_existing_user(
    mock_workos_class, 
    db_session: AsyncSession,
    test_user: HostedUser,
    test_tenant: Tenant,
    test_membership: HostedMembership
):
    """Test GET /v1/auth/callback with an existing user (re-login)."""
    mock_workos = mock_workos_class.return_value
    
    # Update user with workos_id for lookup
    test_user.workos_user_id = "existing_workos_id"
    await db_session.flush()

    mock_user = unittest.mock.MagicMock()
    mock_user.id = "existing_workos_id"
    mock_user.email = test_user.email
    mock_user.first_name = "Test"
    mock_user.last_name = "User"
    
    mock_auth_response = unittest.mock.MagicMock()
    mock_auth_response.user = mock_user
    mock_workos.user_management.authenticate_with_code = unittest.mock.AsyncMock(return_value=mock_auth_response)

    async def _get_session_override():
        yield db_session

    settings = HostedSettings()
    settings.workos_api_key = "test_api_key"
    settings.workos_client_id = "test_client_id"
    settings.jwt_secret = "a" * 32

    app = create_app(settings=settings)
    app.dependency_overrides[get_session] = _get_session_override

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
        response = await ac.get("/v1/auth/callback?code=test_code")
        
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["user"]["id"] == str(test_user.id)
    assert data["tenant"]["id"] == str(test_tenant.id)
