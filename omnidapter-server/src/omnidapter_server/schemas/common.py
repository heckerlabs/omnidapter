"""Common response envelope schemas."""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class EventPaginationMeta(BaseModel):
    limit: int
    offset: int
    count: int
    has_more: bool


class RequestMeta(BaseModel):
    request_id: str


class ListMeta(RequestMeta):
    pagination: PaginationMeta


class EventListMeta(RequestMeta):
    pagination: EventPaginationMeta


class ApiResponse(BaseModel, Generic[T]):
    data: T
    meta: RequestMeta


class ListResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: ListMeta


class EventListResponse(BaseModel, Generic[T]):
    data: list[T]
    meta: EventListMeta


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    error: ErrorDetail
    meta: RequestMeta
