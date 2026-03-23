"""Unit tests for common response schemas."""

from __future__ import annotations

from omnidapter_server.schemas.common import (
    ApiResponse,
    ErrorDetail,
    ErrorResponse,
    ListMeta,
    ListResponse,
    PaginationMeta,
    RequestMeta,
)


def test_common_response_models() -> None:
    pagination = PaginationMeta(total=10, limit=5, offset=0, has_more=True)
    list_meta = ListMeta(request_id="req_1", pagination=pagination)
    list_response = ListResponse(data=["a", "b"], meta=list_meta)
    single = ApiResponse(data={"ok": True}, meta=RequestMeta(request_id="req_2"))
    err = ErrorResponse(
        error=ErrorDetail(code="bad_request", message="nope", details={"field": "name"}),
        meta=RequestMeta(request_id="req_3"),
    )

    assert list_response.meta.pagination.total == 10
    assert single.data["ok"] is True
    assert err.error.code == "bad_request"
