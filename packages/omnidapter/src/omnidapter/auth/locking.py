"""
Per-connection async locking for token refresh concurrency safety.

Maintains one asyncio.Lock per active connection_id.
For multi-process deployments, consumers are responsible for distributed coordination.
"""
from __future__ import annotations

import asyncio
import weakref


class ConnectionLockManager:
    """Manages per-connection-id async locks.

    Uses weak references so locks for inactive connections are garbage-collected.
    """

    def __init__(self) -> None:
        self._locks: weakref.WeakValueDictionary[str, asyncio.Lock] = (
            weakref.WeakValueDictionary()
        )
        self._meta_lock = asyncio.Lock()

    async def acquire(self, connection_id: str) -> asyncio.Lock:
        """Acquire and return the lock for this connection_id.

        Creates the lock if it doesn't exist.
        """
        async with self._meta_lock:
            lock = self._locks.get(connection_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[connection_id] = lock
        return lock

    def get_or_create(self, connection_id: str) -> asyncio.Lock:
        """Synchronously get or create a lock (must be called from async context)."""
        lock = self._locks.get(connection_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[connection_id] = lock
        return lock
