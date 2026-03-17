"""
Correlation ID generation and management for request tracing.
"""

from __future__ import annotations

import uuid


def new_correlation_id() -> str:
    """Generate a new unique correlation ID."""
    return str(uuid.uuid4())
