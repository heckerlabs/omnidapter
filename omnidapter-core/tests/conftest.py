"""Top-level test configuration for omnidapter-core."""

from __future__ import annotations

from pathlib import Path

import pytest


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Auto-mark tests under integration/ directories."""
    for item in items:
        if "integration" in Path(item.fspath).parts:
            item.add_marker(pytest.mark.integration)
