"""Provider metadata endpoints."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from omnidapter import Omnidapter

from omnidapter_server.config import Settings, get_settings
from omnidapter_server.dependencies import AuthContext, get_auth_context, get_request_id
from omnidapter_server.provider_registry import build_provider_registry

router = APIRouter(prefix="/providers", tags=["providers"])


def _build_omni(settings: Settings) -> Omnidapter:
    return Omnidapter(registry=build_provider_registry(settings))


def _provider_to_dict(meta: Any) -> dict:
    return {
        "provider_key": meta.provider_key,
        "display_name": meta.display_name,
        "services": [s.value for s in meta.services],
        "auth_kinds": [a.value for a in meta.auth_kinds],
        "capabilities": meta.capabilities,
        "connection_config_fields": [
            {"name": f.name, "description": f.description, "required": f.required}
            for f in meta.connection_config_fields
        ],
    }


@router.get("")
async def list_providers(
    request: Request,
    auth: Annotated[AuthContext, Depends(get_auth_context)],
    settings: Annotated[Settings, Depends(get_settings)],
    request_id: str = Depends(get_request_id),
):
    omni = _build_omni(settings)
    providers = [_provider_to_dict(omni.describe_provider(key)) for key in omni.list_providers()]
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
    try:
        meta = omni.describe_provider(provider_key)
    except KeyError as exc:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "provider_not_found",
                "message": f"Provider {provider_key!r} not found",
            },
        ) from exc

    return {"data": _provider_to_dict(meta), "meta": {"request_id": request_id}}
