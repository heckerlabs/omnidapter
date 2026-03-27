"""Hosted link token ownership mapping.

Maps global link token IDs to tenant owners for hosted isolation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from omnidapter_hosted.database import HostedBase


class HostedLinkTokenOwner(HostedBase):
    __tablename__ = "hosted_link_token_owners"
    __table_args__ = (
        UniqueConstraint("link_token_id", name="uq_hosted_link_token_owner_link_token"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    # Note: no FK constraint because LinkToken is in omnidapter_server.models with different metadata.
    # Validation is done in routers/link_tokens.py and dependencies.py
    link_token_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
