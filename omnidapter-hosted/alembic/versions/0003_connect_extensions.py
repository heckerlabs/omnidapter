"""Connect extensions — is_enabled on provider configs, reconnect fields on link tokens.

Revision ID: hosted_0003
Revises: hosted_0002
Create Date: 2026-03-24
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "hosted_0003"
down_revision = "hosted_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # is_enabled on hosted_provider_configs (default true — existing configs stay enabled)
    op.add_column(
        "hosted_provider_configs",
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # connection_id (FK to connections) and locked_provider_key on hosted_link_tokens
    op.add_column(
        "hosted_link_tokens",
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "hosted_link_tokens",
        sa.Column("locked_provider_key", sa.String(50), nullable=True),
    )
    op.create_foreign_key(
        "fk_hosted_link_tokens_connection_id",
        "hosted_link_tokens",
        "connections",
        ["connection_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_hosted_link_tokens_connection_id",
        "hosted_link_tokens",
        type_="foreignkey",
    )
    op.drop_column("hosted_link_tokens", "locked_provider_key")
    op.drop_column("hosted_link_tokens", "connection_id")
    op.drop_column("hosted_provider_configs", "is_enabled")
