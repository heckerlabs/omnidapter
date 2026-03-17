"""Initial schema.

Revision ID: 0001
Revises:
Create Date: 2026-03-17
"""

from __future__ import annotations

import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # api_keys — no organization scoping; any valid key accesses all resources
    op.create_table(
        "api_keys",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("key_prefix", sa.String(20), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("is_test", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )

    # provider_configs — one config per provider key, server-wide
    op.create_table(
        "provider_configs",
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
        sa.Column("provider_key", sa.String(50), nullable=False, unique=True),
        sa.Column("auth_kind", sa.String(50), nullable=False, server_default="oauth2"),
        sa.Column("client_id_encrypted", sa.Text(), nullable=True),
        sa.Column("client_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("scopes", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("is_fallback", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.UniqueConstraint("provider_key", name="uq_provider_config_provider"),
    )

    # connections — globally scoped; external_id is globally unique
    # NOTE: In a standalone self-hosted deployment all valid API keys share
    # the same connection namespace. Callers are responsible for ensuring
    # external_id values are globally unique. When running omnidapter-hosted
    # a tenant_id column is added via the hosted migration and enforces
    # per-tenant isolation.
    op.create_table(
        "connections",
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
        sa.Column("provider_key", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(255), nullable=True, unique=True),
        sa.Column("status", sa.String(50), nullable=False, server_default="pending"),
        sa.Column("status_reason", sa.Text(), nullable=True),
        sa.Column("granted_scopes", postgresql.ARRAY(sa.String()), nullable=True),
        sa.Column("provider_account_id", sa.String(255), nullable=True),
        sa.Column("credentials_encrypted", sa.Text(), nullable=True),
        sa.Column("provider_config", postgresql.JSONB(), nullable=True),
        sa.Column("refresh_failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_refresh_failure_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("external_id", name="uq_connection_external_id"),
    )

    # oauth_states — temporary OAuth flow state
    op.create_table(
        "oauth_states",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("provider_key", sa.String(50), nullable=False),
        sa.Column("connection_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("state_token", sa.String(255), nullable=False, unique=True),
        sa.Column("pkce_verifier_encrypted", sa.Text(), nullable=True),
        sa.Column("redirect_uri", sa.Text(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(), nullable=True),
    )

    # Indexes
    op.create_index("ix_connections_status", "connections", ["status"])
    op.create_index("ix_connections_provider", "connections", ["provider_key"])
    op.create_index("ix_oauth_states_token", "oauth_states", ["state_token"])
    op.create_index("ix_api_keys_prefix", "api_keys", ["key_prefix"])


def downgrade() -> None:
    op.drop_table("oauth_states")
    op.drop_table("connections")
    op.drop_table("provider_configs")
    op.drop_table("api_keys")
