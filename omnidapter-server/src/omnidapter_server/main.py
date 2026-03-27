"""Omnidapter Server — FastAPI application."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from omnidapter_server.config import get_settings
from omnidapter_server.middleware.request_id import RequestIdMiddleware
from omnidapter_server.origin_policy import build_cors_settings, parse_allowed_origin_domains
from omnidapter_server.routers import (
    calendar,
    connect,
    connections,
    link_tokens,
    oauth,
    provider_configs,
    providers,
)

logger = logging.getLogger(__name__)


async def _sync_managed_api_key() -> None:
    """Ensure managed API key exists (and rotates if changed)."""
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from omnidapter_server.config import get_settings
    from omnidapter_server.models.api_key import APIKey
    from omnidapter_server.services.auth import hash_api_key, verify_api_key

    settings = get_settings()
    raw_key = settings.omnidapter_api_key.strip()

    if settings.omnidapter_auth_mode == "required" and not raw_key:
        raise RuntimeError("OMNIDAPTER_API_KEY is required when OMNIDAPTER_AUTH_MODE=required")

    if not raw_key:
        return

    key_prefix = raw_key[:12]
    engine = create_async_engine(settings.omnidapter_database_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with factory() as session:
            result = await session.execute(
                select(APIKey)
                .where(APIKey.name.in_(("managed", "initial")))
                .order_by(APIKey.created_at.desc())
            )
            existing = result.scalars().first()

            if existing is not None and verify_api_key(raw_key, existing.key_hash):
                if not existing.is_active:
                    existing.is_active = True
                    await session.commit()
                return

            import uuid

            if existing is None:
                api_key = APIKey(
                    id=uuid.uuid4(),
                    name="managed",
                    key_hash=hash_api_key(raw_key),
                    key_prefix=key_prefix,
                    is_active=True,
                )
                session.add(api_key)
                await session.commit()
                logger.info("Seeded managed API key (prefix=%s)", key_prefix)
            else:
                existing.name = "managed"
                existing.key_hash = hash_api_key(raw_key)
                existing.key_prefix = key_prefix
                existing.is_active = True
                await session.commit()
                logger.info("Rotated managed API key (prefix=%s)", key_prefix)
    finally:
        await engine.dispose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await _sync_managed_api_key()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Omnidapter Server",
    description="Self-hosted REST API wrapping the Omnidapter calendar integration library",
    version="0.3.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
app.add_middleware(RequestIdMiddleware)

settings = get_settings()
allowed_domain_patterns = parse_allowed_origin_domains(settings.omnidapter_allowed_origin_domains)
cors_origins, allow_origin_regex, allow_credentials = build_cors_settings(allowed_domain_patterns)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(providers.router, prefix="/v1")
app.include_router(provider_configs.router, prefix="/v1")
app.include_router(connections.router, prefix="/v1")
app.include_router(calendar.router, prefix="/v1")
app.include_router(link_tokens.router, prefix="/v1")
app.include_router(connect.router)  # /connect is not under /v1
app.include_router(oauth.router)  # /oauth is not under /v1


@app.get("/health")
async def health():
    return {"status": "ok"}


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

    settings = get_settings()
    uvicorn.run(
        "omnidapter_server.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
