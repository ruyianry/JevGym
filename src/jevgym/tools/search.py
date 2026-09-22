"""Time-bounded ("as-of") web search + fetch.

The crux of an honest historical-replay benchmark: when an agent gathers evidence, it must
see only what was public **at the snapshot timestamp** — never the future. Every result and
fetched page is bounded by ``as_of``:

* ``WaybackSearch`` — fetches the closest Internet Archive snapshot **at or before** ``as_of``
  (via the CDX API), so page *content* is leakage-safe and needs no API key.
* ``DatedWebSearch`` — SERP with a max-date filter (needs ``SEARCH_API_KEY``) for *discovery*;
  content fetch delegates to Wayback so it stays as-of-correct.
* ``MockSearch`` — deterministic canned results for offline runs/tests.

``enforce_as_of`` is the final guard: any result whose ``published_at`` postdates ``as_of``
is dropped, no matter the backend.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

import httpx

from ..models.base import JevBaseModel
from ..util import ensure_utc, parse_dt


def _parse_wayback_ts(ts_raw: str) -> datetime | None:
    """Wayback timestamps are ``YYYYMMDDhhmmss`` — parse explicitly (never as unix epoch)."""
    try:
        return datetime.strptime(ts_raw[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


class SearchResult(JevBaseModel):
    title: str
    url: str
    snippet: str = ""
    published_at: datetime | None = None  # None = unknown date
    source: str = ""  # backend that produced it
    content: str | None = None  # populated by fetch()


def enforce_as_of(results: list[SearchResult], as_of: datetime | None) -> list[SearchResult]:
    """Drop any result known to postdate ``as_of`` (undated results are kept)."""
    if as_of is None:
        return results
    cutoff = ensure_utc(as_of)
    return [r for r in results if r.published_at is None or ensure_utc(r.published_at) <= cutoff]


@runtime_checkable
class TimeBoundedSearch(Protocol):
    name: str

    def search(self, query: str, as_of: datetime, k: int = 5) -> list[SearchResult]: ...

    def fetch(self, url: str, as_of: datetime) -> str | None: ...


def _strip_html(html: str, limit: int = 6000) -> str:
    text = re.sub(r"(?is)<(script|style).*?</\1>", " ", html)
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


class MockSearch:
    """Deterministic offline search. Provide canned results keyed loosely by substring."""

    name = "mock"

    def __init__(self, results: list[SearchResult] | None = None, pages: dict[str, str] | None = None):
        self._results = results or []
        self._pages = pages or {}

    def search(self, query: str, as_of: datetime, k: int = 5) -> list[SearchResult]:
        return enforce_as_of(list(self._results), as_of)[:k]

    def fetch(self, url: str, as_of: datetime) -> str | None:
        return self._pages.get(url)


class WaybackSearch:
    """Internet Archive fetcher. Leakage-safe: content comes from the newest snapshot at or
    before ``as_of`` (CDX ``to`` filter). No general full-text discovery, so ``search`` is a
    no-op — pair with a discovery backend, or have the agent fetch known URLs."""

    name = "wayback"
    CDX = "https://web.archive.org/cdx/search/cdx"

    def __init__(self, client: httpx.Client | None = None, timeout: float = 30.0):
        self._client = client
        self._owns = client is None
        self._timeout = timeout

    def _c(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)
        return self._client

    def search(self, query: str, as_of: datetime, k: int = 5) -> list[SearchResult]:
        return []  # Wayback has no full-text search; use DatedWebSearch or fetch() a URL.

    def _closest_snapshot(self, url: str, as_of: datetime) -> tuple[str, datetime] | None:
        to = ensure_utc(as_of).strftime("%Y%m%d%H%M%S")
        resp = self._c().get(
            self.CDX,
            params={
                "url": url,
                "to": to,
                "output": "json",
                "filter": "statuscode:200",
                "limit": "-5",  # newest-first, a few candidates
            },
        )
        resp.raise_for_status()
        rows = resp.json()
        if not rows or len(rows) < 2:
            return None
        # rows[0] is the header; take the newest data row whose timestamp <= as_of.
        for row in rows[1:]:
            ts_raw, original = row[1], row[2]
            snap_dt = _parse_wayback_ts(ts_raw)
            if snap_dt is not None and snap_dt <= ensure_utc(as_of):
                snap_url = f"https://web.archive.org/web/{ts_raw}id_/{original}"
                return snap_url, snap_dt
        return None

    def fetch(self, url: str, as_of: datetime) -> str | None:
        found = self._closest_snapshot(url, as_of)
        if not found:
            return None
        snap_url, _ = found
        resp = self._c().get(snap_url)
        if resp.status_code != 200:
            return None
        return _strip_html(resp.text)


class DatedWebSearch:
    """SERP discovery with a max-date filter (SerpAPI-style), content via Wayback.

    Requires ``api_key``. ``search`` returns results filtered to on/before ``as_of``; ``fetch``
    delegates to :class:`WaybackSearch` so page content is always as-of-correct.
    """

    name = "serp"
    ENDPOINT = "https://serpapi.com/search.json"

    def __init__(self, api_key: str, client: httpx.Client | None = None, timeout: float = 30.0):
        self.api_key = api_key
        self._client = client
        self._owns = client is None
        self._timeout = timeout
        self._wayback = WaybackSearch(client=client, timeout=timeout)

    def _c(self) -> httpx.Client:
        if self._client is None:
            self._client = httpx.Client(timeout=self._timeout, follow_redirects=True)
            self._wayback._client = self._client
        return self._client

    def search(self, query: str, as_of: datetime, k: int = 5) -> list[SearchResult]:
        cd_max = ensure_utc(as_of).strftime("%m/%d/%Y")
        resp = self._c().get(
            self.ENDPOINT,
            params={
                "engine": "google",
                "q": query,
                "num": k,
                "tbs": f"cdr:1,cd_max:{cd_max}",  # custom date range, on/before as_of
                "api_key": self.api_key,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        out: list[SearchResult] = []
        for item in (data.get("organic_results") or [])[:k]:
            out.append(
                SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    snippet=item.get("snippet", ""),
                    published_at=parse_dt(item.get("date")),
                    source=self.name,
                )
            )
        return enforce_as_of(out, as_of)

    def fetch(self, url: str, as_of: datetime) -> str | None:
        return self._wayback.fetch(url, as_of)


SEARCH_PROVIDERS = {
    "mock": MockSearch,
    "wayback": WaybackSearch,
    "serp": DatedWebSearch,
}


def build_search(settings, *, client: httpx.Client | None = None) -> TimeBoundedSearch:
    """Pick a backend from settings. 'serp' falls back to Wayback if no key is set."""
    provider = (settings.search_provider or "wayback").lower()
    if provider == "serp":
        if not settings.search_api_key:
            return WaybackSearch(client=client)  # graceful fallback: fetch-only, no key needed
        return DatedWebSearch(settings.search_api_key, client=client)
    if provider == "mock":
        return MockSearch()
    return WaybackSearch(client=client)


def render_results(results: list[SearchResult]) -> str:
    if not results:
        return "(no results)"
    lines = []
    for i, r in enumerate(results, 1):
        when = r.published_at.strftime("%Y-%m-%d") if r.published_at else "date unknown"
        lines.append(f"[{i}] {r.title} ({when})\n    {r.url}\n    {r.snippet}")
    return "\n".join(lines)
