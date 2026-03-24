"""Add hosted_link_tokens table.

Revision ID: hosted_0002
Revises: hosted_0001
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "hosted_0002"
down_revision = "hosted_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "hosted_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("token_prefix", sa.String(20), nullable=False),
        sa.Column("end_user_id", sa.String(255), nullable=True),
        sa.Column("allowed_providers", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    op.create_index(
        "ix_hosted_link_tokens_prefix",
        "hosted_link_tokens",
        ["token_prefix"],
    )
    op.create_index(
        "ix_hosted_link_tokens_tenant_active",
        "hosted_link_tokens",
        ["tenant_id", "is_active"],
    )


def downgrade() -> None:
    op.drop_table("hosted_link_tokens")
