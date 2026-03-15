"""Unit tests for pagination logic."""

from __future__ import annotations

from omnidapter_api.pagination import build_pagination_meta


def test_default_pagination():
    meta = build_pagination_meta(total=100, limit=50, offset=0)
    assert meta["total"] == 100
    assert meta["has_more"] is True
    assert meta["offset"] == 0


def test_custom_limit():
    meta = build_pagination_meta(total=100, limit=10, offset=0)
    assert meta["limit"] == 10
    assert meta["has_more"] is True


def test_offset_pagination():
    meta = build_pagination_meta(total=100, limit=10, offset=90)
    assert meta["has_more"] is False


def test_empty_results():
    meta = build_pagination_meta(total=0, limit=50, offset=0)
    assert meta["total"] == 0
    assert meta["has_more"] is False


def test_last_page_no_more():
    meta = build_pagination_meta(total=20, limit=10, offset=10)
    assert meta["has_more"] is False


def test_offset_beyond_total():
    meta = build_pagination_meta(total=10, limit=10, offset=100)
    assert meta["has_more"] is False


def test_single_item():
    meta = build_pagination_meta(total=1, limit=50, offset=0)
    assert meta["total"] == 1
    assert meta["has_more"] is False
