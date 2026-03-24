"""
Omnidapter testing utilities.

For use in consuming apps and provider implementations.

    from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore
    from omnidapter.testing.contracts.calendar import CalendarProviderContract
"""

from omnidapter.testing.contracts.calendar import CalendarProviderContract
from omnidapter.testing.fakes.stores import InMemoryCredentialStore, InMemoryOAuthStateStore

__all__ = [
    "InMemoryCredentialStore",
    "InMemoryOAuthStateStore",
    "CalendarProviderContract",
]
