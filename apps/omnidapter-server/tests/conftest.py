"""Top-level test configuration for omnidapter-server."""

from __future__ import annotations

import os

# Override settings for tests
os.environ.setdefault(
    "OMNIDAPTER_ENCRYPTION_KEY",
    "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
)
os.environ.setdefault("OMNIDAPTER_DATABASE_URL", "postgresql+asyncpg://localhost/omnidapter_test")
os.environ.setdefault("OMNIDAPTER_ENV", "DEV")
