from __future__ import annotations

from datetime import datetime
from typing import Protocol

from omnidapter.auth.models import OAuthStatePayload


class OAuthStateStore(Protocol):
    async def save_state(self, state_id: str, payload: OAuthStatePayload, expires_at: datetime) -> None: ...

    async def load_state(self, state_id: str) -> OAuthStatePayload | None: ...

    async def delete_state(self, state_id: str) -> None: ...
