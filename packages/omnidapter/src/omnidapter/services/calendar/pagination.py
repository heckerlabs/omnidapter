"""
Pagination utilities for calendar list operations.
"""
from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    """A single page of results with an optional next-page token."""
    items: list[T]
    next_page_token: str | None = None

    model_config = {"arbitrary_types_allowed": True}


async def iter_pages(
    fetch_page,
    *,
    initial_page_token: str | None = None,
) -> AsyncIterator:
    """Async generator that iterates over all pages using a fetch_page callable.

    Args:
        fetch_page: Async callable(page_token) -> Page
        initial_page_token: Starting page token (None for first page).

    Yields:
        Individual items from each page.
    """
    page_token = initial_page_token
    while True:
        page = await fetch_page(page_token)
        for item in page.items:
            yield item
        if page.next_page_token is None:
            break
        page_token = page.next_page_token
