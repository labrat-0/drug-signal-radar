from __future__ import annotations

import logging
from typing import AsyncGenerator

import httpx
from apify import Actor

from src.models import FDAEnforcementRecord, ScraperInput
from src.utils.rate_limiter import RateLimiter, fetch_with_backoff

logger = logging.getLogger(__name__)

ENFORCEMENT_URL = "https://api.fda.gov/drug/enforcement.json"
PAGE_SIZE = 100  # openFDA max per request


class FDAEnforcementFetcher:
    """Fetches FDA drug enforcement alerts via openFDA /drug/enforcement.json.

    Uses same openFDA pagination pattern as FAERS (skip + limit).
    Note: openFDA skip limit is 25000.

    Yields FDAEnforcementRecord for each valid enforcement alert.
    Skips malformed records (logs warning, increments failed count).
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        rate_limiter: RateLimiter,
        config: ScraperInput,
        state: dict,
    ) -> None:
        self.client = client
        self.rate_limiter = rate_limiter
        self.config = config
        self.state = state

        # Warn for inapplicable filters
        if config.severity_threshold:
            Actor.log.warning(
                f"severityThreshold='{config.severity_threshold}' is not applicable "
                "to FDA Enforcement. Filtering FAERS only."
            )

    def _build_search_query(self) -> str:
        """Build openFDA search query for drug enforcement records."""
        # Search by brand_name or product_description containing drug name
        parts = [f'product_description:"{self.config.drug_name}"']

        if self.config.date_from or self.config.date_to:
            date_from = (self.config.date_from or "19900101").replace("-", "")
            date_to = (self.config.date_to or "20991231").replace("-", "")
            parts.append(f"report_date:[{date_from}+TO+{date_to}]")

        return "+AND+".join(parts)

    async def fetch(self) -> AsyncGenerator[FDAEnforcementRecord, None]:
        """Async generator yielding FDAEnforcementRecord instances."""
        search_query = self._build_search_query()
        skip = 0
        fetched = 0

        await Actor.set_status_message("FDA Enforcement: fetching alerts...")

        while fetched < self.config.max_results:
            limit = min(PAGE_SIZE, self.config.max_results - fetched)
            params = {
                "search": search_query,
                "limit": limit,
                "skip": skip,
            }

            data = await fetch_with_backoff(
                self.client, ENFORCEMENT_URL, self.rate_limiter, params
            )

            if not data:
                break  # 404 (no results for drug) or all retries exhausted

            results = data.get("results", [])
            if not results:
                break

            for raw in results:
                try:
                    record = self._parse_record(raw)
                    yield record
                    fetched += 1
                    self.state["enforcement_count"] = self.state.get("enforcement_count", 0) + 1
                    self.state["scraped"] = self.state.get("scraped", 0) + 1
                except Exception as e:
                    recall_num = raw.get("recall_number", "unknown")
                    Actor.log.warning(
                        f"FDA Enforcement: skipping alert recall_number={recall_num}: {e}"
                    )
                    self.state["enforcement_failed"] = (
                        self.state.get("enforcement_failed", 0) + 1
                    )
                    self.state["failed"] = self.state.get("failed", 0) + 1

            skip += len(results)
            if skip >= 25000 or len(results) < limit:
                break  # openFDA skip limit or last page

        await Actor.set_status_message(
            f"FDA Enforcement: complete ({fetched} alerts)"
        )

    def _parse_record(self, raw: dict) -> FDAEnforcementRecord:
        """Parse a single openFDA enforcement JSON dict into FDAEnforcementRecord."""
        alert_id = str(raw.get("recall_number", ""))
        if not alert_id:
            # Fall back to event_id if recall_number missing
            alert_id = str(raw.get("event_id", "unknown"))

        # voluntary_mandated: "Voluntary: Firm initiated" or "FDA Mandated"
        # Use as action_type; fall back to classification if missing
        action_type = raw.get("voluntary_mandated", raw.get("classification", ""))

        description = raw.get("product_description", "")

        # report_date: YYYYMMDD -> ISO 8601
        report_raw = raw.get("report_date", "")
        report_date = self._to_iso_date(str(report_raw))

        return FDAEnforcementRecord(
            alert_id=alert_id,
            action_type=action_type,
            description=description,
            report_date=report_date,
        )

    def _to_iso_date(self, raw: str) -> str:
        """Convert YYYYMMDD string to ISO 8601 YYYY-MM-DD. Returns '' on failure."""
        raw = raw.strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return ""
