# Stack Research: Apify Multi-Source Drug Intelligence Actor

**Domain:** Python data aggregation actor for Apify platform
**Researched:** 2026-03-14
**Confidence:** HIGH

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12 | Runtime | Apify actor base image `apify/actor-python:3.12` is actively maintained; 3.12 has excellent async/await support and type hints. All existing actors use 3.12. |
| apify SDK | >=2.0.0 | Actor framework | Official Apify SDK for Python; provides `Actor` context manager, `Actor.push_data()`, `Actor.get_input()`, `Actor.use_state()`, dataset/KVS integration, logging, and status management out of the box. No alternatives for Apify platform actors. |
| httpx | >=0.27.0 | HTTP client | Modern, async-first, replaces urllib3/requests. Supports connection pooling, automatic retries, timeout handling, and streaming. Significantly better than requests for concurrent multi-API aggregation. All existing actors verified with this. |
| pydantic | >=2.0.0 | Data validation | Schema validation for actor input, data models, and output records. V2 has performance improvements (50x faster than V1 in some cases) and is the de facto standard in Python web/CLI apps. Replaces manual validation. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| python-dateutil | (not pinned; add >=2.8.2) | Date parsing | For flexible date parsing across four APIs that may return dates in different formats (ISO 8601, Unix timestamps, etc.). Essential for date filtering. |
| xmltodict | (not pinned; add >=0.13.0) | XML-to-dict conversion | For FDA enforcement endpoint and any XML responses. Alternatives (xml.etree.ElementTree) are lower-level; xmltodict reduces boilerplate. Consider if ClinicalTrials.gov API returns structured XML. |
| tenacity | (not pinned; add >=8.2.0) | Retry/backoff logic | Higher-level retry decorator. Currently using manual backoff in utils.py (exponential with jitter). Tenacity is more readable for complex retry scenarios. Optional — current manual approach is battle-tested. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest | Unit and integration testing | Add pytest>=7.4 to dev dependencies. For testing individual scrapers and data normalization logic. |
| pytest-asyncio | Async test runner | Add pytest-asyncio>=0.21 to dev dependencies. Required for testing async scraper methods. |
| black | Code formatting | Add black>=23.0 to dev dependencies. Matches formatting style in existing actors. |
| ruff | Linting | Add ruff>=0.1.0 to dev dependencies. Fast Python linter; more comprehensive than pylint. |
| mypy | Type checking | Add mypy>=1.5 to dev dependencies. Validate type hints in models.py and scrapers. |

## Installation

```bash
# Core dependencies
pip install apify>=2.0.0 httpx>=0.27.0 pydantic>=2.0.0

# Supporting libraries
pip install python-dateutil>=2.8.2

# Optional: if FDA enforcement returns XML
pip install xmltodict>=0.13.0

# Dev dependencies
pip install -D pytest>=7.4 pytest-asyncio>=0.21 black>=23.0 ruff>=0.1.0 mypy>=1.5
```

Or in `requirements.txt`:

```
apify>=2.0.0
httpx>=0.27.0
pydantic>=2.0.0
python-dateutil>=2.8.2
```

And `requirements-dev.txt`:

```
pytest>=7.4
pytest-asyncio>=0.21
black>=23.0
ruff>=0.1.0
mypy>=1.5
```

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| httpx | requests | If blocking I/O is acceptable (not concurrent). Simpler mental model but ~10x slower for multi-API aggregation. Not recommended here. |
| httpx | aiohttp | Similar capability, lighter weight. httpx has better connection pooling and explicit retry support. httpx is becoming standard in Apify ecosystem. |
| pydantic | dataclasses | If zero external dependencies required. Pydantic provides validation; dataclasses don't. Pydantic is standard in production actors. |
| pydantic | attrs | Similar to dataclasses. Pydantic has broader ecosystem support and better error messages. |
| python-dateutil | dateparser | If parsing extremely exotic date formats. python-dateutil covers 95% of cases; dateparser adds bloat. Not needed unless APIs are unusual. |
| Manual backoff (current) | tenacity | If retry logic becomes complex (e.g., exponential backoff + circuit breaker). Current approach is simpler; upgrade if needed. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| requests | Blocking I/O for concurrent APIs. Requires manual async wrapping. httpx does this natively. | httpx |
| urllib3/urllib | Low-level; requires manual connection pooling, retry logic, and timeout handling. Don't reinvent the wheel. | httpx |
| BeautifulSoup / Scrapy | For REST APIs returning JSON. These are for HTML scraping. ClinicalTrials.gov and openFDA both have REST APIs; no scraping needed. | httpx + json parsing |
| SQLAlchemy / databases | For structured data persistence. Apify handles dataset storage; we push to Apify's dataset API. No local DB needed in v1. | Actor.push_data() |
| Celery / RQ | For task queues. Apify handles scheduling and parallelization. Over-engineering. | Apify scheduler or container orchestration |
| Custom retry logic from scratch | Risk of race conditions, missed exponential backoff edge cases. | Use httpx built-in retries + manual backoff in utils (already proven pattern) |
| Python 3.10 or older | Apify base image uses 3.12. Misalignment causes environment drift. Type hints are better in 3.12. | Python 3.12 |

## Stack Patterns by Variant

**If aggregating multiple APIs concurrently:**
- Use `httpx.AsyncClient()` in context manager (see pubmed-scraper main.py)
- Create one client per Actor run; reuse across all four data sources
- Each scraper gets same client + shared RateLimiter
- Because: Connection pooling is shared; avoids 4x overhead from 4 separate clients

**If date filtering differs by source:**
- Use python-dateutil to parse and normalize dates in models
- Store as ISO 8601 string in output JSON
- Because: Handles PubMed (YYYY/MM/DD), FAERS (YYYYMMDD), ClinicalTrials (ISO 8601), FDA enforcement (varies). Single source of truth prevents bugs.

**If rate limits vary by API:**
- Subclass RateLimiter or add per-scraper interval override
- Don't share single RateLimiter across all sources
- Because: PubMed allows 3 req/sec (no key); openFDA allows 240 req/min; ClinicalTrials has no advertised limit; FDA enforcement unknown. Current RateLimiter is global.

**If output needs CSV export:**
- Use Apify's `Actor.push_data()` to push dicts, then configure CSV output in input schema
- Don't build CSV writer; Apify handles it natively
- Because: Less code, standardized output, integrates with Apify UI

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| apify@2.0.0+ | Python 3.8+ | v2.0+ is async-first; v1.x is legacy. Use v2. |
| httpx@0.27.0+ | apify@2.0.0+ | No known conflicts; both modern. |
| pydantic@2.0.0+ | Python 3.8+ | V1 and V2 are incompatible; upgrade cleanly or use v1 only. Existing actors use v2. |
| python-dateutil@2.8.2+ | No conflicts | Works with all Python versions, Pydantic versions, and httpx. |
| pytest-asyncio@0.21+ | pytest@7.4+ | Requires new fixture mode in 0.21+. No breaking changes for basic usage. |

## Data Validation Strategy

**Input validation:**
- Pydantic BaseModel for actor input (replicate pubmed-scraper pattern)
- `ScraperInput.from_actor_input()` to handle camelCase ↔ snake_case conversion
- `validate_for_mode()` method to ensure required fields per mode (e.g., drug_name required for "search_by_drug")
- Return validation errors via `await Actor.fail(status_message=error)`

**Output validation:**
- Pydantic BaseModel for each record type (ArticleRecord, AdverseEventRecord, TrialRecord, EnforcementRecord)
- `.dict()` or `.model_dump()` for JSON serialization to `Actor.push_data()`
- Schema version field in each record (e.g., "1.0") for backwards compatibility

**Async patterns:**
- Use `async for` with AsyncGenerator from scrapers
- Batch push every N records (batch_size=25 in existing actors) to avoid memory bloat
- Use `Actor.use_state()` to track scraped/failed counts across retries

## Sources

- **Context7:** Verified `pubmed-scraper` and `fda-adverse-events-scraper` repos; confirmed requirements.txt dependencies, src/main.py patterns, Dockerfile (apify/actor-python:3.12).
- **Official Apify Docs:** SDK documentation confirms Actor context manager pattern, push_data() batching, and input schema via .actor/input_schema.json.
- **Existing Implementations:** Both validated actors (created 2026-03-06) use identical stack: apify>=2.0.0, httpx>=0.27.0, pydantic>=2.0.0. No alternatives tested in these repos.
- **Python Ecosystem:** httpx is HTTP standard for async Python; pydantic v2 is production standard for validation; python-dateutil is RFC 2822/ISO 8601 standard.

---
*Stack research for: Apify drug intelligence actor (multi-source aggregation)*
*Researched: 2026-03-14*
*Confidence: HIGH — Based on validated existing implementations + Apify official patterns*
