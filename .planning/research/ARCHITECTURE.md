# Architecture Patterns for Multi-Source Data Aggregation

**Domain:** Multi-source data aggregation systems (drug intelligence signals)
**Researched:** 2026-03-14
**Confidence:** HIGH (based on existing working actors: pubmed-scraper, fda-adverse-events-scraper)

---

## Standard Architecture

### System Overview

Multi-source data aggregation systems follow a **layered pipeline** pattern:

```
┌──────────────────────────────────────────────────────────────────┐
│                        INPUT LAYER                               │
├──────────────────────────────────────────────────────────────────┤
│  Actor.get_input() → ScraperInput Validation → Apply Filters    │
│  (drug name, date range, severity threshold, limits)             │
└─────────┬──────────────────────────────────────────────────────┘
          │
          ├─────────────────────────────────────────────────────┐
          │                                                     │
┌─────────▼──────┐  ┌─────────────────┐  ┌──────────────────┐  │
│  PubMed        │  │  FAERS/openFDA  │  │  ClinicalTrials  │  │
│  Fetcher       │  │  Fetcher        │  │  Fetcher         │  │
│  (E-utilities) │  │  (REST API)     │  │  (API v2)        │  │
└─────────┬──────┘  └────────┬────────┘  └────────┬─────────┘  │
          │                   │                    │             │
          └─────────────────────────────────────┐  ┌────────────┘
                                                │  │
                      ┌───────────────────────────┴──┴───────────────┐
                      │       FDA Enforcement                       │
                      │       Fetcher (Recalls/Alerts)              │
                      │       (REST API)                            │
                      └──────────────┬────────────────────────────────┘
                                     │
┌──────────────────────────────────────────────────────────────────┐
│                   NORMALIZATION LAYER                            │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐│
│  │ PubMed Parser    │  │ FAERS Parser     │  │ Clinical Trials  ││
│  │ → ArticleRecord  │  │ → AdverseEvent   │  │ Parser           ││
│  │                  │  │   Record         │  │ → TrialRecord    ││
│  └──────────────────┘  └──────────────────┘  └──────────────────┘│
│                                                                   │
│  ┌──────────────────┐                                            │
│  │ FDA Enforcement  │                                            │
│  │ Parser           │                                            │
│  │ → AlertRecord    │                                            │
│  └──────────────────┘                                            │
└──────┬───────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                   AGGREGATION LAYER                             │
├──────────────────────────────────────────────────────────────────┤
│  Merge by drug_name, normalize dates, deduplicate sources        │
│  Compile unified per-drug signal object                          │
└──────┬──────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                   ENRICHMENT LAYER                              │
├──────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────┐  ┌───────────────────────────┐   │
│  │ Risk Score Calculation    │  │ Signal Filtering/Sorting  │   │
│  │ (weighted formula)        │  │ (by severity, recency)    │   │
│  └───────────────────────────┘  └───────────────────────────┘   │
└──────┬──────────────────────────────────────────────────────────┘
       │
┌──────▼──────────────────────────────────────────────────────────┐
│                   OUTPUT LAYER                                  │
├──────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ JSON Export  │  │ CSV Export   │  │ Actor.push_data()    │   │
│  │ (per drug)   │  │ (flattened)  │  │ (batch to dataset)   │   │
│  └──────────────┘  └──────────────┘  └──────────────────────┘   │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **Fetchers** (PubMed, FAERS, ClinicalTrials, FDA) | Query external APIs, handle pagination, rate limiting, retries | `AsyncGenerator` yielding raw API responses; `RateLimiter` for throttling |
| **Parsers/Normalizers** | Convert source-specific JSON/XML to Pydantic models; extract structured fields | `parse_*()` functions + `*Record` Pydantic models (schema_version, type, source-specific fields) |
| **Aggregators** | Merge parsed records by drug identifier; handle duplicates; combine signals | Group by `drug_name` (or normalized name); flatten arrays (papers, events, trials, alerts) |
| **Enrichment** | Calculate risk scores; filter/sort by criteria | Weighted formula (event count × severity + recall flag + trial completion status) |
| **Exporter** | Batch results to Apify dataset or transform to CSV | `Actor.push_data()` for batched output; CSV serialization for tabular export |

---

## Recommended Project Structure

```
src/
├── main.py                 # Actor entrypoint: input validation, orchestration
├── models.py              # Pydantic models for input + output
│                          # - DrugSignalInput (filters)
│                          # - DrugSignal (unified output)
│                          # - ArticleRecord, AdverseEventRecord, etc.
│
├── fetchers/              # Data source integrations
│   ├── __init__.py
│   ├── base.py            # BaseFetcher abstract class
│   ├── pubmed.py          # PubMedFetcher (reuse pubmed-scraper logic)
│   ├── faers.py           # FAERSFetcher (reuse fda-adverse-events-scraper logic)
│   ├── clinical_trials.py # ClinicalTrialsFetcher (new)
│   └── fda_enforcement.py # FDAEnforcementFetcher (new)
│
├── parsers/               # Source-specific → normalized models
│   ├── __init__.py
│   ├── pubmed_parser.py   # XML parsing for PubMed
│   ├── faers_parser.py    # JSON parsing for openFDA FAERS
│   ├── trial_parser.py    # JSON parsing for ClinicalTrials.gov
│   └── enforcement_parser.py # JSON parsing for FDA enforcement
│
├── aggregator.py          # Merge multi-source records into per-drug signal
├── risk_scorer.py         # Calculate v1 risk score
├── utils.py               # RateLimiter, date normalization, helpers
│
└── .actor/                # Apify actor metadata (created separately)
    ├── input_schema.json
    └── actor.json
```

### Structure Rationale

- **`fetchers/`:** Each data source is isolated. Fetcher interface is consistent (async generator); can parallelize or swap sources independently. Reuses existing scraper code by extracting the fetch+parse logic.
- **`parsers/`:** Parsing logic is decoupled from fetching. A parser can be tested independently. Makes it easy to change source API without breaking normalization.
- **`aggregator.py`:** Central logic for merging signals by drug. Keeps main.py clean and makes the aggregation strategy testable.
- **`risk_scorer.py`:** Separate module for signal enrichment. v2 can swap in a more complex model without touching other layers.
- **`utils.py`:** Shared utilities (RateLimiter from existing actors, date helpers, validators).

---

## Architectural Patterns

### Pattern 1: AsyncGenerator for Streaming Data

**What:** Fetchers yield records one at a time using `async for` loops. Main thread batches and pushes to Apify dataset. Never loads entire result set in memory.

**When to use:** Multi-source aggregation with potentially thousands of results per source. Apify actors run in constrained cloud environments.

**Trade-offs:**
- **Pro:** Memory efficient, progressive results visible in Apify dashboard, easy to halt early if max_results reached.
- **Con:** Can't easily re-sort results (would need to buffer), harder to deduplicate across all sources (requires in-memory set or post-processing).

**Example:**
```python
async def fetch(self) -> AsyncGenerator[dict[str, Any], None]:
    """Yield raw API records one at a time."""
    skip = 0
    while skip < self.config.max_results:
        page = await self.client.get(url, params={"skip": skip, "limit": 100})
        for record in page.json()["results"]:
            yield record
        skip += 100
```

### Pattern 2: Pydantic Models for Schema Versioning

**What:** Each source has a dedicated `*Record` model (ArticleRecord, AdverseEventRecord, etc.) with `schema_version` and `type` fields. Output model (DrugSignal) nests all four source types.

**When to use:** Any integration with multiple external APIs. Protects against schema drift when upstream changes.

**Trade-offs:**
- **Pro:** Explicit contract between fetcher and parser. Type hints catch mismatches early. Backwards-compatible versioning.
- **Con:** Models must stay in sync with upstream APIs; manual parser updates needed when source APIs change.

**Example:**
```python
class ArticleRecord(BaseModel):
    schema_version: str = "1.0"
    type: str = "article"
    pmid: str
    doi: str
    title: str
    # ... (source-specific fields)

class DrugSignal(BaseModel):
    drug_name: str
    articles: list[ArticleRecord] = []
    adverse_events: list[AdverseEventRecord] = []
    trials: list[TrialRecord] = []
    alerts: list[AlertRecord] = []
    risk_score: float
```

### Pattern 3: Rate Limiting + Retry with Exponential Backoff

**What:** Wrap HTTP clients with a `RateLimiter` (wait before each request) and retry logic (exponential backoff on failures). Reuse from existing actors.

**When to use:** Any external API integration. Government APIs (NCBI, openFDA) have strict rate limits; cloud APIs (ClinicalTrials.gov) may have request throttling.

**Trade-offs:**
- **Pro:** Respects API limits, reduces failed requests, prevents IP blocks.
- **Con:** Adds latency; long-running actors may timeout if rate limits are very strict.

**Example:**
```python
class RateLimiter:
    def __init__(self, interval: float = 0.34):
        self.interval = interval
        self.last_request = 0

    async def wait(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.interval:
            await asyncio.sleep(self.interval - elapsed)
        self.last_request = time.time()

# In fetcher:
async with httpx.AsyncClient() as client:
    rate_limiter = RateLimiter(interval=0.34)
    for _ in range(max_retries):
        try:
            await rate_limiter.wait()
            response = await client.get(url)
            return response.json()
        except Exception:
            await asyncio.sleep(2 ** retry_count)
```

### Pattern 4: Normalized Date Handling

**What:** Each source returns dates in different formats (ISO 8601, YYYYMMDD, "2023 Jan-Feb"). Normalize to ISO 8601 in parsers; store as string for JSON export.

**When to use:** Any system aggregating data from heterogeneous sources with temporal data.

**Trade-offs:**
- **Pro:** Consistent format downstream; easy filtering/sorting by date.
- **Con:** Precision loss if source has partial dates (e.g., only month/year); parsing errors if format detection fails.

**Example:**
```python
def normalize_date(raw_date: str, format_hint: str = None) -> str:
    """Convert various date formats to ISO 8601."""
    if not raw_date:
        return ""
    # Try common formats: YYYYMMDD, YYYY-MM-DD, "YYYY Mon Day", etc.
    for fmt in ["%Y%m%d", "%Y-%m-%d", "%Y %b %d"]:
        try:
            dt = datetime.strptime(raw_date.strip(), fmt)
            return dt.isoformat()
        except ValueError:
            pass
    return raw_date  # Return as-is if unparseable
```

---

## Data Flow

### Request Flow

```
1. Actor receives input (drug_name, date_from, date_to, severity_threshold, max_results)
2. Input validation (DrugSignalInput.validate())
3. Concurrent fetchers initialized with filters
4. Each fetcher streams records to parser
5. Parser normalizes to *Record models
6. Aggregator collects by drug_name
7. Risk scorer enriches each signal
8. Batch results to Actor.push_data() (every 25 records)
9. Export as JSON (primary) or CSV (secondary)
```

### Signal Aggregation Flow

```
PubMed articles        FAERS adverse events      ClinicalTrials trials     FDA enforcement alerts
        │                       │                         │                         │
        └───────────────────────┼─────────────────────────┼─────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │ Parse to *Record      │
                    │ (normalize dates)     │
                    └───────────┬───────────┘
                                │
            ┌───────────────────┼───────────────────┐
            │                   │                   │
        ┌───▼───┐           ┌───▼───┐           ┌──▼────┐
        │Article│           │Event  │           │Trial/ │
        │Record │           │Record │           │Alert  │
        │ array │           │ array │           │ array │
        └───┬───┘           └───┬───┘           └──┬────┘
            │                   │                   │
            └───────────────────┼───────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │ Group by drug_name    │
                    │ (key: normalized name)│
                    └───────────┬───────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Create DrugSignal      │
                    │ (nest all arrays)      │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Calculate risk_score   │
                    │ (weighted formula)     │
                    └───────────┬────────────┘
                                │
                    ┌───────────▼────────────┐
                    │ Output JSON + CSV      │
                    └────────────────────────┘
```

### Key Data Flows

1. **Fetch → Parse → Aggregate:**
   - Concurrent fetchers yield raw API responses → parsers normalize to Pydantic models → aggregator merges by drug_name
   - Decouples source-specific logic from normalization logic
   - Allows reuse of existing scraper code without refactoring

2. **Aggregation → Enrichment → Export:**
   - Aggregator groups signals by drug → risk scorer calculates per-drug metrics → exporter batches to Apify dataset
   - Progressive results visible in Apify dashboard in real-time

3. **Filtering & Deduplication:**
   - Fetchers filter by date_range, severity (upstream in query strings where possible)
   - Parsers handle duplicates within a source (e.g., same PMID appearing multiple times in PubMed results)
   - Aggregator deduplicates across sources by matching drug_name + unique ID (PMID, safety_report_id, etc.)

---

## Scaling Considerations

| Scale | Architecture Adjustments |
|-------|--------------------------|
| **0-10 runs/month (dev/test)** | Single actor, serial fetchers, 100-1K results per source, no caching |
| **10-100 runs/month (beta launch)** | Parallel fetchers (asyncio), 1K-10K results per source, simple in-memory caching for frequently queried drugs, batch size 25 |
| **100K+ signal queries/month (production)** | Consider splitting fetchers into separate actors (fan-out pattern), dedicated result caching layer (Redis/Apify key-value store), pre-aggregated indexes for top drugs, async queue for backpressure |

### Scaling Priorities

1. **First bottleneck:** API rate limits (PubMed NCBI: 3 req/sec without key). Mitigation: Stagger requests across sources, use RateLimiter, add exponential backoff.
2. **Second bottleneck:** Memory usage with large result sets. Mitigation: AsyncGenerator streaming (already done), implement disk spilling for temp buffers if needed (v2).
3. **Third bottleneck:** Apify actor concurrency limits. Mitigation: v2 could split into source-specific sub-actors called via `actor.call()`, then aggregate results.

---

## Anti-Patterns

### Anti-Pattern 1: Loading All Results into Memory Before Aggregation

**What people do:** Fetch all PubMed articles, all FAERS events, all trials into lists, then aggregate at the end.

**Why it's wrong:** Apify actors run in memory-constrained environments (~512 MB–2 GB). If each source returns 10K records, you're holding 40K objects in memory simultaneously. Risk of OOM kills.

**Do this instead:** Use AsyncGenerator streaming. Yield parsed records immediately. Let `Actor.push_data()` batch and flush periodically. Aggregation happens lazily as records arrive.

### Anti-Pattern 2: Mixing Fetching and Parsing Logic

**What people do:** Fetcher class parses API response and returns normalized models directly.

**Why it's wrong:** Hard to test independently. If API schema changes, parser fails silently. Source-specific logic bleeds into normalization layer.

**Do this instead:** Separate concerns. Fetcher → raw dict/JSON. Parser → Pydantic model. Chain them: `fetcher.fetch()` → `parser.parse()`.

### Anti-Pattern 3: Hardcoded Drug Name Matching

**What people do:** Exact string match on `drug_name` to group signals. "aspirin" ≠ "Aspirin" ≠ "acetylsalicylic acid".

**Why it's wrong:** Data loss due to casing/formatting differences across sources. Missed signals.

**Do this instead:** Normalize before aggregation. Lowercase, strip whitespace, basic fuzzy matching (v1). Consider RxNorm API for canonical names (v2).

### Anti-Pattern 4: Calculating Risk Score Without Source Confidence Weights

**What people do:** Simple sum: (adverse_event_count + recall_flag + trial_completion_status).

**Why it's wrong:** All sources treated equally. FAERS has high false-positive rate; PubMed peer review is more reliable. Risk score lacks nuance.

**Do this instead:** Weight by source reliability: PubMed (0.9), trials (0.8), FAERS (0.6), FDA enforcement (0.95). Version the scoring formula.

---

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **NCBI PubMed (E-utilities)** | HTTP + rate limiter (3 req/sec limit without key). ESearch for IDs, EFetch for full records. XML parsing. | Reuse from pubmed-scraper. Respects NCBI rate limit via RateLimiter(interval=0.34s). |
| **openFDA FAERS** | REST JSON API. `/drug/event.json` endpoint with search parameters. Pagination via `skip`/`limit`. | Reuse from fda-adverse-events-scraper. No auth required. 120 req/min soft limit. |
| **ClinicalTrials.gov API v2** | REST JSON API. `/api/v2/studies` with query filters (condition, drug, status). Pagination via `pageNumber`. | New. No auth. Generous rate limits. Response includes full trial protocol + status. |
| **FDA Enforcement (openFDA)** | REST JSON API. `/drug/enforcement.json` with date filters, recall classification. Same rate limits as FAERS. | New. Combines recalls + field corrections in single endpoint. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| **Fetchers ↔ Parsers** | AsyncGenerator[dict] → Pydantic model. Fetcher yields raw JSON/XML as dict. Parser consumes and normalizes. | Decoupled. Parser can ignore unknown fields. Easy to version independently. |
| **Parsers ↔ Aggregator** | List[*Record] grouped by drug_name. Aggregator pulls from all parsers, groups. | In-memory grouping. If deduplication needed across sources (same PMID in multiple trials), use set of (source_id, source_type) tuples. |
| **Aggregator ↔ Risk Scorer** | DrugSignal (nested arrays) → DrugSignal (with risk_score). | Enrichment step. Risk score is read-only field on output model. |
| **Scorer ↔ Exporter** | DrugSignal → JSON/CSV. Exporter takes final signal, serializes, batches. | Final transformation. CSV flattens nested arrays (multiple rows per drug). |

---

## Implementation Notes for Reuse

### Reusing pubmed-scraper Code

1. **Extract the Fetcher:**
   - Copy `scraper.py:PubMedScraper` class logic (minus main.py orchestration)
   - Adapt to return async generator: `async def fetch() -> AsyncGenerator[dict, None]`
   - Import existing `utils.py:RateLimiter`, `utils.py:fetch_xml()` directly

2. **Reuse Parsing:**
   - Copy `scraper.py:_parse_article()` and helper functions
   - Wrap in new module `parsers/pubmed_parser.py`
   - Use existing `models.py:ArticleRecord` or adapt if schema changed

3. **Aggregate:**
   - Group ArticleRecords by drug_name via aggregator.py

### Reusing fda-adverse-events-scraper Code

1. **Extract Fetcher:** Copy `scraper.py:FDAAdverseEventsScraper._scrape()` and `fetch_page()` methods
2. **Reuse Parsing:** Use existing `scraper.py:parse_adverse_event()` logic; wrap in parsers module
3. **Aggregate:** Group AdverseEventRecords by drug_name

### New Sources (ClinicalTrials.gov, FDA Enforcement)

Follow the same pattern:
1. **Fetcher:** New class, `async def fetch()`, yields raw API responses
2. **Parser:** Source-specific normalizer to Pydantic model (TrialRecord, AlertRecord)
3. **Aggregator:** Group by drug_name

---

## Sources

- **pubmed-scraper** (`/home/labrat/Github Projects/pubmed-scraper/`) — Working implementation of async fetcher + parser pattern with Apify SDK
- **fda-adverse-events-scraper** (`/home/labrat/Github Projects/fda-adverse-events-scraper/`) — Working implementation of REST API fetcher with pagination, rate limiting, and normalization
- **Apify SDK documentation** — Actor.get_input(), Actor.push_data(), Actor.use_state() patterns
- **NCBI E-utilities documentation** — ESearch/EFetch API rate limits, XML response structure
- **openFDA documentation** — `/drug/event.json` and `/drug/enforcement.json` endpoints, rate limits
- **ClinicalTrials.gov API v2 documentation** — REST endpoint structure, pagination, query parameters

---

*Architecture research for: Drug Signal Radar (multi-source drug intelligence aggregator)*
*Researched: 2026-03-14*
