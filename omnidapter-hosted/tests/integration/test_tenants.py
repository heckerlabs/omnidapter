"""Integration tests for tenant and dashboard management."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient
from omnidapter_hosted.config import get_hosted_settings
from omnidapter_hosted.models.membership import HostedMembership, MemberRole
from omnidapter_hosted.models.tenant import Tenant, TenantPlan
from omnidapter_hosted.models.user import HostedUser
from omnidapter_hosted.services.auth_flows import issue_jwt
from sqlalchemy.ext.asyncio import AsyncSession


@pytest_asyncio.fixture
async def authenticated_dashboard_client(
    client: AsyncClient, db_session: AsyncSession
) -> tuple[AsyncClient, HostedUser, Tenant]:
    """Provide a client authenticated with a dashboard JWT."""
    # Create user
    user = HostedUser(id=uuid.uuid4(), email=f"test-{uuid.uuid4()}@example.com", name="Test User")
    db_session.add(user)

    # Create tenant
    tenant = Tenant(id=uuid.uuid4(), name="Dashboard Tenant", plan=TenantPlan.FREE, is_active=True)
    db_session.add(tenant)

    # Create membership
    membership = HostedMembership(
        id=uuid.uuid4(), user_id=user.id, tenant_id=tenant.id, role=MemberRole.OWNER
    )
    db_session.add(membership)

    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(tenant)

    # Issue JWT
    settings = get_hosted_settings()
    token = issue_jwt(user.id, tenant.id, membership.role, settings)

    client.headers["Authorization"] = f"Bearer {token}"
    return client, user, tenant


@pytest.mark.asyncio
async def test_get_profile(authenticated_dashboard_client):
    client, user, _ = authenticated_dashboard_client
    response = await client.get("/v1/dashboard/profile")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["email"] == user.email
    assert data["name"] == user.name


@pytest.mark.asyncio
async def test_update_profile(authenticated_dashboard_client):
    client, user, _ = authenticated_dashboard_client
    new_name = "Updated Name"
    response = await client.patch("/v1/dashboard/profile", json={"name": new_name})
    assert response.status_code == 200
    assert response.json()["data"]["name"] == new_name


@pytest.mark.asyncio
async def test_get_tenant(authenticated_dashboard_client):
    client, _, tenant = authenticated_dashboard_client
    response = await client.get("/v1/dashboard/tenant")
    assert response.status_code == 200
    assert response.json()["data"]["name"] == tenant.name


@pytest.mark.asyncio
async def test_list_api_keys_dashboard(authenticated_dashboard_client):
    client, _, _ = authenticated_dashboard_client
    # Create an API key via dashboard
    response = await client.post("/v1/dashboard/api-keys", json={"name": "New Web Key"})
    assert response.status_code == 201
    assert "key" in response.json()["data"]
    assert response.json()["data"]["name"] == "New Web Key"

    # List them
    response = await client.get("/v1/dashboard/api-keys")
    assert response.status_code == 200
    assert len(response.json()["data"]) == 1
    assert response.json()["data"][0]["name"] == "New Web Key"
