"""Top-level test configuration for omnidapter-hosted."""

from __future__ import annotations

import os

os.environ.setdefault("OMNIDAPTER_ENCRYPTION_KEY", "test-encryption-key-for-hosted-tests")
os.environ.setdefault("OMNIDAPTER_DATABASE_URL", "postgresql+asyncpg://localhost/omnidapter_test")
os.environ.setdefault("OMNIDAPTER_ENV", "test")
