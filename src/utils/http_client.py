from __future__ import annotations

import httpx

DEFAULT_HEADERS = {
    "User-Agent": "DrugSignalRadar/0.1 (Apify Actor; contact: actor@apify.com)",
    "Accept": "application/json",
}


def create_http_client(timeout: float = 30.0) -> httpx.AsyncClient:
    """Create a single shared httpx.AsyncClient.

    IMPORTANT: Call once in main(), pass to all fetchers.
    Do NOT create per-fetcher clients -- defeats connection pooling.
    """
    return httpx.AsyncClient(
        headers=DEFAULT_HEADERS,
        timeout=httpx.Timeout(timeout),
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        follow_redirects=True,
    )
