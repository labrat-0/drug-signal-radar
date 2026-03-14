from __future__ import annotations
import asyncio
import logging
from apify import Actor
from src.models import ScraperInput, SourceStatus, SourceState
from src.utils.rate_limiter import RateLimiter, GLOBAL_RATE_INTERVAL
from src.utils.http_client import create_http_client
from src.scrapers.pubmed import PubMedFetcher
from src.scrapers.faers import FAERSFetcher
from src.scrapers.clinical_trials import ClinicalTrialsFetcher
from src.scrapers.fda_enforcement import FDAEnforcementFetcher

logger = logging.getLogger(__name__)

BATCH_SIZE = 25
# Semaphore(2): max 2 sources running concurrently.
# Rationale: 4 sources x 100 records with abstracts could spike memory.
# Semaphore(2) keeps peak memory roughly equivalent to 2 single-source actors.
# Can be tuned upward in Phase 1.x after profiling (see RESEARCH.md open questions).
MAX_CONCURRENT_SOURCES = 2


async def run_aggregator(config: ScraperInput, state: dict) -> None:
    """
    Orchestrates concurrent multi-source drug data fetching.

    Strategy:
    1. Create ONE shared RateLimiter and ONE shared httpx.AsyncClient
    2. Run all four fetchers under asyncio.gather with Semaphore(2) bounding concurrency
    3. Collect ALL records from ALL sources before pushing (aggregate-then-push)
    4. If any source raises (all retries exhausted), fail entire run (all-or-nothing)
    5. Push all collected records in 25-record batches via Actor.push_data()

    Args:
        config: validated ScraperInput from Actor.get_input()
        state: persistent state dict from Actor.use_state()
    """
    shared_limiter = RateLimiter(interval=GLOBAL_RATE_INTERVAL)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_SOURCES)
    source_statuses: list[SourceStatus] = []

    async with create_http_client() as client:
        # Instantiate all four fetchers with shared resources
        fetchers = [
            ("pubmed", PubMedFetcher(client, shared_limiter, config, state)),
            ("faers", FAERSFetcher(client, shared_limiter, config, state)),
            ("clinicaltrials", ClinicalTrialsFetcher(client, shared_limiter, config, state)),
            ("fda_enforcement", FDAEnforcementFetcher(client, shared_limiter, config, state)),
        ]

        # Collect results: each bounded_fetch returns (source_name, records, status)
        async def bounded_fetch(
            source_name: str,
            fetcher,
        ) -> tuple[str, list, SourceStatus]:
            async with semaphore:
                records: list = []
                try:
                    Actor.log.info(f"{source_name}: starting fetch")
                    async for record in fetcher.fetch():
                        records.append(record.model_dump())
                    status = SourceStatus(
                        source=source_name,
                        state=SourceState.SUCCESS,
                        records_fetched=len(records),
                        records_failed=state.get(f"{source_name}_failed", 0),
                    )
                    Actor.log.info(
                        f"{source_name}: complete ({len(records)} records)"
                    )
                except Exception as e:
                    # Source failed after all retries. Per locked decision: fail entire run.
                    Actor.log.error(
                        f"{source_name}: FAILED after all retries: {type(e).__name__}: {e}"
                    )
                    status = SourceStatus(
                        source=source_name,
                        state=SourceState.FAILED,
                        records_fetched=len(records),
                        records_failed=state.get(f"{source_name}_failed", 0),
                        error_message=f"{type(e).__name__}: {e}",
                    )
                    # Re-raise so asyncio.gather propagates failure
                    raise

                return (source_name, records, status)

        # Run all four fetchers concurrently; raise immediately if any fails
        # return_exceptions=False means first exception cancels remaining tasks
        try:
            results = await asyncio.gather(
                *[bounded_fetch(name, fetcher) for name, fetcher in fetchers],
                return_exceptions=False,
            )
        except Exception as e:
            # All-or-nothing: one source failed -> fail entire actor
            await Actor.fail(
                status_message=(
                    f"Source fetch failed: {e}. "
                    "All sources must succeed for complete drug signal intelligence. "
                    "Retry or check logs for details."
                )
            )
            return

        # All sources succeeded -- collect all records
        all_records: list[dict] = []
        for source_name, records, status in results:
            source_statuses.append(status)
            all_records.extend(records)
            Actor.log.info(
                f"{source_name}: {status.records_fetched} records, "
                f"{status.records_failed} failed"
            )

        # Update final state
        state["scraped"] = len(all_records)

        # Push all records in 25-record batches (aggregate-then-push strategy)
        await Actor.set_status_message(
            f"Pushing {len(all_records)} records to dataset..."
        )
        await _push_batches(all_records)

        # Push source status metadata as a summary record
        summary_record = {
            "_type": "aggregation_summary",
            "drug_name": config.drug_name,
            "total_records": len(all_records),
            "sources": [s.model_dump() for s in source_statuses],
        }
        await Actor.push_data([summary_record])

        Actor.log.info(
            f"Aggregation complete: {len(all_records)} records from "
            f"{len(results)} sources pushed to dataset."
        )


async def _push_batches(records: list[dict]) -> None:
    """Push records to Apify dataset in batches of BATCH_SIZE (25)."""
    batch: list[dict] = []
    pushed_total = 0

    for record in records:
        batch.append(record)
        if len(batch) >= BATCH_SIZE:
            await Actor.push_data(batch)
            pushed_total += len(batch)
            await Actor.set_status_message(
                f"Pushing records: {pushed_total}/{len(records)}"
            )
            batch = []

    # Push remaining records
    if batch:
        await Actor.push_data(batch)
        pushed_total += len(batch)
