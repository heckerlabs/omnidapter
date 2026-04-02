"""add connect session fields to link_tokens

Adds the four columns needed for the one-time bootstrap-token → session-token
exchange flow (POST /connect/session):

- consumed_at      — timestamp set when the lt_ token is first exchanged;
                     prevents the bootstrap URL from being reused.
- session_token_hash   — bcrypt hash of the issued cs_ session token.
- session_token_prefix — first 16 chars of the cs_ token (lookup index).
- session_expires_at   — when the session token expires (independent of the
                         link token's own expires_at).

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-02
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "link_tokens",
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "link_tokens",
        sa.Column("session_token_hash", sa.String(255), nullable=True),
    )
    op.add_column(
        "link_tokens",
        sa.Column("session_token_prefix", sa.String(20), nullable=True),
    )
    op.add_column(
        "link_tokens",
        sa.Column("session_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_link_tokens_session_token_prefix",
        "link_tokens",
        ["session_token_prefix"],
    )


def downgrade() -> None:
    op.drop_index("ix_link_tokens_session_token_prefix", table_name="link_tokens")
    op.drop_column("link_tokens", "session_expires_at")
    op.drop_column("link_tokens", "session_token_prefix")
    op.drop_column("link_tokens", "session_token_hash")
    op.drop_column("link_tokens", "consumed_at")
