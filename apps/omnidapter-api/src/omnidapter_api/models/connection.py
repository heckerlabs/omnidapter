"""Connection model — end-user's authorized connection to a provider."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnidapter_api.database import Base

if TYPE_CHECKING:
    from omnidapter_api.models.organization import Organization


class ConnectionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    NEEDS_REAUTH = "needs_reauth"
    REVOKED = "revoked"


class Connection(Base):
    __tablename__ = "connections"
    __table_args__ = (
        UniqueConstraint("organization_id", "external_id", name="uq_connection_org_external_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    provider_key: Mapped[str] = mapped_column(String(50), nullable=False)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(50), default=ConnectionStatus.PENDING, nullable=False
    )
    status_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    granted_scopes: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    provider_account_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Encrypted credentials
    credentials_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    refresh_failure_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_refresh_failure_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    organization: Mapped[Organization] = relationship("Organization", back_populates="connections")
    usage_records: Mapped[list] = relationship("UsageRecord", back_populates="connection")
