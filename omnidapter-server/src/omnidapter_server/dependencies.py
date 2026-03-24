"""FastAPI dependency injection helpers."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.database import get_session
from omnidapter_server.encryption import EncryptionService
from omnidapter_server.models.api_key import APIKey
from omnidapter_server.services.auth import authenticate_api_key, update_last_used

logger = logging.getLogger(__name__)
_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="BearerAuth",
    description="Use `Authorization: Bearer <API_KEY>`",
)


def get_encryption_service(
    settings: Annotated[Settings, Depends(get_settings)],
) -> EncryptionService:
    return EncryptionService(
        current_key=settings.omnidapter_encryption_key,
        previous_key=settings.omnidapter_encryption_key_previous,
        allow_plaintext_fallback=settings.omnidapter_env == "LOCAL",
    )


class AuthContext:
    """Resolved authentication context for a request."""

    def __init__(self, api_key: APIKey | None) -> None:
        self.api_key = api_key


async def get_auth_context(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(_bearer_scheme),
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> AuthContext:
    """Extract and validate API key from Authorization header."""
    if settings.omnidapter_auth_mode == "disabled":
        return AuthContext(api_key=None)

    authorization = request.headers.get("Authorization")

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Missing Authorization header"},
        )

    if bearer_credentials is None:
        raise HTTPException(
            status_code=401,
            detail={
                "code": "invalid_api_key",
                "message": "Authorization header must be 'Bearer <key>'",
            },
        )

    raw_key = bearer_credentials.credentials
    api_key = await authenticate_api_key(raw_key, session)

    if api_key is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "invalid_api_key", "message": "Invalid or inactive API key"},
        )

    await update_last_used(api_key.id, session)

    return AuthContext(api_key=api_key)


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")
