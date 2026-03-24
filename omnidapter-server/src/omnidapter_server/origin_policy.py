"""Origin and redirect safety helpers shared by API apps."""

from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
_warned_default = False


def _is_prod_env(env: str) -> bool:
    normalized = env.strip().upper()
    if normalized == "PRODUCTION":
        return True
    return normalized == "PROD"


def parse_allowed_origin_domains(raw: str) -> list[str]:
    """Parse comma-separated domain patterns.

    Supported patterns:
    - "*" for any domain
    - "example.com" for an exact host
    - "*.example.com" for subdomains
    """

    global _warned_default

    domains = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not domains:
        domains = ["*"]

    if domains == ["*"] and not _warned_default:
        logger.warning(
            "OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS is not configured; "
            "defaulting to '*'. This is permissive and should be restricted in production."
        )
        _warned_default = True

    return domains


def is_host_allowed(host: str, allowed_domain_patterns: list[str]) -> bool:
    """Return whether a host is accepted by allowed domain patterns."""

    normalized_host = host.strip().lower().rstrip(".")
    if not normalized_host:
        return False

    for pattern in allowed_domain_patterns:
        normalized_pattern = pattern.strip().lower()
        if normalized_pattern == "*":
            return True
        if normalized_pattern.startswith("*."):
            suffix = normalized_pattern[2:]
            if normalized_host.endswith(f".{suffix}"):
                return True
            continue
        if normalized_host == normalized_pattern:
            return True

    return False


def build_cors_settings(
    allowed_domain_patterns: list[str],
) -> tuple[list[str], str | None, bool]:
    """Build CORSMiddleware settings from allowed host patterns."""

    if "*" in allowed_domain_patterns:
        return ["*"], None, False

    regex_parts: list[str] = []
    for pattern in allowed_domain_patterns:
        if pattern.startswith("*."):
            suffix = re.escape(pattern[2:])
            regex_parts.append(rf"https?://(?:[A-Za-z0-9-]+\.)+{suffix}(?::\d+)?")
        else:
            regex_parts.append(rf"https?://{re.escape(pattern)}(?::\d+)?")

    allow_origin_regex = "^(" + "|".join(regex_parts) + ")$"
    return [], allow_origin_regex, True


def validate_redirect_url(
    redirect_url: str,
    *,
    request_host: str | None,
    allowed_domain_patterns: list[str],
    env: str,
) -> None:
    """Validate redirect URL against the origin-domain policy."""

    parts = urlsplit(redirect_url)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("redirect_url must start with http:// or https://")
    if parts.hostname is None:
        raise ValueError("redirect_url must include a hostname")
    if parts.username or parts.password:
        raise ValueError("redirect_url must not include URL credentials")

    if request_host and not is_host_allowed(request_host, allowed_domain_patterns):
        raise ValueError("Request host is not allowed by OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS")

    if not is_host_allowed(parts.hostname, allowed_domain_patterns):
        raise ValueError("redirect_url host is not allowed")

    if _is_prod_env(env) and parts.scheme != "https" and parts.hostname not in _LOCAL_HOSTS:
        raise ValueError("redirect_url must use https when OMNIDAPTER_ENV=PROD")
