"""Provider metadata endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from omnidapter import Omnidapter

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.dependencies import AuthContext, get_auth_context, get_request_id
from omnidapter_server.provider_registry import build_provider_registry
from omnidapter_server.services.provider_metadata_flows import (
    get_provider_flow,
    list_providers_flow,
)

router = APIRouter(prefix="/providers", tags=["providers"])


def _build_omni(settings: Settings) -> Omnidapter:
    return Omnidapter(registry=build_provider_registry(settings))


@router.get("")
async def list_providers(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: str = Depends(get_request_id),
):
    omni = _build_omni(settings)
    providers = list_providers_flow(omni)
    return {"data": providers, "meta": {"request_id": request_id}}


@router.get("/{provider_key}")
async def get_provider(
    provider_key: str,
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: str = Depends(get_request_id),
):
    omni = _build_omni(settings)
    return {"data": get_provider_flow(omni, provider_key), "meta": {"request_id": request_id}}
