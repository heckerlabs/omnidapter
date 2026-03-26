"""Hosted link token model — short-lived tokens for the Connect UI."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from omnidapter_hosted.database import HostedBase


class HostedLinkToken(HostedBase):
    __tablename__ = "hosted_link_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False
    )
    # bcrypt hash of the raw token
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # First 16 chars of raw token for DB lookup (e.g. "lt_abc123456789")
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    # Opaque end-user identifier provided by the host application
    end_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional list of provider keys this token is allowed to connect
    allowed_providers: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # Where to redirect after the connect flow completes
    redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Reconnect: lock this token to an existing connection (for credential refresh)
    # Note: no FK constraint because Connection is in omnidapter_server.models with different metadata.
    # Validation is done in routers/link_tokens.py._resolve_reconnect_provider()
    connection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )
    # Provider key locked to the connection (derived at token creation for reconnect)
    locked_provider_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
