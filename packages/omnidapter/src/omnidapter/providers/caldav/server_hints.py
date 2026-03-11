"""
Known CalDAV server quirks and detection.

The CalDAV protocol has many implementations with varying behaviors.
This module provides detection logic for known servers with specific quirks.
"""

from __future__ import annotations

from enum import Enum


class CalDAVServerHint(str, Enum):
    """Known CalDAV server implementations with special handling."""

    GENERIC = "generic"
    GOOGLE = "google"  # Google's CalDAV endpoint (legacy)
    ICLOUD = "icloud"
    FASTMAIL = "fastmail"
    NEXTCLOUD = "nextcloud"
    RADICALE = "radicale"
    DAVICAL = "davical"


def detect_server_hint(server_url: str) -> CalDAVServerHint:
    """Detect the server hint from a server URL.

    Args:
        server_url: The CalDAV server URL.

    Returns:
        A CalDAVServerHint indicating the server type.
    """
    url_lower = server_url.lower()

    if "icloud.com" in url_lower or "caldav.icloud.com" in url_lower:
        return CalDAVServerHint.ICLOUD
    if "fastmail.com" in url_lower or "fastmail.fm" in url_lower:
        return CalDAVServerHint.FASTMAIL
    if "nextcloud" in url_lower or "/remote.php/dav" in url_lower:
        return CalDAVServerHint.NEXTCLOUD
    if "google.com" in url_lower:
        return CalDAVServerHint.GOOGLE
    if "radicale" in url_lower:
        return CalDAVServerHint.RADICALE
    if "davical" in url_lower:
        return CalDAVServerHint.DAVICAL

    return CalDAVServerHint.GENERIC


def get_principal_url_template(
    server_hint: CalDAVServerHint, server_url: str, username: str
) -> str:
    """Return the best-guess principal URL for a given server hint."""
    base = server_url.rstrip("/")

    if server_hint == CalDAVServerHint.ICLOUD:
        return "https://caldav.icloud.com"
    if server_hint == CalDAVServerHint.NEXTCLOUD:
        return f"{base}/remote.php/dav/principals/users/{username}/"
    if server_hint == CalDAVServerHint.FASTMAIL:
        return f"{base}/"

    return f"{base}/"
