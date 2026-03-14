from __future__ import annotations

import logging
from typing import AsyncGenerator

import httpx
from apify import Actor

from src.models import FAERSRecord, ScraperInput
from src.utils.rate_limiter import RateLimiter, fetch_with_backoff

logger = logging.getLogger(__name__)

FAERS_URL = "https://api.fda.gov/drug/event.json"
FAERS_PAGE_SIZE = 100  # openFDA max per request


class FAERSFetcher:
    """Fetches FAERS adverse event reports via openFDA /drug/event.json.

    Supports:
    - Drug name search (medicinalproduct field)
    - Date range filtering (receiptdate)
    - Severity filtering (serious=1 for 'serious_only')
    - Pagination via skip + limit

    Yields FAERSRecord for each valid report.
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

    def _build_search_query(self) -> str:
        """Build openFDA search query string."""
        parts = [f'patient.drug.medicinalproduct:"{self.config.drug_name}"']

        # Date range: openFDA uses YYYYMMDD format
        if self.config.date_from or self.config.date_to:
            date_from = (self.config.date_from or "19900101").replace("-", "")
            date_to = (self.config.date_to or "20991231").replace("-", "")
            parts.append(f"receiptdate:[{date_from}+TO+{date_to}]")

        # Severity filter
        if self.config.severity_threshold == "serious_only":
            parts.append("serious:1")

        return "+AND+".join(parts)

    async def fetch(self) -> AsyncGenerator[FAERSRecord, None]:
        """Async generator yielding FAERSRecord instances."""
        search_query = self._build_search_query()
        skip = 0
        fetched = 0

        await Actor.set_status_message("FAERS: fetching adverse events...")

        while fetched < self.config.max_results:
            limit = min(FAERS_PAGE_SIZE, self.config.max_results - fetched)
            params = {
                "search": search_query,
                "limit": limit,
                "skip": skip,
            }

            data = await fetch_with_backoff(
                self.client, FAERS_URL, self.rate_limiter, params
            )

            if not data:
                break  # No more results or error

            results = data.get("results", [])
            if not results:
                break  # Empty page = done

            for raw in results:
                try:
                    record = self._parse_record(raw)
                    yield record
                    fetched += 1
                    self.state["faers_count"] = self.state.get("faers_count", 0) + 1
                    self.state["scraped"] = self.state.get("scraped", 0) + 1
                except Exception as e:
                    event_id = raw.get("safetyreportid", "unknown")
                    Actor.log.warning(
                        f"FAERS: skipping report safetyreportid={event_id}: {e}"
                    )
                    self.state["faers_failed"] = self.state.get("faers_failed", 0) + 1
                    self.state["failed"] = self.state.get("failed", 0) + 1

            # openFDA max skip is 25000
            skip += len(results)
            if skip >= 25000 or len(results) < limit:
                break  # Hit openFDA pagination limit or last page

        await Actor.set_status_message(f"FAERS: complete ({fetched} adverse events)")

    def _parse_record(self, raw: dict) -> FAERSRecord:
        """Parse a single openFDA FAERS event JSON dict into FAERSRecord."""
        event_id = str(raw.get("safetyreportid", ""))

        # Primary reaction: first entry in reactions list
        reactions = raw.get("patient", {}).get("reaction", [])
        reaction = reactions[0].get("reactionmeddrapt", "") if reactions else ""

        # Serious flag: openFDA serious field is "1" (serious) or "2" (not serious)
        serious_raw = raw.get("serious", "2")
        serious_flag = str(serious_raw) == "1"

        # Receipt date: YYYYMMDD -> ISO 8601 YYYY-MM-DD
        receipt_raw = raw.get("receiptdate", "")
        report_date = self._to_iso_date(receipt_raw)

        # Patient age: raw value + unit (age unit codes: 800=decade, 801=year, etc.)
        patient = raw.get("patient", {})
        age = str(patient.get("patientonsetage", ""))
        age_unit_code = str(patient.get("patientonsetageunit", ""))
        age_unit = {
            "800": "decade",
            "801": "year",
            "802": "month",
            "803": "week",
            "804": "day",
            "805": "hour",
        }.get(age_unit_code, "")
        patient_age = f"{age} {age_unit}".strip() if age else ""

        return FAERSRecord(
            event_id=event_id,
            reaction=reaction,
            serious_flag=serious_flag,
            report_date=report_date,
            patient_age=patient_age,
        )

    def _to_iso_date(self, raw: str) -> str:
        """Convert YYYYMMDD string to ISO 8601 YYYY-MM-DD. Returns '' on failure."""
        raw = str(raw).strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"
        return ""
