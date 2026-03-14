"""Integration tests for connection health tracking."""

from __future__ import annotations

import uuid

import pytest
from omnidapter_api.models.connection import Connection, ConnectionStatus
from omnidapter_api.models.organization import Organization
from omnidapter_api.services.connection_health import (
    record_refresh_failure,
    record_refresh_success,
    transition_to_active,
)
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_refresh_failure_increments_count_in_db(
    session: AsyncSession,
    org: Organization,
):
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="health_test",
        status=ConnectionStatus.ACTIVE,
        refresh_failure_count=0,
    )
    session.add(conn)
    await session.flush()

    await record_refresh_failure(conn.id, session, reauth_threshold=3)
    await session.refresh(conn)
    assert conn.refresh_failure_count == 1
    assert conn.status == ConnectionStatus.ACTIVE


@pytest.mark.asyncio
async def test_refresh_failures_reach_threshold(
    session: AsyncSession,
    org: Organization,
):
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="threshold_test",
        status=ConnectionStatus.ACTIVE,
        refresh_failure_count=2,
    )
    session.add(conn)
    await session.flush()

    status = await record_refresh_failure(conn.id, session, reauth_threshold=3)
    assert status == ConnectionStatus.NEEDS_REAUTH

    await session.refresh(conn)
    assert conn.status == ConnectionStatus.NEEDS_REAUTH
    assert conn.refresh_failure_count == 3
    assert conn.last_refresh_failure_at is not None


@pytest.mark.asyncio
async def test_refresh_success_resets_count(
    session: AsyncSession,
    org: Organization,
):
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="reset_test",
        status=ConnectionStatus.ACTIVE,
        refresh_failure_count=2,
    )
    session.add(conn)
    await session.flush()

    await record_refresh_success(conn.id, session)
    await session.refresh(conn)
    assert conn.refresh_failure_count == 0
    assert conn.last_refresh_failure_at is None


@pytest.mark.asyncio
async def test_transition_to_active_sets_scopes(
    session: AsyncSession,
    org: Organization,
):
    conn = Connection(
        id=uuid.uuid4(),
        organization_id=org.id,
        provider_key="google",
        external_id="active_test",
        status=ConnectionStatus.PENDING,
    )
    session.add(conn)
    await session.flush()

    scopes = ["https://www.googleapis.com/auth/calendar"]
    await transition_to_active(
        conn.id, session, granted_scopes=scopes, provider_account_id="user@gmail.com"
    )

    await session.refresh(conn)
    assert conn.status == ConnectionStatus.ACTIVE
    assert conn.granted_scopes == scopes
    assert conn.provider_account_id == "user@gmail.com"
    assert conn.refresh_failure_count == 0
