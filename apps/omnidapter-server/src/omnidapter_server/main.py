"""Omnidapter Server — FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from omnidapter_server.config import get_settings
from omnidapter_server.middleware.request_id import RequestIdMiddleware
from omnidapter_server.origin_policy import build_cors_settings, parse_allowed_origin_domains
from omnidapter_server.routers import calendar, connections, oauth, provider_configs, providers

app = FastAPI(
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
