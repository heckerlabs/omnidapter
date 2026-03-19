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
from omnidapter_server.routers import providers

from omnidapter_hosted.config import get_hosted_settings
from omnidapter_hosted.dependencies import get_hosted_auth_context
from omnidapter_hosted.routers import (
    api_keys,
    calendar,
    connections,
    memberships,
    oauth,
    provider_configs,
    tenants,
    users,
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


app = FastAPI(
    title="Omnidapter Hosted",
    description="Multi-tenant hosted API with billing and team management",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Override server's auth with hosted auth (resolves tenant + rate limits)
app.dependency_overrides[_server_get_auth_context] = get_hosted_auth_context
app.dependency_overrides[_server_get_settings] = get_hosted_settings

# Middleware
app.add_middleware(RequestIdMiddleware)
settings = get_hosted_settings()
allowed_domain_patterns = _parse_allowed_origin_domains(settings.omnidapter_allowed_origin_domains)
cors_origins, allow_origin_regex, allow_credentials = _build_cors_settings(allowed_domain_patterns)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server router that is metadata-only and does not expose tenant resources
app.include_router(providers.router, prefix="/v1")

# Hosted routers (tenant-scoped)
app.include_router(tenants.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(memberships.router, prefix="/v1")
app.include_router(api_keys.router, prefix="/v1")
app.include_router(provider_configs.router, prefix="/v1")
app.include_router(connections.router, prefix="/v1")
app.include_router(calendar.router, prefix="/v1")
app.include_router(oauth.router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "omnidapter-hosted"}


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "req_unknown")
    return JSONResponse(
        status_code=500,
        content={
            "error": {"code": "internal_error", "message": "An unexpected error occurred"},
            "meta": {"request_id": request_id},
        },
    )


def run() -> None:
    import uvicorn

    settings = get_hosted_settings()
    uvicorn.run(
        "omnidapter_hosted.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
