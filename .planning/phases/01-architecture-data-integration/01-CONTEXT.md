# Phase 1: Architecture & Data Integration - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Build async infrastructure to fetch raw data from four public health APIs (PubMed via NCBI E-utilities, FAERS via openFDA, ClinicalTrials.gov API v2, FDA enforcement alerts via openFDA), coordinate concurrent requests with rate limiting and exponential backoff retry logic, validate user inputs, and push batched results to Apify dataset. By end of phase, users can query any drug and retrieve raw data from all four sources without rate limit errors.

</domain>

<decisions>
## Implementation Decisions

### Concurrency & Parallelism
- **Strategy:** All four sources fetch in parallel concurrently
- **Failure mode:** If any source fails (timeout, API error, network), fail the entire actor run with clear error message. All-or-nothing ensures user gets complete drug signal intelligence or knows to retry.
- **Timeout:** Global timeout for entire fetch phase (not per-source). When any source reaches global timeout, abort that source and fail the run if it hasn't completed yet.
- **Connection initialization:** Claude's Discretion — researcher will decide between independent initialization, staggered starts, or shared httpx.AsyncClient based on initial profiling. Goal: minimal setup overhead without overwhelming initial API load.

### Rate Limiting & API Coordination
- **Strategy:** Single global rate limit of 0.5 req/sec across all four sources combined
  - Conservative approach accounts for unknown rate limits (ClinicalTrials.gov limits flagged as research dependency)
  - Prevents cascading overload across heterogeneous APIs
  - Can be tuned upward in Phase 2 if initial profiling shows headroom
- **Exponential backoff on 429 errors:** 1s → 2s → 4s, max 5 retries (per API-02 requirement)

### Input Filters & Adaptation
- **Filter application:** All optional filters (dateFrom, dateTo, severityThreshold, maxResults) apply uniformly across all four sources
  - dateFrom/dateTo: interpret consistently (ISO 8601 range applied to publication/report dates in each source)
  - severityThreshold: applies directly to FAERS (has severity field); other sources: ignored (documented in logs)
  - maxResults: enforced globally across aggregated output
- **Unsupported filter handling:** Warn user in logs ("severityThreshold not applicable to PubMed; filtering FAERS only") and proceed. Best-effort filtering for each source based on its schema.
- **Free tier limit:** Enforce APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING check; cap maxResults at 25 for free users (consistent with pubmed-scraper and fda-adverse-events-scraper pattern)

### Claude's Discretion

These areas planner decides during Phase 1 planning:
- **Batch pushing strategy:** Push-as-you-go per source vs. aggregate-then-push? Planner will evaluate trade-offs between latency (push early) vs. throughput (aggregate efficiently)
- **Progress reporting granularity:** What status messages user sees (per-source progress, timeline, failure counts)? Researcher will identify best pattern from existing actors.
- **Global timeout duration:** Exact timeout value (e.g., 5 minutes, 10 minutes?) based on typical query complexity
- **Error logging detail:** How much failure context to preserve in state (partial failure records for debugging vs. minimal state)

</decisions>

<code_context>
## Existing Code Insights

### Reusable Assets
- **PubMed fetcher:** `pubmed-scraper/src/scrapers/pubmed.py` — NCBI E-utilities fetching logic. Reuse with async wrapper around existing httpx.get() calls.
- **FAERS fetcher:** `fda-adverse-events-scraper/src/scrapers/faers.py` — openFDA API fetching. Reuse directly; already handles openFDA response format.
- **Rate limiter utility:** `fda-adverse-events-scraper/src/utils.py` — RateLimiter class (token bucket or similar). Adapt for global coordination across 4 sources.
- **Actor input pattern:** Both existing actors use `ScraperInput.from_actor_input()` and `config.validate_for_mode()`. Reuse pattern for Phase 1 input validation.
- **Free tier check:** Both actors implement the same pattern — check `APIFY_IS_AT_HOME` + `APIFY_USER_IS_PAYING`. Reuse directly.

### Established Patterns
- **Pydantic models:** Both actors define strict schema models in `models.py`. Follow same pattern for ScraperInput + per-source models.
- **Async with Actor context manager:** Standard Apify SDK pattern in both. Reuse `async with Actor:` and `Actor.get_input()`, `Actor.set_status_message()`, `Actor.use_state()`, `Actor.push_data()`.
- **httpx.AsyncClient for HTTP:** Both use async client for rate-limited fetching. Leverage for Phase 1's concurrent requests.
- **State tracking:** Both use `Actor.use_state(default_value={"scraped": 0, "failed": 0})`. Expand for Phase 1 to track per-source state.
- **Logging via Actor.log:** Consistent throughout. Use for phase progress and filter warnings.

### Integration Points
- **Entry point:** `src/main.py` will instantiate all four fetchers, coordinate concurrent tasks, apply global rate limiting, and collect results.
- **Fetchers:** `src/scrapers/pubmed.py`, `src/scrapers/faers.py`, `src/scrapers/clinicaltrials.py`, `src/scrapers/fda_enforcement.py` — each source isolated.
- **Models:** `src/models.py` defines ScraperInput, per-source record models (PubMedRecord, FAERSRecord, etc.), and unified output schema.
- **Rate limiter:** `src/utils/rate_limiter.py` — global token bucket, shared across all concurrent fetchers.
- **Apify metadata:** `.actor/input_schema.json` — defines input parameters (drugName, dateFrom, dateTo, severityThreshold, maxResults) and defaults.

</code_context>

<specifics>
## Specific Ideas

- Actor should expose clear progress messages per source (e.g., "PubMed: fetching... ✓ 45 papers | FAERS: fetching... | ClinicalTrials: pending | FDA: pending")
- Free tier message from existing actors is good model: "Free tier: limited to 25 results. Subscribe for unlimited."
- Reuse existing error handling patterns (fail with `Actor.fail(status_message=...)`) rather than reinventing

</specifics>

<deferred>
## Deferred Ideas

- Multi-source signal correlation (detect same drug across sources, boost risk score) — Phase 2+
- Adaptive rate limiting (self-tune based on response codes) — Phase 1.x enhancement
- Per-source timeout (kill slow sources but continue others) — reconsidered; full-parallel with global timeout is simpler for v1
- Source credibility weighting — Phase 1.x+

</deferred>

---

*Phase: 01-architecture-data-integration*
*Context gathered: 2026-03-14*
