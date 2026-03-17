"""Connection health tracking — refresh failure counting and status transitions."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, case, update
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.models.connection import Connection, ConnectionStatus


async def record_refresh_failure(
    connection_id: uuid.UUID,
    session: AsyncSession,
    reauth_threshold: int,
) -> str:
    """Increment refresh failure count and transition to needs_reauth if threshold reached.

    Returns:
        New connection status
    """
    needs_reauth_expr = and_(
        Connection.status == ConnectionStatus.ACTIVE,
        Connection.refresh_failure_count + 1 >= reauth_threshold,
    )

    result = await session.execute(
        update(Connection)
        .where(Connection.id == connection_id)
        .values(
            refresh_failure_count=Connection.refresh_failure_count + 1,
            last_refresh_failure_at=datetime.now(timezone.utc),
            status=case(
                (needs_reauth_expr, ConnectionStatus.NEEDS_REAUTH),
                else_=Connection.status,
            ),
            status_reason=case(
                (needs_reauth_expr, "Token refresh failed repeatedly. Please reauthorize."),
                else_=Connection.status_reason,
            ),
        )
        .returning(Connection.status)
    )
    new_status = result.scalar_one_or_none()
    if new_status is None:
        return ConnectionStatus.REVOKED

    await session.commit()
    if isinstance(new_status, ConnectionStatus):
        return new_status.value
    return str(new_status)


async def record_refresh_success(
    connection_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    """Reset refresh failure count after a successful token refresh."""
    await session.execute(
        update(Connection)
        .where(Connection.id == connection_id)
        .values(refresh_failure_count=0, last_refresh_failure_at=None)
    )
    await session.commit()


async def transition_to_active(
    connection_id: uuid.UUID,
    session: AsyncSession,
    granted_scopes: list[str] | None = None,
    provider_account_id: str | None = None,
) -> None:
    """Transition a pending connection to active after successful OAuth."""
    values: dict = {
        "status": ConnectionStatus.ACTIVE,
        "status_reason": None,
        "refresh_failure_count": 0,
    }
    if granted_scopes is not None:
        values["granted_scopes"] = granted_scopes
    if provider_account_id is not None:
        values["provider_account_id"] = provider_account_id

    await session.execute(update(Connection).where(Connection.id == connection_id).values(**values))
    await session.commit()


async def transition_to_revoked(
    connection_id: uuid.UUID,
    session: AsyncSession,
    reason: str | None = None,
) -> None:
    """Transition a connection to revoked and clear its credentials."""
    await session.execute(
        update(Connection)
        .where(Connection.id == connection_id)
        .values(
            status=ConnectionStatus.REVOKED,
            status_reason=reason,
            credentials_encrypted=None,
        )
    )
    await session.commit()


async def update_last_used(
    connection_id: uuid.UUID,
    session: AsyncSession,
) -> None:
    """Update the last_used_at timestamp on a connection."""
    await session.execute(
        update(Connection)
        .where(Connection.id == connection_id)
        .values(last_used_at=datetime.now(timezone.utc))
    )
    await session.commit()
