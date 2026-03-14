# src/aggregator.py — stub replaced by Plan 05
from __future__ import annotations
from src.models import ScraperInput


async def run_aggregator(config: ScraperInput, state: dict) -> None:
    """Stub: Plan 05 implements the full aggregation pipeline."""
    from apify import Actor
    Actor.log.warning("Aggregator stub: no data fetched yet. Implement Plan 05.")
