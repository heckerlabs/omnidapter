"""
Omnidapter logging configuration.

Uses Python's standard logging module under the 'omnidapter' namespace.
The library never configures handlers or formatters — consumers attach their own.

Logger hierarchy:
  omnidapter                  # root library logger
  omnidapter.transport        # HTTP transport, requests, responses
  omnidapter.auth             # OAuth, token refresh
  omnidapter.providers.google
  omnidapter.providers.microsoft
  omnidapter.providers.caldav
  omnidapter.providers.zoho
  omnidapter.registry         # provider registration
  omnidapter.connection       # connection resolution
"""

import logging


def get_logger(name: str) -> logging.Logger:
    """Return a logger under the omnidapter namespace.

    Args:
        name: Sub-namespace, e.g. "transport", "auth", "providers.google".
              Will be prefixed with "omnidapter." automatically.

    Returns:
        A Logger instance.
    """
    if not name.startswith("omnidapter"):
        name = f"omnidapter.{name}"
    return logging.getLogger(name)


# Module-level convenience loggers
transport_logger = get_logger("transport")
auth_logger = get_logger("auth")
registry_logger = get_logger("registry")
connection_logger = get_logger("connection")
