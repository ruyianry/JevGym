from __future__ import annotations

from datetime import datetime, timezone

import httpx
import respx

from jevgym.tools.search import (
    MockSearch,
    SearchResult,
    WaybackSearch,
    enforce_as_of,
)

UTC = timezone.utc
AS_OF = datetime(2026, 1, 10, tzinfo=UTC)


def test_enforce_as_of_drops_future_keeps_undated():
    rs = [
        SearchResult(title="past", url="u1", published_at=datetime(2026, 1, 1, tzinfo=UTC)),
        SearchResult(title="future", url="u2", published_at=datetime(2026, 2, 1, tzinfo=UTC)),
        SearchResult(title="undated", url="u3"),
    ]
    kept = {r.title for r in enforce_as_of(rs, AS_OF)}
    assert kept == {"past", "undated"}


def test_mock_search_and_fetch():
    ms = MockSearch(
        results=[SearchResult(title="a", url="u", published_at=datetime(2026, 1, 1, tzinfo=UTC))],
        pages={"u": "body text"},
    )
    assert ms.search("q", AS_OF)[0].title == "a"
    assert ms.fetch("u", AS_OF) == "body text"


@respx.mock
def test_wayback_fetch_returns_snapshot_at_or_before_as_of():
    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(
            200,
            json=[
                ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                ["k", "20260105120000", "https://example.com/x", "text/html", "200", "d", "100"],
            ],
        )
    )
    respx.get(url__regex=r"web\.archive\.org/web/").mock(
        return_value=httpx.Response(200, text="<html><body>Hello <b>world</b></body></html>")
    )
    text = WaybackSearch().fetch("https://example.com/x", AS_OF)
    assert text and "Hello world" in text


@respx.mock
def test_wayback_rejects_snapshot_after_as_of():
    # Only a post-as_of snapshot exists -> must return None (client-side leakage guard).
    respx.get("https://web.archive.org/cdx/search/cdx").mock(
        return_value=httpx.Response(
            200,
            json=[
                ["urlkey", "timestamp", "original", "mimetype", "statuscode", "digest", "length"],
                ["k", "20260201000000", "https://example.com/x", "text/html", "200", "d", "100"],
            ],
        )
    )
    assert WaybackSearch().fetch("https://example.com/x", AS_OF) is None
