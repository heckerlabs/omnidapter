"""
CalDAV authentication helpers (Basic auth).
"""

from __future__ import annotations

import base64

from omnidapter.auth.models import BasicCredentials


def basic_auth_header(credentials: BasicCredentials) -> str:
    """Generate a Basic Authorization header value."""
    token = base64.b64encode(f"{credentials.username}:{credentials.password}".encode()).decode()
    return f"Basic {token}"
