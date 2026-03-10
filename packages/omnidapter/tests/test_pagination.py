"""
Unit tests for pagination utilities.
"""

from omnidapter.services.calendar.pagination import Page, iter_pages


class TestPage:
    def test_page_with_items(self):
        page = Page(items=["a", "b", "c"], next_page_token="token_2")
        assert page.items == ["a", "b", "c"]
        assert page.next_page_token == "token_2"

    def test_page_without_next_token(self):
        page = Page(items=["x"], next_page_token=None)
        assert page.next_page_token is None


class TestIterPages:
    async def test_single_page(self):
        async def fetch(token):
            return Page(items=["a", "b"], next_page_token=None)

        results = []
        async for item in iter_pages(fetch):
            results.append(item)

        assert results == ["a", "b"]

    async def test_multiple_pages(self):
        pages = [
            Page(items=[1, 2], next_page_token="p2"),
            Page(items=[3, 4], next_page_token="p3"),
            Page(items=[5], next_page_token=None),
        ]
        page_index = [0]

        async def fetch(token):
            idx = page_index[0]
            page_index[0] += 1
            return pages[idx]

        results = []
        async for item in iter_pages(fetch):
            results.append(item)

        assert results == [1, 2, 3, 4, 5]

    async def test_empty_page(self):
        async def fetch(token):
            return Page(items=[], next_page_token=None)

        results = []
        async for item in iter_pages(fetch):
            results.append(item)

        assert results == []
