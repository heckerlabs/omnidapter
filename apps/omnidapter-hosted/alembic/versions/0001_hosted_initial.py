"""Hosted initial schema — extends server schema with tenant support.

Revision ID: hosted_0001
Revises: 0001
Create Date: 2026-03-17
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "hosted_0001"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # tenants table
    op.create_table(
        "tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("plan", sa.String(50), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("settings", postgresql.JSONB(), nullable=True),
    )

    # users table
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("workos_user_id", sa.String(255), nullable=True),
    )

    # memberships table
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(50), nullable=False, server_default="member"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.UniqueConstraint("tenant_id", "user_id", name="uq_membership_tenant_user"),
    )

    # hosted_api_keys table (tenant-scoped, separate from server's global api_keys)
    op.create_table(
        "hosted_api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    # hosted_usage_records table (per-tenant usage for billing)
    op.create_table(
        "hosted_usage_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("endpoint", sa.String(255), nullable=False),
        sa.Column("provider_key", sa.String(50), nullable=True),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("billed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )

    # hosted_connection_owners table (tenant ownership mapping for shared connections)
    op.create_table(
        "hosted_connection_owners",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"]),
        sa.UniqueConstraint("connection_id", name="uq_hosted_connection_owner_connection"),
    )

    # hosted_provider_configs table (tenant-scoped OAuth app credentials)
    op.create_table(
        "hosted_provider_configs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_key", sa.String(50), nullable=False),
        sa.Column("auth_kind", sa.String(50), nullable=False, server_default="oauth2"),
        sa.Column("client_id_encrypted", sa.Text(), nullable=True),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint(
            "tenant_id",
            "provider_key",
            name="uq_hosted_provider_config_tenant_provider",
        ),
    )

    # Indexes
    op.create_index("ix_hosted_api_keys_tenant", "hosted_api_keys", ["tenant_id"])
    op.create_index("ix_hosted_api_keys_prefix", "hosted_api_keys", ["key_prefix"])
    op.create_index(
        "ix_hosted_usage_tenant_created", "hosted_usage_records", ["tenant_id", "created_at"]
    )
    op.create_index("ix_hosted_connection_owners_tenant", "hosted_connection_owners", ["tenant_id"])
    op.create_index(
        "ix_hosted_provider_configs_tenant_provider",
        "hosted_provider_configs",
        ["tenant_id", "provider_key"],
    )
    op.create_index("ix_memberships_tenant", "memberships", ["tenant_id"])
    op.create_index("ix_users_email", "users", ["email"])


def downgrade() -> None:
    op.drop_table("hosted_usage_records")
    op.drop_table("hosted_provider_configs")
    op.drop_table("hosted_connection_owners")
    op.drop_table("hosted_api_keys")
    op.drop_table("memberships")
    op.drop_table("users")
    op.drop_table("tenants")
