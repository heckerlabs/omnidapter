"""Migrate link tokens to server companion table pattern

Revision ID: hosted_0003
Revises: hosted_0002
Create Date: 2026-03-27

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "hosted_0003"
down_revision: str | Sequence[str] | None = ("hosted_0002", "0002")
branch_labels: str | Sequence[str] | None = None
# Ensure server's link_tokens table exists before we create the companion table
depends_on: str | Sequence[str] | None = "0002"


def upgrade() -> None:
    """Upgrade schema."""
    # Create companion table — link_token_id references link_tokens.id (server table)
    op.create_table(
        "hosted_link_token_owners",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        # No FK to link_tokens: server and hosted use different SQLAlchemy metadata bases.
        # Ownership is validated in code (same pattern as hosted_connection_owners).
        sa.Column("link_token_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("link_token_id", name="uq_hosted_link_token_owner_link_token"),
    )
    op.create_index(
        "ix_hosted_link_token_owners_tenant_id",
        "hosted_link_token_owners",
        ["tenant_id"],
    )

    # Drop old hosted_link_tokens table — link tokens now live in server's link_tokens table.
    # No data migration needed: tokens are short-lived (default 30 min) and will expire naturally.
    op.drop_index("ix_hosted_link_tokens_tenant_is_active", table_name="hosted_link_tokens")
    op.drop_index("ix_hosted_link_tokens_token_prefix", table_name="hosted_link_tokens")
    op.drop_table("hosted_link_tokens")


def downgrade() -> None:
    """Downgrade schema."""
    op.create_table(
        "hosted_link_tokens",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.String(length=255), nullable=False),
        sa.Column("token_prefix", sa.String(length=20), nullable=False),
        sa.Column("end_user_id", sa.String(length=255), nullable=True),
        sa.Column(
            "allowed_providers",
            sa.dialects.postgresql.ARRAY(sa.String()),  # type: ignore[attr-defined]
            nullable=True,
        ),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("connection_id", sa.UUID(), nullable=True),
        sa.Column("locked_provider_key", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_hosted_link_tokens_token_prefix", "hosted_link_tokens", ["token_prefix"])
    op.create_index(
        "ix_hosted_link_tokens_tenant_is_active", "hosted_link_tokens", ["tenant_id", "is_active"]
    )

    op.drop_index("ix_hosted_link_token_owners_tenant_id", table_name="hosted_link_token_owners")
    op.drop_table("hosted_link_token_owners")
