"""Organization model."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from omnidapter_api.database import Base


class PlanType(str, Enum):
    FREE = "free"
    PAYG = "payg"


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    plan: Mapped[str] = mapped_column(String(50), default=PlanType.FREE, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    memberships: Mapped[list] = relationship("Membership", back_populates="organization")
    api_keys: Mapped[list] = relationship("APIKey", back_populates="organization")
    provider_configs: Mapped[list] = relationship("ProviderConfig", back_populates="organization")
    connections: Mapped[list] = relationship("Connection", back_populates="organization")
    usage_records: Mapped[list] = relationship("UsageRecord", back_populates="organization")
