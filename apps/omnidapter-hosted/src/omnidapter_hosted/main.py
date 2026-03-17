"""Omnidapter Hosted — multi-tenant FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

# Import server's auth dependency so we can override it
from omnidapter_server.dependencies import get_auth_context as _server_get_auth_context
from omnidapter_server.middleware.request_id import RequestIdMiddleware
from omnidapter_server.routers import calendar, connections, oauth, provider_configs, providers

from omnidapter_hosted.dependencies import get_hosted_auth_context
from omnidapter_hosted.routers import api_keys, memberships, tenants, users

app = FastAPI(
    title="Omnidapter Hosted",
    description="Multi-tenant hosted API with billing and team management",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Override server's auth with hosted auth (resolves tenant + rate limits)
app.dependency_overrides[_server_get_auth_context] = get_hosted_auth_context

# Middleware
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Server routers that don't need tenant scoping (use as-is with overridden auth)
app.include_router(providers.router, prefix="/v1")
app.include_router(provider_configs.router, prefix="/v1")
app.include_router(oauth.router)

# Hosted routers (tenant-scoped)
app.include_router(tenants.router, prefix="/v1")
app.include_router(users.router, prefix="/v1")
app.include_router(memberships.router, prefix="/v1")
app.include_router(api_keys.router, prefix="/v1")

# NOTE: connections and calendar routes use the server implementation with overridden auth.
# Full tenant-scoped connection routing is a planned enhancement.
app.include_router(connections.router, prefix="/v1")
app.include_router(calendar.router, prefix="/v1")


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

    uvicorn.run("omnidapter_hosted.main:app", host="0.0.0.0", port=8000, reload=True)
