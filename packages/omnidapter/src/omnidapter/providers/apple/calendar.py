"""
Apple Calendar service — iCloud CalDAV with a fixed server URL.

Users provide only their Apple ID and an app-specific password; the
iCloud CalDAV endpoint is pre-configured.
"""

from __future__ import annotations

from typing import Any

from omnidapter.providers.caldav.calendar import CalDAVCalendarService
from omnidapter.providers.caldav.server_hints import CalDAVServerHint
from omnidapter.stores.credentials import StoredCredential
from omnidapter.transport.client import OmnidapterHttpClient
from omnidapter.transport.retry import RetryPolicy

ICLOUD_CALDAV_URL = "https://caldav.icloud.com"


class AppleCalendarService(CalDAVCalendarService):
    """Apple Calendar service backed by iCloud CalDAV.

    The server URL is always ``https://caldav.icloud.com``; callers
    only need to supply Basic credentials (Apple ID + app-specific password).
    """

    def __init__(
        self,
        connection_id: str,
        stored_credential: StoredCredential,
        retry_policy: RetryPolicy | None = None,
        hooks: Any = None,
    ) -> None:
        super().__init__(connection_id, stored_credential, retry_policy, hooks)
        self._server_url = ICLOUD_CALDAV_URL
        self._server_hint = CalDAVServerHint.ICLOUD
        self._http = OmnidapterHttpClient(
            provider_key="apple",
            retry_policy=retry_policy,
            hooks=hooks,
        )

    @property
    def _provider_key(self) -> str:
        return "apple"
