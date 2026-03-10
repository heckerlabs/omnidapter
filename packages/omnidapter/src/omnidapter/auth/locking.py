from __future__ import annotations

import asyncio


class ConnectionLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}

    def for_connection(self, connection_id: str) -> asyncio.Lock:
        if connection_id not in self._locks:
            self._locks[connection_id] = asyncio.Lock()
        return self._locks[connection_id]
