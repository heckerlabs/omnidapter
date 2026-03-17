"""Hosted database setup — separate Base from server so hosted can extend tables."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class HostedBase(DeclarativeBase):
    """SQLAlchemy declarative base for hosted-specific models.

    Uses a separate metadata object from the server's Base so hosted can
    define tenant_id extensions to server tables without mapper conflicts.
    """
