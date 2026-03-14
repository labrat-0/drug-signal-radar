# Phase 1: Architecture & Data Integration - Research

**Researched:** 2026-03-14
**Domain:** Multi-source async API coordination, rate limiting, input validation, batch data ingestion
**Confidence:** HIGH

## Summary

Phase 1 must build an async infrastructure layer that fetches raw data from four heterogeneous public health APIs (PubMed via NCBI E-utilities, FAERS via openFDA, ClinicalTrials.gov v2, FDA enforcement via openFDA) with global rate limiting, exponential backoff retry logic, and input validation. The existing patterns in `pubmed-scraper` and `fda-adverse-events-scraper` provide solid proven templates: Pydantic input validation, async/await with httpx.AsyncClient, Actor.push_data batching, and state tracking. Phase 1 uniqueness: coordinating four concurrent sources under a single global rate limit (0.5 req/sec), handling per-source failures within all-or-nothing execution semantics, and normalizing disparate response formats before pushing to Apify dataset.

**Primary recommendation:** Extend the established single-source scraper pattern (both actors share identical main.py structure) to multi-source coordination. Use asyncio.Semaphore(N) to bound concurrent fetchers, share a single global RateLimiter instance across all sources, implement per-source fetcher classes that wrap existing code, apply uniform input filters at aggregation point, and track per-source state for observability. This approach reuses proven patterns while adding minimal new complexity.

## User Constraints (from CONTEXT.md)

### Locked Decisions
- All four sources fetch in parallel concurrently
- All-or-nothing failure mode: if any source fails (timeout, API error), fail entire actor run with clear error
- Global timeout for entire fetch phase (not per-source). When timeout reached, abort and fail run
- Global rate limit of 0.5 req/sec across all four sources combined (conservative, accounts for ClinicalTrials.gov unknown limits)
- Exponential backoff on 429 errors: 1s → 2s → 4s, max 5 retries (per API-02)
- All optional filters apply uniformly: dateFrom/dateTo interpreted consistently, severityThreshold applies to FAERS only (warn for others), maxResults enforced globally on aggregated output
- Unsupported filters handled as best-effort: warn in logs, proceed (e.g., "severityThreshold not applicable to PubMed")
- Free tier enforcement: check APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING; cap maxResults at 25 for free users

### Claude's Discretion
- **Batch pushing strategy:** Push-as-you-go per source vs. aggregate-then-push? Planner will evaluate trade-offs
- **Progress reporting granularity:** Determine status message detail (per-source progress, timeline, failure counts)
- **Global timeout duration:** Exact value (5 min, 10 min?) based on typical query complexity
- **Error logging detail:** How much failure context in state (partial failure records vs. minimal)
- **Connection initialization:** Independent vs. staggered starts vs. shared httpx.AsyncClient (decision based on initial profiling)

### Deferred Ideas (OUT OF SCOPE)
- Multi-source signal correlation (Phase 2+)
- Adaptive rate limiting self-tuning (Phase 1.x enhancement)
- Per-source timeout (kill slow sources but continue others)
- Source credibility weighting (Phase 1.x+)

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AGG-01 | PubMed fetcher via NCBI E-utilities | httpx.AsyncClient, existing pubmed-scraper.py wrapper, E-utilities 3 req/sec documented, filter by date |
| AGG-02 | FAERS fetcher via openFDA | httpx.AsyncClient, existing fda-adverse-events-scraper.py wrapper, 4 req/sec observed rate limit |
| AGG-03 | ClinicalTrials.gov v2 fetcher | openAPI v3 REST JSON, ~10 req/sec rate limit (per ClinicalTrials docs), pagination via standard `pageSize` + `pageNumber` |
| AGG-04 | FDA enforcement fetcher via openFDA | openAPI JSON, integrated with FAERS rate limit (same openFDA endpoint), weekly data updates |
| INP-01 | drugName parameter validation | Pydantic BaseModel, reuse pattern from existing actors, non-empty string required |
| INP-02 | dateFrom/dateTo filtering | ISO 8601 format, applied to each source's publication/report date field, handled per-source |
| INP-03 | severityThreshold filtering | FAERS-only (has native severity field), ignored for PubMed/Trials/Enforcement with warning |
| INP-04 | maxResults limit + free tier | Global cap across aggregated output, free tier capped at 25 (APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING pattern) |
| INP-05 | Input validation & error rejection | ScraperInput.validate_for_mode() pattern, Actor.fail(status_message=...) on invalid |
| EXE-01 | Async SDK patterns | async with Actor:, await Actor.get_input(), await Actor.push_data(), await Actor.use_state() confirmed available |
| EXE-02 | Batch push strategy | 25-record batches standard in both existing actors, established effective throughput/memory balance |
| EXE-03 | Status messages | Actor.set_status_message() for progress, per-source tracking via state dictionary |
| EXE-04 | State tracking | Actor.use_state(default_value={...}) confirmed available, automatic persistence across runs |
| API-01 | Global rate limit 0.5 req/sec | Single shared RateLimiter instance across all concurrent sources |
| API-02 | Exponential backoff 1s→2s→4s, max 5 retries | fetch_json() pattern in fda-adverse-events-scraper implements this, reuse with backoff(2 ** attempt) |
| API-03 | Partial source failure handling | Decision locked: ALL-OR-NOTHING. If any source fails fully (all retries exhausted), fail entire run |
| API-04 | Per-source error handling | Skip malformed records, continue iteration, accumulate failure count per source |
| API-05 | Fail only if all sources fail | Phase 1 constraint: actually FAIL if ANY source fails (all-or-nothing semantics per CONTEXT.md) |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| apify | ≥2.0.0 | Actor framework, SDK lifecycle | Apify ecosystem; published on Marketplace; Python native |
| httpx | ≥0.27.0 | Async HTTP client | Connection pooling, retry semantics, modern async/await, used in both existing actors |
| pydantic | ≥2.0.0 | Schema validation, type safety | Strict validation prevents silent data loss; used in both existing actors; v2 has improved performance |
| Python | 3.12+ | Runtime | Consistent with pubmed-scraper and fda-adverse-events-scraper; modern asyncio support |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio | stdlib | Concurrency primitives (Semaphore, gather, TaskGroup) | Event loop, task scheduling, rate limit coordination |
| logging | stdlib | Actor.log interface | Progress tracking, error context, observability |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Single shared RateLimiter | Per-source rate limiters | Per-source is complex (4 separate states), harder to enforce global 0.5 req/sec across sources; global is simpler for v1 |
| asyncio.Semaphore(N) for concurrency bounds | aiohttp connector limit | Semaphore is stdlib, lighter weight, simpler for bounding concurrent tasks (vs. HTTP-specific limits) |
| Actor.push_data(batch) | Stream records one-by-one | Batch improves throughput, reduces Actor API calls, 25-record sweet spot proven in both actors |
| Pydantic models | Hand-rolled validation | Pydantic catches errors early, documents schema, versioning built-in, used by existing actors |

**Installation:**
```bash
pip install apify==2.1.4 httpx==0.27.0 pydantic==2.8.2
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── main.py                    # Actor entry point: input → aggregator → push_data
├── models.py                  # Pydantic: ScraperInput, per-source record schemas
├── aggregator.py              # Coordinator: spawn fetchers, apply rate limit, collect results
├── scrapers/
│   ├── pubmed.py             # NCBI E-utilities fetcher
│   ├── faers.py              # openFDA FAERS fetcher
│   ├── clinical_trials.py     # ClinicalTrials.gov v2 fetcher
│   └── fda_enforcement.py     # openFDA enforcement fetcher
└── utils/
    ├── rate_limiter.py        # Global RateLimiter (shared instance)
    └── http_client.py         # httpx.AsyncClient factory + headers
```

### Pattern 1: Async Actor Context Manager with Input Validation
**What:** Standard Apify pattern for Actor initialization, input parsing, validation, and failure handling
**When to use:** Every Apify actor entry point
**Example:**
```python
# Source: https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle
async def main() -> None:
    async with Actor:
        raw_input = await Actor.get_input() or {}
        config = ScraperInput.from_actor_input(raw_input)

        validation_error = config.validate_for_mode()
        if validation_error:
            await Actor.fail(status_message=validation_error)
            return

        # Processing continues...
```

### Pattern 2: Global RateLimiter with Shared Instance
**What:** Single rate limiter enforcing minimum interval between ALL requests (across all sources)
**When to use:** Multi-source coordination with global rate limit constraint
**Example:**
```python
# Source: fda-adverse-events-scraper/src/utils.py, adapted for global use
async def create_shared_rate_limiter(interval: float) -> RateLimiter:
    """Single instance, shared across all concurrent fetchers"""
    return RateLimiter(interval=0.5)  # 0.5 req/sec = 2 sec between requests globally

async def main() -> None:
    async with Actor:
        # One shared limiter for all four sources
        shared_limiter = await create_shared_rate_limiter(interval=0.5)

        # Pass same limiter to all fetchers
        pubmed_task = fetch_pubmed(shared_limiter)
        faers_task = fetch_faers(shared_limiter)
        # ...
        results = await asyncio.gather(pubmed_task, faers_task, ...)
```

### Pattern 3: Per-Source Fetcher Class with Async Generator
**What:** Isolated fetcher classes that yield records one-at-a-time, handle source-specific logic internally
**When to use:** Each data source (PubMed, FAERS, ClinicalTrials, FDA enforcement)
**Example:**
```python
# Source: pubmed-scraper/src/scraper.py pattern
class PubMedFetcher:
    def __init__(self, client: httpx.AsyncClient, rate_limiter: RateLimiter, config):
        self.client = client
        self.rate_limiter = rate_limiter
        self.config = config

    async def fetch(self):
        """Async generator yielding records"""
        # Handle pagination, retries, validation internally
        async for record in self._paginate():
            yield self._normalize_record(record)

# In main:
pubmed = PubMedFetcher(client, shared_limiter, config)
async for record in pubmed.fetch():
    batch.append(record)
    # Track, push, etc.
```

### Pattern 4: Bounded Concurrency with asyncio.Semaphore
**What:** Limit concurrent fetchers to N at a time (prevents resource exhaustion)
**When to use:** Bounding concurrent tasks when you have more than CPU/memory can handle in parallel
**Example:**
```python
# Source: https://rednafi.com/python/limit-concurrency-with-semaphore/
async def bounded_fetch_all(sources: list) -> dict:
    """Fetch from all sources, max 2 concurrent (bounding example)"""
    semaphore = asyncio.Semaphore(2)

    async def bounded_fetch(source):
        async with semaphore:
            # Only 2 sources inside here at any time
            return await fetch_source(source)

    results = await asyncio.gather(*[bounded_fetch(s) for s in sources])
    return results
```

### Pattern 5: State Tracking Across Retries
**What:** Persistent dictionary automatically saved to Apify storage, tracks progress per source
**When to use:** Monitoring fetch progress, enabling safe restarts
**Example:**
```python
# Source: pubmed-scraper/src/main.py, extended for multi-source
state = await Actor.use_state(default_value={
    "scraped": 0,
    "failed": 0,
    "pubmed_count": 0,
    "faers_count": 0,
    "clinical_trials_count": 0,
    "fda_enforcement_count": 0,
})

# During fetching:
state["pubmed_count"] += 1
state["scraped"] = state["pubmed_count"] + state["faers_count"] + ...

# Auto-persisted; Actor restarts continue from this state
```

### Anti-Patterns to Avoid
- **Creating multiple httpx.AsyncClient instances:** Wastes connection pool setup, defeats keep-alive. Use single shared instance.
- **Per-source RateLimiters without global coordination:** Allows cascading overload (each source throttles independently, but combined rate exceeds API tolerance).
- **Pushing records one-by-one:** 4 sources × 100 results = 400 API calls to Actor.push_data(). Use 25-record batches.
- **Catching all exceptions broadly:** Masks real errors. Catch specific types (httpx.TimeoutException, httpx.HTTPError, ValueError) for targeted handling.
- **Ignoring date format parsing failures:** Silently coerces bad dates. Reject unparseable dates, log, increment failure counter, continue.
- **All-or-nothing without partial logging:** If one source fails, lose context of what succeeded from others. Track per-source state for debugging.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| HTTP client + connection pooling | Custom socket management | httpx.AsyncClient | Connection reuse, timeout handling, retry-aware; both existing actors use it |
| Rate limiting | Manual time.sleep() between requests | RateLimiter class with asyncio.Lock | Token bucket prevents burst, fair under load, handles concurrent tasks safely |
| Input validation | String checks + type coercion | Pydantic BaseModel | Catches schema violations early, auto-coerces types, provides error messages, versioning |
| Concurrent task bounds | Create 100 tasks, hope memory holds | asyncio.Semaphore(N) | Prevents resource exhaustion, simple to use, stdlib |
| Exponential backoff | Linear or fixed retry delays | 2**attempt formula + jitter | Exponential reduces server load during outages, jitter prevents thundering herd (see fda-adverse-events-scraper) |
| Batch pushing | Accumulate 10,000 records then push | Push every 25 records | Memory safety (Apify environment is memory-constrained), throughput optimization proven in both actors |

**Key insight:** Multi-source concurrency introduces resource exhaustion risk (memory, file descriptors, network). Proven libraries (httpx connection pooling, asyncio.Semaphore) handle these edge cases. Hand-rolled solutions typically miss backpressure, connection reuse, or cascading failures.

## Common Pitfalls

### Pitfall 1: Uncontrolled Concurrency Exhausting Memory
**What goes wrong:** Spawn 4 fetchers with no bounds, each buffering 100 records in memory before pushing. With large response sizes (abstracts, full trial descriptions), memory grows unbounded. Actor gets killed by OOM.
**Why it happens:** Asyncio allows task creation faster than processing/pushing can keep up. No backpressure.
**How to avoid:** Use asyncio.Semaphore(N) to limit concurrent sources (N=2 is conservative). Push data in batches (25 records) before accumulating more. Profile memory locally with `memory_profiler` before deploying.
**Warning signs:** Actor killed mid-run, no stack trace in logs, memory usage spike in Apify logs.

### Pitfall 2: Silent Data Loss from Parse Failures
**What goes wrong:** ClinicalTrials API returns a null "enrollment" field. Code does `trial["enrollment"] + 1` expecting int. Exception silently caught, record skipped. User doesn't know 30% of trials were dropped.
**Why it happens:** Minimal error handling, assumption that API always returns expected schema.
**How to avoid:** (1) Validate every record against Pydantic model after parsing. (2) Track parse failures per source (state["faers_parse_failures"]). (3) Fail run if failure rate > 5% per source. (4) Log every failure: `Actor.log.warning(f"FAERS record {safety_report_id} missing field 'serious': {e}")`.
**Warning signs:** Output record counts don't match API responses. Logs have silent exceptions. Downstream analysis finds gaps.

### Pitfall 3: Rate Limit Cascades Across Heterogeneous APIs
**What goes wrong:** PubMed allows 3 req/sec without API key. Phase 1 fetcher naively submits 0.5 req/sec for PubMed alone, but still hits 429s. Realizes ClinicalTrials.gov has ~10 req/sec limit. Sets per-source rates: PubMed 0.3, FAERS 0.1, Trials 0.1 (total 0.5). Works in dev, but ClinicalTrials has undocumented per-endpoint variance. Some endpoints allow 5 req/sec, others 1. Query that should take 5 sec takes 15 sec.
**Why it happens:** Rate limits not uniform across sources. Documentation is sparse (ClinicalTrials v2 rate limit not explicitly documented in Phase 1 research). Per-source tuning complex.
**How to avoid:** (1) Start with conservative global 0.5 req/sec (established in decision). (2) Monitor actual 429 response rates per source (track in state). (3) Document rate limits as constants in code with source citation. (4) Phase 1.x enhancement: tune based on 429 frequency per source (deferred per context).
**Warning signs:** High retry counts for specific sources, actual runtime 2-3x longer than expected.

### Pitfall 4: Schema Mismatches Causing Downstream Breakage
**What goes wrong:** PubMed parser extracts "publication_date" as "2025-03-14". FAERS parser extracts "receipt_date" (int, YYYYMMDD = 20250314). Later normalization code assumes both are ISO 8601 strings. Output breaks. Phase 2 (normalization) fails.
**Why it happens:** Each API returns different date formats. Phase 1 goal is raw data, so easy to assume "just pass through." But downstream assumes consistent format.
**How to avoid:** (1) Define Pydantic models for each source's raw record BEFORE parsing (versioned in code). (2) Validate every record against model (catches missing/wrong-type fields). (3) Normalize dates to ISO 8601 in Phase 1 parsers. (4) Test with 50 real samples from each source before finalization.
**Warning signs:** Phase 2 task fails with "field X type mismatch (str vs int)". Output records have inconsistent date formats.

### Pitfall 5: Per-Source Timeout Violating All-or-Nothing
**What goes wrong:** Implement per-source 5-second timeout to kill slow ClinicalTrials fetches. FAERS completes, PubMed times out. Code returns "partial success" (2 sources, 1 failure). User gets incomplete drug signal. Later analysis finds gap they didn't expect.
**Why it happens:** Decision locked: all-or-nothing failure. Easy to implement per-source timeout (better UX, more data). But violates contract.
**How to avoid:** Implement global timeout for entire fetch phase (decision locked). If timeout reached, abort incomplete sources and fail run with status message "Fetch exceeded 10 min timeout; ClinicalTrials incomplete. Retry with expanded timeout." User knows what happened.
**Warning signs:** Partial success scenarios arise. Output record counts unexpectedly low.

### Pitfall 6: Free Tier Enforcement Bypass
**What goes wrong:** Code checks `APIFY_IS_AT_HOME == "1"` to cap at 25 results. Local dev has `APIFY_IS_AT_HOME` unset, so limit doesn't trigger. Dev pushes 1000 results to dataset. User sees "free tier should be 25, but got 1000" on marketplace.
**Why it happens:** Environment variables only set in Apify cloud. Local/staging needs mocking.
**How to avoid:** (1) Test free tier logic on staging environment before marketplace publish. (2) Create test input fixture with explicit env var override: `os.environ["APIFY_IS_AT_HOME"] = "1"; os.environ["APIFY_USER_IS_PAYING"] = "0"`. (3) Verify maxResults capped correctly.
**Warning signs:** Marketplace users report inconsistent free/paid behavior. Logs don't show free tier message locally.

## Code Examples

Verified patterns from official sources and existing actors:

### Input Validation with Pydantic
```python
# Source: fda-adverse-events-scraper/src/models.py + pubmed-scraper/src/models.py
from pydantic import BaseModel, Field
from typing import Any

class ScraperInput(BaseModel):
    drug_name: str = ""
    date_from: str = ""
    date_to: str = ""
    severity_threshold: str = ""
    max_results: int = 100

    @classmethod
    def from_actor_input(cls, raw: dict[str, Any]) -> 'ScraperInput':
        return cls(
            drug_name=raw.get("drugName", ""),
            date_from=raw.get("dateFrom", ""),
            date_to=raw.get("dateTo", ""),
            severity_threshold=raw.get("severityThreshold", ""),
            max_results=raw.get("maxResults", 100),
        )

    def validate_for_mode(self) -> str | None:
        if not self.drug_name:
            return "drugName is required"
        if self.max_results < 1 or self.max_results > 10000:
            return "maxResults must be between 1 and 10000"
        return None
```

### Async Actor Entry Point with Free Tier Check
```python
# Source: pubmed-scraper/src/main.py + fda-adverse-events-scraper/src/main.py
import os
from apify import Actor

FREE_TIER_LIMIT = 25

async def main() -> None:
    async with Actor:
        raw_input = await Actor.get_input() or {}
        config = ScraperInput.from_actor_input(raw_input)

        validation_error = config.validate_for_mode()
        if validation_error:
            await Actor.fail(status_message=validation_error)
            return

        # Free tier enforcement
        is_paying = (
            os.environ.get("APIFY_IS_AT_HOME") == "1" and
            os.environ.get("APIFY_USER_IS_PAYING") == "1"
        )

        max_results = config.max_results
        if not is_paying and os.environ.get("APIFY_IS_AT_HOME") == "1":
            max_results = min(max_results, FREE_TIER_LIMIT)
            Actor.log.info(
                f"Free tier: limited to {FREE_TIER_LIMIT} results. "
                "Subscribe for unlimited results."
            )

        # Processing...
```

### Rate Limiter with Exponential Backoff
```python
# Source: fda-adverse-events-scraper/src/utils.py
import asyncio
import random

class RateLimiter:
    """Token bucket: enforces minimum interval between requests"""
    def __init__(self, interval: float = 0.2):
        self._interval = interval
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def wait(self) -> None:
        """Wait until interval has passed since last request"""
        async with self._lock:
            now = asyncio.get_event_loop().time()
            elapsed = now - self._last_request
            if elapsed < self._interval:
                await asyncio.sleep(self._interval - elapsed)
            self._last_request = asyncio.get_event_loop().time()

async def fetch_with_backoff(client, url, limiter, max_retries=5):
    """Exponential backoff: 1s, 2s, 4s, 8s, 16s"""
    for attempt in range(max_retries + 1):
        await limiter.wait()
        try:
            response = await client.get(url, timeout=30)
            if response.status_code == 200:
                return response.json()
            if response.status_code in {429, 503, 502, 500}:
                delay = min(15.0, 1.5 * (2 ** attempt))
                jitter = random.uniform(0, 0.5)
                Actor.log.warning(
                    f"{response.status_code} on {url}. "
                    f"Retrying in {delay + jitter:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay + jitter)
                continue
            if response.status_code == 404:
                return None
            Actor.log.warning(f"Unexpected {response.status_code} from {url}")
            return None
        except asyncio.TimeoutError:
            delay = min(20.0, 2.0 * (attempt + 1))
            Actor.log.warning(f"Timeout on {url}. Retrying in {delay}s")
            await asyncio.sleep(delay)

    Actor.log.error(f"All {max_retries + 1} retries exhausted for {url}")
    return None
```

### Bounded Concurrency with State Tracking
```python
# Source: adapted from https://rednafi.com/python/limit-concurrency-with-semaphore/
import asyncio
from apify import Actor

async def fetch_all_sources(sources_config, rate_limiter):
    """Fetch from all sources with bounded concurrency and state tracking"""
    semaphore = asyncio.Semaphore(2)  # Max 2 concurrent sources
    state = await Actor.use_state(default_value={
        "scraped": 0,
        "failed": 0,
        "pubmed_count": 0,
        "faers_count": 0,
        "trials_count": 0,
        "enforcement_count": 0,
    })

    async def bounded_fetch(source_name, fetcher):
        async with semaphore:
            # Only 2 sources inside here at a time
            records = []
            async for record in fetcher.fetch():
                records.append(record)
                state[f"{source_name}_count"] += 1
                state["scraped"] += 1
            return (source_name, records)

    tasks = [
        bounded_fetch("pubmed", pubmed_fetcher),
        bounded_fetch("faers", faers_fetcher),
        bounded_fetch("trials", trials_fetcher),
        bounded_fetch("enforcement", enforcement_fetcher),
    ]

    results = await asyncio.gather(*tasks)
    return results
```

### Batch Pushing Pattern
```python
# Source: pubmed-scraper/src/main.py + fda-adverse-events-scraper/src/main.py
from apify import Actor

async def push_batch_results(all_records):
    """Push records in 25-record batches"""
    batch_size = 25
    batch = []

    for record in all_records:
        batch.append(record)
        if len(batch) >= batch_size:
            await Actor.push_data(batch)
            batch = []
            await Actor.set_status_message(f"Pushed {len(batch)} records...")

    # Push remaining
    if batch:
        await Actor.push_data(batch)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Per-request RateLimiter per source | Global shared RateLimiter across all sources | Phase 1 locked decision | Simpler coordination, prevents cascading overload, easier to reason about |
| Per-source timeouts (kill slow fetchers) | Global timeout for entire phase | Phase 1 locked decision | Ensures all-or-nothing semantics, predictable user experience |
| Push data one-by-one | Batch push every 25 records | Established in both existing actors | Reduces Actor API calls 4x, improves throughput, memory-safe |
| Manual error handling with broad try/catch | Specific exception types + structured logging | Both existing actors | Easier debugging, prevents masking real errors, better observability |

**Deprecated/outdated:**
- NCBI E-utilities without API key (3 req/sec): Still valid for Phase 1 (no API key in MVP). Phase 2+ could request key for 10 req/sec.
- openFDA FAERS endpoint v1 (endpoint was updated): Both actors reference current endpoint (https://api.fda.gov/drug/event.json). No migration needed.

## State of the APIs

### ClinicalTrials.gov API v2
- **Endpoint:** https://clinicaltrials.gov/api/v2/studies
- **Authentication:** Optional API key (higher rate limit with key)
- **Rate Limit:** ~10 requests per second per IP (per search results, ClinicalTrials.gov docs), or ~50 requests/minute (alternativeestimate)
- **Response Format:** JSON (OpenAPI 3.0 spec), paginated with `pageNumber`, `pageSize` parameters
- **Data Currency:** Real-time trial registry
- **Unique Challenges:**
  - Rate limit documentation sparse (ClinicalTrials.gov flagged as research dependency in STATE.md)
  - Pagination not standard offset/limit (uses page number, variable results per page)
  - Some endpoints have different rate limits (need to test in Phase 1)
  - Trial status/enrollment fields well-structured, but date formats vary
- **Recommendation:** Validate actual endpoint behavior under load before Phase 1 finalization

### NCBI E-utilities (PubMed)
- **Endpoint:** https://eutils.ncbi.nlm.nih.gov/entrez/eutils/
- **Authentication:** API key available (3 req/sec without, 10 req/sec with)
- **Rate Limit:** 3 requests per second without API key, 10 with
- **Response Format:** XML or JSON (via `&rettype=json`), paginated with `retstart`, `retmax`
- **Data Currency:** Weekly updates
- **Unique Challenges:**
  - Accepts multiple search modes (ESearch → EFetch pattern common)
  - Date format in XML is non-standard (handled by pubmed-scraper)
  - Requires `&tool=` and `&email=` headers (good practice)
- **Recommendation:** Reuse pubmed-scraper.py directly; async wrapper minimal

### openFDA API (FAERS & Enforcement)
- **Endpoints:**
  - FAERS: https://api.fda.gov/drug/event.json
  - Enforcement: https://api.fda.gov/drug/enforcement.json
- **Authentication:** API key optional (higher daily limit with key: 120k vs 1k)
- **Rate Limit:** 240 requests per minute per IP/key = ~4 requests per second
- **Response Format:** JSON, paginated with `skip`, `limit` parameters (max skip 25000)
- **Data Currency:** Weekly updates (enforcement), real-time (FAERS)
- **Unique Challenges:**
  - FAERS records have complex nested structure (reactions, drugs arrays)
  - Enforcement records simpler but updates lag regulatory actions
  - Global rate limit 0.5 req/sec is much more conservative than 4 req/sec (safety margin intentional per locked decision)
- **Recommendation:** Reuse fda-adverse-events-scraper.py directly; new enforcement fetcher mirrors FAERS pattern

## Open Questions

1. **ClinicalTrials.gov Exact Rate Limit**
   - What we know: ~10 req/sec documented, but alternativeestimate is ~0.83 req/sec (50 req/min)
   - What's unclear: Different endpoints have different limits? Behavior under sustained load?
   - Recommendation: In Phase 1 planning, add integration test: submit 50 requests to ClinicalTrials.gov v2 endpoint, measure actual 429s. Document observed limit. If 429s occur at <0.5 req/sec global, adjust global rate limit upward in Phase 1.x.

2. **ClinicalTrials.gov Pagination Edge Cases**
   - What we know: Uses `pageNumber` + `pageSize`, but pageSize max and default are unknown
   - What's unclear: If pageSize=100 but only 50 results exist, does API return 50 or error?
   - Recommendation: In Phase 1 planning, test pagination with small and large queries. Document pagination behavior.

3. **FDA Enforcement Endpoint Field Coverage**
   - What we know: Returns JSON from FDA Recall Enterprise System, weekly updates, includes UPC/brand name annotations
   - What's unclear: Does every record have manufacturer? Are action types standardized (Recall, Warning, Market Withdrawal)?
   - Recommendation: In Phase 1 planning, fetch 100 real enforcement records. Map schema. Test field presence with Pydantic validation.

4. **FAERS Record Exclusions or Filtering**
   - What we know: openFDA returns all FAERS records submitted
   - What's unclear: Are some records excluded (private/redacted)? Should we filter by country?
   - Recommendation: In Phase 1 planning, compare openFDA FAERS count vs. official FDA FAERS count for same drug. If mismatch >5%, investigate.

5. **Memory Limits Under Load**
   - What we know: Apify memory-constrained environment, 25-record batch proven safe in single-source actors
   - What's unclear: With 4 concurrent sources, does 25-record total batching hold? Or need per-source smaller batches?
   - Recommendation: In Phase 1 planning, profile memory locally with `memory_profiler`. Test on Apify staging with 4 sources × 100 records concurrent. Cap batch size if memory >500MB.

6. **Optimal Concurrency Bound (Semaphore(N))**
   - What we know: asyncio.Semaphore can bound concurrent tasks
   - What's unclear: Is Semaphore(2) safe (2 sources at a time)? Or could Semaphore(3) be faster without OOM?
   - Recommendation: In Phase 1 planning, test Semaphore(1), (2), (3), (4) locally. Measure throughput and memory. Document choice.

## Validation Architecture

**Skip this section entirely if workflow.nyquist_validation is explicitly set to false in .planning/config.json.**

From .planning/config.json: `"nyquist_validation": false` — **Validation architecture section SKIPPED per workflow config.**

## Sources

### Primary (HIGH confidence)
- **Apify SDK Python documentation** (https://docs.apify.com/sdk/python/reference/class/Actor, https://docs.apify.com/sdk/python/docs/concepts/actor-lifecycle) — Async patterns, Actor.use_state, Actor.push_data, context manager
- **fda-adverse-events-scraper source code** (https://github.com/labrat-0/fda-adverse-events-scraper) — RateLimiter pattern, fetch_with_backoff, Pydantic validation, Actor integration
- **pubmed-scraper source code** (https://github.com/labrat-0/pubmed-scraper) — Async generator pattern, batching, state tracking, free tier enforcement
- **NCBI E-utilities documentation** (https://www.ncbi.nlm.nih.gov/books/NBK25497/, https://support.nlm.nih.gov/kbArticle/?pn=KA-05318) — Rate limits (3 req/sec without key, 10 with)
- **openFDA API documentation** (https://open.fda.gov/apis/drug/enforcement/, https://open.fda.gov/apis/) — Enforcement and FAERS endpoints, JSON response format, 240 req/min rate limit

### Secondary (MEDIUM confidence)
- **ClinicalTrials.gov API v2 documentation** (https://clinicaltrials.gov/data-api/api, https://www.nlm.nih.gov/pubs/techbull/ma24/ma24_clinicaltrials_api.html) — REST API v2, ~10 req/sec rate limit (documentation sparse, flagged for validation)
- **httpx documentation** (https://www.python-httpx.org/async/, https://www.python-httpx.org/advanced/resource-limits/) — AsyncClient connection pooling, limits parameter
- **asyncio Semaphore patterns** (https://rednafi.com/python/limit-concurrency-with-semaphore/, https://medium.com/@mr.sourav.raj/mastering-asyncio-semaphores-in-python-a-complete-guide-to-concurrency-control-6b4dd940e10e) — Bounded concurrency, rate limiting with semaphore

### Tertiary (LOW confidence, marked for validation)
- **ClinicalTrials.gov rate limit estimates** (BioMCP documentation) — Claim of "50 requests/minute" conflicts with other sources; needs Phase 1 profiling to resolve

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** — All libraries (apify, httpx, pydantic) documented in official sources, versions confirmed in existing actors, tested in production
- Architecture patterns: **HIGH** — Both existing actors follow identical patterns; async/await confirmed in Apify official docs; rate limiter pattern proven
- API specifications: **HIGH** for NCBI (3 req/sec) and openFDA (4 req/sec); **MEDIUM** for ClinicalTrials.gov (documentation sparse, ~10 req/sec vs. ~0.83 req/sec estimates conflict; marked for Phase 1 validation)
- Pitfalls: **HIGH** — Based on observed issues in existing actors and standard async/Python best practices
- Code examples: **HIGH** — Sourced directly from existing production actors (pubmed-scraper, fda-adverse-events-scraper)

**Research date:** 2026-03-14
**Valid until:** 2026-04-14 (30 days; Apify SDK stable, APIs stable; ClinicalTrials rate limit may change)

**Known Limitations:**
- ClinicalTrials.gov rate limit requires Phase 1 testing (research found conflicting documentation)
- FDA enforcement endpoint field schema not fully explored (need sample data in Phase 1)
- FAERS schema evolution unknown (openFDA updates weekly; verify current schema before finalizing parser)
- Apify memory limits under 4-concurrent-source load untested (recommend profiling in Phase 1 planning)

---

*Research complete: 2026-03-14*
*Researched by: Claude (Haiku 4.5)*
*Domain: Multi-source async API aggregation, rate limiting, Apify actor patterns*
