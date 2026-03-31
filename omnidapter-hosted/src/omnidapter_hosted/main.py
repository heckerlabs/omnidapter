"""Omnidapter Hosted — multi-tenant FastAPI application."""

from __future__ import annotations

import logging
import re

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import server's auth dependency so we can override it
from omnidapter_server.config import get_settings as _server_get_settings
from omnidapter_server.dependencies import get_auth_context as _server_get_auth_context
from omnidapter_server.middleware.request_id import RequestIdMiddleware

from omnidapter_hosted.config import HostedSettings, get_hosted_settings
from omnidapter_hosted.dependencies import get_hosted_auth_context
from omnidapter_hosted.routers import (
    auth,
    calendar,
    connect,
    connections,
    dashboard,
    link_tokens,
    oauth,
    provider_configs,
    providers,
)

logger = logging.getLogger(__name__)


def _parse_allowed_origin_domains(raw: str) -> list[str]:
    domains = [item.strip().lower() for item in raw.split(",") if item.strip()]
    if not domains:
        domains = ["*"]
    if domains == ["*"]:
        logger.warning(
            "OMNIDAPTER_ALLOWED_ORIGIN_DOMAINS is not configured; "
            "defaulting to '*'. This is permissive and should be restricted in production."
        )
    return domains


def _build_cors_settings(allowed_domain_patterns: list[str]) -> tuple[list[str], str | None, bool]:
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


async def health_endpoint():
    return {"status": "ok", "service": "omnidapter-hosted"}


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "An unexpected error occurred"},
            "meta": {"request_id": request_id},
        },
    )


# For backward compatibility in tests
health = health_endpoint


def create_app(settings: HostedSettings | None = None) -> FastAPI:
    """Create and configure the Omnidapter Hosted FastAPI application."""
    app = FastAPI(
        title="Omnidapter Hosted",
        description="Multi-tenant hosted API with billing and team management",
        version="0.1.0",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    if settings is None:
        settings = get_hosted_settings()

    # Override server's auth with hosted auth (resolves tenant + rate limits)
    app.dependency_overrides[_server_get_auth_context] = get_hosted_auth_context
    app.dependency_overrides[_server_get_settings] = lambda: settings
    app.dependency_overrides[get_hosted_settings] = lambda: settings

    # Middleware
    app.add_middleware(RequestIdMiddleware)

    if settings:
        allowed_domain_patterns = _parse_allowed_origin_domains(
            settings.omnidapter_allowed_origin_domains
        )
        cors_origins, allow_origin_regex, allow_credentials = _build_cors_settings(
            allowed_domain_patterns
        )

        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins,
            allow_origin_regex=allow_origin_regex,
            allow_credentials=allow_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    # Auth — WorkOS login/callback, JWT-based /me, stateless logout
    app.include_router(auth.router, prefix="/v1")

    # Dashboard — JWT Bearer auth, all management UI routes
    app.include_router(dashboard.router, prefix="/v1")

    # Integration API — omni_* API key auth
    app.include_router(connections.router, prefix="/v1")
    app.include_router(calendar.router, prefix="/v1")
    app.include_router(provider_configs.router, prefix="/v1")

    # Provider management — API key auth
    app.include_router(providers.router, prefix="/v1")

    # Link token issuance — API key auth
    app.include_router(link_tokens.router, prefix="/v1")

    # Connect UI — link token auth
    app.include_router(connect.router)

    # OAuth callback (stateless, state-validated)
    app.include_router(oauth.router)

    app.get("/health")(health_endpoint)
    app.exception_handler(Exception)(unhandled_exception_handler)

    return app


# Default app instance for backward compatibility
app = create_app()


def run() -> None:
    import uvicorn

    settings = get_hosted_settings()
    uvicorn.run(
        "omnidapter_hosted.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
