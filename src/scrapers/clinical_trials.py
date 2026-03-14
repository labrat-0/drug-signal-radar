from __future__ import annotations

import logging
from typing import AsyncGenerator

import httpx
from apify import Actor

from src.models import ClinicalTrialRecord, ScraperInput
from src.utils.rate_limiter import RateLimiter, fetch_with_backoff

logger = logging.getLogger(__name__)

CLINICALTRIALS_URL = "https://clinicaltrials.gov/api/v2/studies"
PAGE_SIZE = 100  # ClinicalTrials.gov v2 max pageSize is 1000; 100 is safe default


class ClinicalTrialsFetcher:
    """Fetches clinical trials from ClinicalTrials.gov API v2.

    Uses pageNumber + pageSize pagination.
    Note: ClinicalTrials.gov rate limits are not precisely documented (~10 req/sec).
    Global 0.5 req/sec from RateLimiter is well within any observed limit.

    Yields ClinicalTrialRecord for each valid trial.
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

        # Warn if unsupported filters provided
        if config.severity_threshold:
            Actor.log.warning(
                f"severityThreshold='{config.severity_threshold}' is not applicable "
                "to ClinicalTrials. Filtering FAERS only."
            )

    async def fetch(self) -> AsyncGenerator[ClinicalTrialRecord, None]:
        """Async generator yielding ClinicalTrialRecord instances."""
        page_number = 1
        fetched = 0

        await Actor.set_status_message("ClinicalTrials: fetching trials...")

        while fetched < self.config.max_results:
            limit = min(PAGE_SIZE, self.config.max_results - fetched)
            params: dict = {
                "query.term": self.config.drug_name,
                "pageSize": limit,
                "pageNumber": page_number,
                "format": "json",
            }

            # Date filtering via query term (ClinicalTrials v2 date filter via lastUpdatePostDate)
            # For broader date range, embed in query term as "AREA[LastUpdatePostDate]RANGE[from,to]"
            if self.config.date_from:
                date_from = self.config.date_from  # Already ISO 8601
                params["filter.lastUpdatePostDate"] = f"RANGE[{date_from},MAX]"
            if self.config.date_to:
                date_from_part = self.config.date_from or "MIN"
                params["filter.lastUpdatePostDate"] = (
                    f"RANGE[{date_from_part},{self.config.date_to}]"
                )

            data = await fetch_with_backoff(
                self.client, CLINICALTRIALS_URL, self.rate_limiter, params
            )

            if not data:
                break

            studies = data.get("studies", [])
            if not studies:
                Actor.log.info(f"ClinicalTrials: no results on page {page_number}")
                break

            for study in studies:
                try:
                    record = self._parse_study(study)
                    yield record
                    fetched += 1
                    self.state["trials_count"] = self.state.get("trials_count", 0) + 1
                    self.state["scraped"] = self.state.get("scraped", 0) + 1
                except Exception as e:
                    nct_id = self._safe_get_nct(study)
                    Actor.log.warning(
                        f"ClinicalTrials: skipping study nctId={nct_id}: {e}"
                    )
                    self.state["trials_failed"] = self.state.get("trials_failed", 0) + 1
                    self.state["failed"] = self.state.get("failed", 0) + 1

            # Check if more pages exist
            total = data.get("totalCount", 0)
            if fetched >= total or len(studies) < limit:
                break  # Last page

            page_number += 1

        await Actor.set_status_message(
            f"ClinicalTrials: complete ({fetched} trials)"
        )

    def _parse_study(self, study: dict) -> ClinicalTrialRecord:
        """Parse a ClinicalTrials.gov v2 study JSON dict into ClinicalTrialRecord."""
        protocol = study.get("protocolSection", {})
        identification = protocol.get("identificationModule", {})
        status_module = protocol.get("statusModule", {})
        design_module = protocol.get("designModule", {})

        trial_id = identification.get("nctId", "")
        title = identification.get("briefTitle", "")
        status = status_module.get("overallStatus", "")

        # Phase is a list in v2 (e.g., ["PHASE1", "PHASE2"])
        phases = design_module.get("phases", [])
        phase = ", ".join(phases) if phases else "N/A"

        # Enrollment
        enrollment_info = design_module.get("enrollmentInfo", {})
        enrollment_raw = enrollment_info.get("count")
        enrollment = int(enrollment_raw) if enrollment_raw is not None else None

        return ClinicalTrialRecord(
            trial_id=trial_id,
            title=title,
            status=status,
            phase=phase,
            enrollment=enrollment,
        )

    def _safe_get_nct(self, study: dict) -> str:
        try:
            return study["protocolSection"]["identificationModule"]["nctId"]
        except Exception:
            return "unknown"
