"""Omnidapter Hosted API — FastAPI application."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from omnidapter_api.middleware.request_id import RequestIdMiddleware
from omnidapter_api.routers import calendar, connections, oauth, provider_configs, providers, usage

app = FastAPI(
    title="Omnidapter API",
    description="Managed REST API wrapping the Omnidapter calendar integration library",
    version="0.2.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Middleware
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Tighten in production to dashboard domain
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(providers.router, prefix="/v1")
app.include_router(provider_configs.router, prefix="/v1")
app.include_router(connections.router, prefix="/v1")
app.include_router(calendar.router, prefix="/v1")
app.include_router(oauth.router)  # /oauth is not under /v1
app.include_router(usage.router, prefix="/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.middleware("http")
async def add_rate_limit_headers(request: Request, call_next):
    response = await call_next(request)
    rate_limit = getattr(request.state, "rate_limit", None)
    if rate_limit:
        response.headers.setdefault("X-RateLimit-Limit", str(rate_limit.get("limit", "")))
        response.headers.setdefault("X-RateLimit-Remaining", str(rate_limit.get("remaining", "")))
        response.headers.setdefault("X-RateLimit-Reset", str(rate_limit.get("reset", "")))
    return response


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

    uvicorn.run("omnidapter_api.main:app", host="0.0.0.0", port=8000, reload=True)
