"""Link token model — short-lived tokens for the Connect UI."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from omnidapter_server.database import Base


class LinkToken(Base):
    __tablename__ = "link_tokens"
    __table_args__ = (
        Index("ix_link_tokens_token_prefix", "token_prefix"),
        Index("ix_link_tokens_is_active", "is_active"),
        Index("ix_link_tokens_session_token_prefix", "session_token_prefix"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    # bcrypt hash of the raw token
    token_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    # First 16 chars of raw token for DB lookup (e.g. "lt_abc123456789")
    token_prefix: Mapped[str] = mapped_column(String(20), nullable=False)
    # Opaque end-user identifier provided by the host application
    end_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Optional list of provider keys this token is allowed to connect
    allowed_providers: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # Where to redirect after the connect flow completes (client app URL)
    redirect_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Reconnect: lock this token to an existing connection.
    # No FK constraint — Connection is in the same metadata but validation is done in routers.
    connection_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    # Provider key locked to the connection (derived at token creation for reconnect)
    locked_provider_key: Mapped[str | None] = mapped_column(String(50), nullable=True)
    # Service kinds to authorize when creating a connection via this token
    services: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    # One-time exchange: set when the bootstrap lt_ token is consumed via POST /connect/session.
    # Once set the bootstrap token is permanently unusable — only the cs_ session token works.
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Session token (cs_*) issued in exchange for the bootstrap lt_ token.
    session_token_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    session_token_prefix: Mapped[str | None] = mapped_column(String(20), nullable=True)
    session_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
