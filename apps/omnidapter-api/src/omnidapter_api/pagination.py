"""Pagination helpers for API responses."""

from __future__ import annotations


def build_pagination_meta(total: int, limit: int, offset: int) -> dict[str, int | bool]:
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": (offset + limit) < total,
    }
