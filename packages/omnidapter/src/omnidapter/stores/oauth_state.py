"""
OAuthStateStore interface for temporary OAuth state persistence.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any


class OAuthStateStore(ABC):
    """Abstract interface for OAuth state persistence.

    Used to store temporary state between OAuth begin and complete.
    The consuming app implements this.
    """

    @abstractmethod
    async def save_state(
        self,
        state_id: str,
        payload: dict[str, Any],
        expires_at: datetime,
    ) -> None:
        """Persist an OAuth state payload with expiry."""
        ...

    @abstractmethod
    async def load_state(self, state_id: str) -> dict[str, Any] | None:
        """Load a state payload by state_id.

        Returns None if the state does not exist or has expired.
        """
        ...

    @abstractmethod
    async def delete_state(self, state_id: str) -> None:
        """Delete a state payload."""
        ...
