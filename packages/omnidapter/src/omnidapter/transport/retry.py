"""
Retry policy and backoff configuration.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


@dataclass
class RetryPolicy:
    """Configuration for retry behavior on HTTP requests.

    Attributes:
        max_retries: Maximum number of retry attempts (not counting initial).
        backoff_base: Base backoff in seconds (exponential).
        backoff_max: Maximum backoff cap in seconds.
        retry_on_status: HTTP status codes that trigger a retry.
        retry_on_network_error: Whether to retry on network-level failures.
        jitter: Whether to add random jitter to backoff.
    """
    max_retries: int = 3
    backoff_base: float = 1.0
    backoff_max: float = 60.0
    retry_on_status: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )
    retry_on_network_error: bool = True
    jitter: bool = True

    @classmethod
    def default(cls) -> RetryPolicy:
        """Return the default retry policy."""
        return cls()

    @classmethod
    def no_retry(cls) -> RetryPolicy:
        """Return a policy with no retries."""
        return cls(max_retries=0)

    def get_backoff(self, attempt: int) -> float:
        """Compute backoff seconds for a given attempt number (0-indexed)."""
        import random
        delay = min(self.backoff_base * (2 ** attempt), self.backoff_max)
        if self.jitter:
            delay *= (0.5 + random.random() * 0.5)
        return delay
