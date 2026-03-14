"""Top-level test configuration for omnidapter-api."""

from __future__ import annotations

import os

# Override settings for tests
os.environ.setdefault("OMNIDAPTER_ENCRYPTION_KEY", "test-encryption-key-for-all-tests")
os.environ.setdefault("OMNIDAPTER_DATABASE_URL", "postgresql+asyncpg://localhost/omnidapter_test")
os.environ.setdefault("OMNIDAPTER_ENV", "test")
