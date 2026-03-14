from __future__ import annotations

import asyncio
import os
import logging
from apify import Actor
from src.models import ScraperInput
from src.utils.rate_limiter import FREE_TIER_LIMIT

GLOBAL_TIMEOUT_SECONDS = 600  # 10 minutes for entire fetch phase

logger = logging.getLogger(__name__)


async def main() -> None:
    async with Actor:
        # 1. Read and parse input
        raw_input = await Actor.get_input() or {}
        config = ScraperInput.from_actor_input(raw_input)

        # 2. Validate input; fail fast on invalid
        validation_error = config.validate_for_mode()
        if validation_error:
            await Actor.fail(status_message=validation_error)
            return

        # 3. Free tier enforcement
        # Pattern: APIFY_IS_AT_HOME="1" means running on Apify platform
        # APIFY_USER_IS_PAYING="1" means paid tier; anything else = free
        is_on_platform = os.environ.get("APIFY_IS_AT_HOME") == "1"
        is_paying = os.environ.get("APIFY_USER_IS_PAYING") == "1"
        if is_on_platform and not is_paying:
            config.max_results = min(config.max_results, FREE_TIER_LIMIT)
            Actor.log.info(
                f"Free tier: results capped at {FREE_TIER_LIMIT} per source. "
                "Subscribe for unlimited results."
            )

        # 4. Initialize per-source state
        state = await Actor.use_state(default_value={
            "scraped": 0,
            "failed": 0,
            "pubmed_count": 0,
            "pubmed_failed": 0,
            "faers_count": 0,
            "faers_failed": 0,
            "trials_count": 0,
            "trials_failed": 0,
            "enforcement_count": 0,
            "enforcement_failed": 0,
        })

        # 5. Signal startup
        await Actor.set_status_message(
            f"Starting drug signal query for '{config.drug_name}'. "
            "Fetching from PubMed, FAERS, ClinicalTrials, FDA Enforcement..."
        )

        # 6. Run aggregator within global timeout
        # Aggregator is imported here to avoid circular imports and
        # so this file remains testable without aggregator implemented.
        try:
            from src.aggregator import run_aggregator
            await asyncio.wait_for(
                run_aggregator(config, state),
                timeout=GLOBAL_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            await Actor.fail(
                status_message=(
                    f"Fetch exceeded {GLOBAL_TIMEOUT_SECONDS // 60} min global timeout. "
                    f"Query '{config.drug_name}' may be too broad. "
                    "Retry with narrower dateFrom/dateTo range or lower maxResults."
                )
            )
            return

        await Actor.set_status_message(
            f"Complete. Fetched {state['scraped']} records "
            f"({state['pubmed_count']} papers, {state['faers_count']} adverse events, "
            f"{state['trials_count']} trials, {state['enforcement_count']} alerts)."
        )


if __name__ == "__main__":
    asyncio.run(main())
