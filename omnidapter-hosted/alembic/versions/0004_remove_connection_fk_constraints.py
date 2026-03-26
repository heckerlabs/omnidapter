"""Remove FK constraints on connection_id (cross-metadata issue).

Revision ID: hosted_0004
Revises: hosted_0003
Create Date: 2026-03-25

The Connection model is in omnidapter_server with a different SQLAlchemy
metadata, so FK constraints cause NoReferencedTableError. These are removed
and validation is handled in application code instead.
"""

from __future__ import annotations

from alembic import op

revision = "hosted_0004"
down_revision = "hosted_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Remove FK from hosted_link_tokens.connection_id
    op.drop_constraint(
        "fk_hosted_link_tokens_connection_id",
        "hosted_link_tokens",
        type_="foreignkey",
    )

    # Remove FK from hosted_connection_owners.connection_id (auto-generated constraint name)
    op.drop_constraint(
        "hosted_connection_owners_connection_id_fkey",
        "hosted_connection_owners",
        type_="foreignkey",
    )


def downgrade() -> None:
    # Recreate FK for hosted_link_tokens.connection_id
    op.create_foreign_key(
        "fk_hosted_link_tokens_connection_id",
        "hosted_link_tokens",
        "connections",
        ["connection_id"],
        ["id"],
    )

    # Recreate FK for hosted_connection_owners.connection_id
    op.create_foreign_key(
        "hosted_connection_owners_connection_id_fkey",
        "hosted_connection_owners",
        "connections",
        ["connection_id"],
        ["id"],
    )
