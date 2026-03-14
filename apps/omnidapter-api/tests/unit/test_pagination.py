"""Unit tests for pagination logic."""

from __future__ import annotations


def paginate(items: list, limit: int = 50, offset: int = 0) -> dict:
    """Simple pagination helper used in responses."""
    total = len(items)
    page = items[offset : offset + limit]
    return {
        "data": page,
        "meta": {
            "pagination": {
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
            }
        },
    }


def test_default_pagination():
    items = list(range(100))
    result = paginate(items)
    assert len(result["data"]) == 50
    assert result["meta"]["pagination"]["total"] == 100
    assert result["meta"]["pagination"]["has_more"] is True
    assert result["meta"]["pagination"]["offset"] == 0


def test_custom_limit():
    items = list(range(100))
    result = paginate(items, limit=10)
    assert len(result["data"]) == 10
    assert result["meta"]["pagination"]["has_more"] is True


def test_offset_pagination():
    items = list(range(100))
    result = paginate(items, limit=10, offset=90)
    assert len(result["data"]) == 10
    assert result["meta"]["pagination"]["has_more"] is False


def test_empty_results():
    items = []
    result = paginate(items)
    assert result["data"] == []
    assert result["meta"]["pagination"]["total"] == 0
    assert result["meta"]["pagination"]["has_more"] is False


def test_last_page_no_more():
    items = list(range(20))
    result = paginate(items, limit=10, offset=10)
    assert len(result["data"]) == 10
    assert result["meta"]["pagination"]["has_more"] is False


def test_offset_beyond_total():
    items = list(range(10))
    result = paginate(items, limit=10, offset=100)
    assert result["data"] == []
    assert result["meta"]["pagination"]["has_more"] is False


def test_single_item():
    items = ["only"]
    result = paginate(items, limit=50, offset=0)
    assert result["data"] == ["only"]
    assert result["meta"]["pagination"]["total"] == 1
    assert result["meta"]["pagination"]["has_more"] is False
