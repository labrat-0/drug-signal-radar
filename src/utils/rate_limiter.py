from __future__ import annotations

import asyncio
import json
import logging
import random

logger = logging.getLogger(__name__)

FREE_TIER_LIMIT = 25
GLOBAL_RATE_INTERVAL = 2.0  # 0.5 req/sec = 2.0 sec between requests
MAX_RETRIES = 5
RETRYABLE_STATUS_CODES = {429, 500, 502, 503}


class RateLimiter:
    """Global token bucket -- one instance shared across ALL four sources.

    Enforces 0.5 req/sec (2.0s interval) using asyncio.Lock to serialize
    concurrent callers. Do NOT create per-source instances.
    """

    def __init__(self, interval: float = GLOBAL_RATE_INTERVAL) -> None:
        self._interval = interval
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        async with self._lock:
            loop = asyncio.get_event_loop()
            now = loop.time()
            elapsed = now - self._last_request
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_request = asyncio.get_event_loop().time()


async def fetch_with_backoff(
    client: object,
    url: str,
    limiter: RateLimiter,
    params: dict | None = None,
    max_retries: int = MAX_RETRIES,
) -> dict | None:
    """Fetch JSON with rate limiting and exponential backoff.

    Backoff schedule: 1s, 2s, 4s, 8s, 16s (capped at 15s) + jitter.
    Returns None on 404 or after all retries exhausted.
    Raises on unexpected non-retryable errors.
    """
    for attempt in range(max_retries + 1):
        await limiter.wait()
        try:
            response = await client.get(url, params=params, timeout=30.0)  # type: ignore[union-attr]
            if response.status_code == 200:
                return response.json()
            if response.status_code == 404:
                return None
            if response.status_code in RETRYABLE_STATUS_CODES:
                delay = min(15.0, 1.0 * (2**attempt))
                jitter = random.uniform(0, 0.5)
                logger.warning(
                    "HTTP %d on %s. Retrying in %.1fs (attempt %d/%d)",
                    response.status_code,
                    url,
                    delay + jitter,
                    attempt + 1,
                    max_retries,
                )
                await asyncio.sleep(delay + jitter)
                continue
            logger.warning("Unexpected HTTP %d from %s", response.status_code, url)
            return None
        except json.JSONDecodeError as e:
            delay = min(15.0, 1.0 * (2**attempt))
            jitter = random.uniform(0, 0.5)
            # Log response details for debugging
            resp_text = response.text[:200] if response else "No response object"
            resp_status = response.status_code if response else "N/A"
            logger.warning(
                "Invalid JSON response from %s (status=%s, body_sample=%r). "
                "Retrying in %.1fs (attempt %d/%d)",
                url,
                resp_status,
                resp_text,
                delay + jitter,
                attempt + 1,
                max_retries,
            )
            await asyncio.sleep(delay + jitter)
            continue
        except asyncio.TimeoutError:
            delay = min(20.0, 2.0 * (attempt + 1))
            logger.warning("Timeout fetching %s. Retrying in %ds", url, delay)
            await asyncio.sleep(delay)

    logger.error("All %d retries exhausted for %s", max_retries + 1, url)
    return None
