"""Shared API response formatting utilities."""

from __future__ import annotations


def wrap_response(data: object, request_id: str) -> dict:
    if isinstance(data, list):
        return {
            "data": [
                item.model_dump(mode="json") if hasattr(item, "model_dump") else item
                for item in data
            ],
            "meta": {"request_id": request_id},
        }
    if hasattr(data, "model_dump"):
        return {"data": data.model_dump(mode="json"), "meta": {"request_id": request_id}}  # type: ignore[union-attr]
    return {"data": data, "meta": {"request_id": request_id}}
