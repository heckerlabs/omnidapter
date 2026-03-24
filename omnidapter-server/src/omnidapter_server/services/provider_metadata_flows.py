"""Shared provider metadata flows."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from omnidapter import Omnidapter


def provider_to_dict(meta: Any) -> dict:
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


def list_providers_flow(omni: Omnidapter) -> list[dict]:
    return [provider_to_dict(omni.describe_provider(key)) for key in omni.list_providers()]


def get_provider_flow(omni: Omnidapter, provider_key: str) -> dict:
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
    return provider_to_dict(meta)
