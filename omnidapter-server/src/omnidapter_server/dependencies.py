"""FastAPI dependency injection helpers."""

from __future__ import annotations

import logging
import uuid
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
api_key_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="APIKeyAuth",
    description="Main Server API Key (omni_*)",
)

link_token_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="LinkTokenAuth",
    description="Connect UI session token (cs_*). The one-time lt_* bootstrap token is only accepted by POST /connect/init.",
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
        Security(api_key_scheme),
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


class LinkTokenContext:
    """Resolved context for a Connect UI request authenticated by a link token."""

    def __init__(
        self,
        *,
        end_user_id: str | None,
        allowed_providers: list[str] | None,
        redirect_uri: str | None,
        connection_id: uuid.UUID | None = None,
        locked_provider_key: str | None = None,
        services: list[str] | None = None,
    ) -> None:
        self.end_user_id = end_user_id
        self.allowed_providers = allowed_providers
        self.redirect_uri = redirect_uri
        self.connection_id = connection_id
        self.locked_provider_key = locked_provider_key
        self.services = services

    @property
    def is_reconnect(self) -> bool:
        return self.connection_id is not None


async def get_link_token_context(
    bearer_credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(link_token_scheme),
    ] = None,
    session: AsyncSession = Depends(get_session),
) -> LinkTokenContext:
    """Validate a cs_* session token from Authorization header and return context.

    Session tokens are issued by ``POST /connect/session`` in exchange for the
    one-time bootstrap ``lt_*`` token.  Bootstrap tokens are intentionally
    rejected here — they may only be used at the session exchange endpoint.
    """
    from omnidapter_server.services.link_tokens import verify_session_token

    if bearer_credentials is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Missing Authorization header"},
        )

    raw_token = bearer_credentials.credentials
    if not raw_token.startswith("cs_"):
        raise HTTPException(
            status_code=401,
            detail={"code": "unauthenticated", "message": "Invalid session token"},
        )

    link_token = await verify_session_token(raw_token, session)
    if link_token is None:
        raise HTTPException(
            status_code=401,
            detail={"code": "session_expired", "message": "Session expired or invalid"},
        )

    return LinkTokenContext(
        end_user_id=link_token.end_user_id,
        allowed_providers=link_token.allowed_providers,
        redirect_uri=link_token.redirect_uri,
        connection_id=link_token.connection_id,
        locked_provider_key=link_token.locked_provider_key,
        services=link_token.services,
    )


def get_request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "req_unknown")
