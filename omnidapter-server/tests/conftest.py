"""Top-level test configuration for omnidapter-server."""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Set env var defaults needed by both unit and integration tests."""
    os.environ.setdefault(
        "OMNIDAPTER_ENCRYPTION_KEY",
        "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=",
    )
    os.environ.setdefault(
        "OMNIDAPTER_DATABASE_URL", "postgresql+asyncpg://localhost/omnidapter_test"
    )
    os.environ.setdefault("OMNIDAPTER_ENV", "DEV")
    os.environ.setdefault("OMNIDAPTER_API_KEY", "omni_test_suite_initial_key_123456")


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark tests under integration/ directories."""
    for item in items:
        if "integration" in Path(item.fspath).parts:
            item.add_marker(pytest.mark.integration)
