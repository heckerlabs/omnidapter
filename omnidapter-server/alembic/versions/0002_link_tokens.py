"""add link_tokens table

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "link_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("token_prefix", sa.String(length=20), nullable=False),
        sa.Column("end_user_id", sa.String(length=255), nullable=True),
        sa.Column("allowed_providers", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=True),
        sa.Column("locked_provider_key", sa.String(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        op.f("ix_link_tokens_token_prefix"), "link_tokens", ["token_prefix"], unique=False
    )
    op.create_index(op.f("ix_link_tokens_is_active"), "link_tokens", ["is_active"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_link_tokens_is_active"), table_name="link_tokens")
    op.drop_index(op.f("ix_link_tokens_token_prefix"), table_name="link_tokens")
    op.drop_table("link_tokens")
