# Pitfalls Research: Multi-Source Drug Signal Aggregation

**Domain:** Medical data aggregation (PubMed, FAERS, ClinicalTrials.gov, FDA enforcement)
**Researched:** 2026-03-14
**Confidence:** HIGH (based on existing actor patterns + domain requirements)

---

## Critical Pitfalls

### Pitfall 1: Uncontrolled Resource Exhaustion When Aggregating Four Sources in Parallel

**What goes wrong:**
Actor memory bloats and eventually crashes or times out. CPU spikes from concurrent requests to 4 APIs simultaneously. No individual source respects rate limits of other sources.

**Why it happens:**
Each source's rate limiter is independent. When all four scrapers run concurrently without coordination, they flood the Apify container and the external APIs. If one source is slow (e.g., FAERS has network jitter), buffered data accumulates in memory while other sources keep fetching.

**How to avoid:**
1. **Implement a global coordinator** that manages concurrency across all 4 sources. Use `asyncio.Semaphore(max_concurrent=2)` to limit concurrent source operations, not just per-source rate limiting.
2. **Fetch one source fully before starting the next** for MVP (simplest approach). Only parallelize sources after MVP if profiling shows benefit.
3. **Strict batching**: Push data to Apify dataset after **each source completes**, not after all data is loaded into memory.
4. **Memory monitoring**: Log peak memory after each source completes. If any source exceeds 100MB, error out early.
5. **Use iterators, not lists**: Never store all results in memory. Use async generators throughout the pipeline.

**Warning signs:**
- Apify actor timeout (killed after 15 minutes) = uncontrolled blocking somewhere
- Memory warnings in logs: "Approaching memory limit"
- Latency spike after a few hundred records = buffer bloat
- Network errors mid-run, then recovery = async task accumulation

**Phase to address:**
**Phase 1 (Core Aggregation)** — Build rate limiting and resource management into the initial scraper architecture. Cannot be bolted on later.

---

### Pitfall 2: Conflicting Rate Limits Across Four APIs With Different Policies

**What goes wrong:**
Actor gets blocked/throttled by one or more APIs. Recovery logic fails silently. No visibility into which source caused the failure.

**Why it happens:**
- NCBI E-utilities: max 3 req/sec without API key, enforced at IP level
- openFDA: max 100 req/minute per IP, enforced differently (rolling window vs. hard window)
- ClinicalTrials.gov API v2: max 100 req/minute, blocking behavior unclear
- FDA enforcement endpoint: unclear limits, may use CORS rules instead

Different backoff strategies don't compose well. If one rate limiter retries aggressively, it can trigger the other's limit.

**How to avoid:**
1. **Document rate limits in code as constants**:
   ```python
   RATE_LIMITS = {
       "pubmed": {"max_per_sec": 3, "requires_api_key": True},
       "faers": {"max_per_min": 100, "window": "rolling"},
       "clinicaltrials": {"max_per_min": 100, "window": "hard"},
       "fda_enforcement": {"max_per_min": "unknown", "fallback_interval": 1.0},
   }
   ```
2. **Use conservative defaults**: Start with 0.5 req/sec for all (slowest common denominator). Allow users to increase via input params for paid actors.
3. **Separate retry logic from rate limiting**:
   - Rate limiter: deterministic wait based on policy
   - Retry handler: exponential backoff for 429/503, max 3 retries, jitter added
4. **Log rate limit hits per source**: Include source name, HTTP status, retry count in every backoff log.
5. **Fail fast on repeated 429s**: If a source returns 429 more than 2 times in a run, fail the entire source (don't retry forever).

**Warning signs:**
- One source completes fine, another mysteriously hangs for 5+ seconds between requests
- Logs show "429 Too Many Requests" followed by timeout errors
- API response times increase throughout the run (progressive throttling)
- Different users report different blocking patterns (varies by IP reputation)

**Phase to address:**
**Phase 1** — Rate limit documentation and coordination strategy must be in input schema and README. Cannot be tuned post-launch without user confusion.

---

### Pitfall 3: Schema Mismatches When Normalizing Across Four Heterogeneous Data Sources

**What goes wrong:**
Output JSON has inconsistent field names, types, and nesting. Risk score calculation breaks because fields are sometimes strings, sometimes ints. Downstream consumers can't reliably parse output.

**Why it happens:**
Each source returns vastly different schemas:
- PubMed: XML with 100+ optional fields, author arrays, MeSH term hierarchies
- FAERS: Deeply nested patient/drug/reaction objects, optional arrays, legacy codes
- ClinicalTrials.gov: Complex site/status enums, varying date formats (YYYY-MM-DD vs. unstructured)
- FDA enforcement: RSS item metadata, different schema than openFDA FAERS

Mapping these to a single "drug signal" schema is lossy. If mapping logic is scattered across different modules, inconsistencies creep in (e.g., one normalizer uses "adverse_reaction", another uses "reaction_term").

**How to avoid:**
1. **Design a unified schema BEFORE coding any scraper**. Define all possible fields and their canonical types.
   ```python
   class DrugSignal(BaseModel):
       # Canonical schema
       source: str  # "pubmed" | "faers" | "clinicaltrials" | "fda"
       source_record_id: str
       drug_name: str  # normalized, lowercase
       drug_name_variants: list[str]  # raw names as found in source
       signal_type: str  # "publication" | "adverse_event" | "trial_status" | "enforcement"
       summary: str
       severity_indicators: SeverityIndicators
       date: datetime  # ISO 8601, UTC
       sources_urls: dict[str, str]  # map to original record
       confidence_score: float  # 0-1, how trustworthy is this signal
   ```
2. **One normalizer class per source**, with strict input/output types:
   ```python
   class PubMedNormalizer:
       def normalize(self, article: ArticleRecord) -> DrugSignal: ...
   ```
3. **Validate output**: Every normalizer must produce valid DrugSignal via Pydantic.
4. **Test with real data samples** from each source in Phase 1. Don't assume schema — test against actual API responses.
5. **Include schema_version in every output record**. Allows future migrations.

**Warning signs:**
- Output CSV has columns in different orders for different records
- Risk score calculation crashes because it assumes field type X but gets field type Y
- Downstream analysis script fails on subset of records
- User complaints: "This drug appears twice with different names"

**Phase to address:**
**Phase 1** — Unified schema design and test data validation. Fixing schema after launch causes breaking changes.

---

### Pitfall 4: Silent Data Loss From Partial Parsing Failures Across Multiple Records

**What goes wrong:**
Actor reports success but omits records silently. Output contains only 30% of expected data. User doesn't notice until analysis step fails on aggregate stats.

**Why it happens:**
Each source has edge cases in parsing:
- FAERS: Sometimes patient.reaction array is missing or malformed → code throws exception → single record lost
- ClinicalTrials.gov: Some trials don't have enrollment data → NPE on calculation → swallowed in try/except
- FDA enforcement: Inconsistent date formats → parsing fails → skipped
- PubMed: Articles with no authors → Author list parsing fails

Typical pattern: `try: parse_record() except: continue` logs at ERROR level but continues. User sees "Scraping completed successfully" and 100 records, not realizing 500 were silently dropped.

**How to avoid:**
1. **Track parse failures by source and type**:
   ```python
   parse_failures = {
       "pubmed": {"missing_title": 0, "invalid_date": 0},
       "faers": {"missing_reactions": 0, "malformed_drugs": 0},
   }
   ```
2. **Report failure rate in final status**: "Scraped 1000 records, 50 parse failures (5%)"
3. **Fail the run if failure rate exceeds threshold**: e.g., >10% = abort with error
4. **Store partial records separately**: If a record fails parsing, store raw JSON with error annotation instead of dropping
5. **Test parsing against worst-case source data**: In Phase 1, get 100 edge-case records from each source and validate the parser doesn't lose data

**Warning signs:**
- Final count (X records) much lower than expected (~Y records)
- Actor status says "Success" but critical fields missing from all records
- Logs show many ERROR lines with "Error parsing record" but run continues
- User manually compares expected counts vs. actual and finds discrepancy

**Phase to address:**
**Phase 1** — Implement parse failure tracking and thresholds. Phase 2: add partial-record storage if needed.

---

### Pitfall 5: Async Task Leaks in Concurrent Scraper Loops

**What goes wrong:**
Apify actor hangs at 99% completion. Task list grows unbounded. Memory climbs. After 10-15 minutes, actor is killed by platform timeout.

**Why it happens:**
When aggregating 4 sources concurrently with async generators:
- Source loop 1 yields 1000 records → all enqueued for parsing
- Source loop 2 yields 1000 records → also enqueued
- If one source is slow, tasks accumulate in the event loop queue
- Exception in one source's loop doesn't cancel other tasks → orphaned coroutines

Example pitfall: `await asyncio.gather(source1.scrape(), source2.scrape(), ...)` without timeouts or cancellation on first failure.

**How to avoid:**
1. **Use `asyncio.TaskGroup` (Python 3.11+) with proper cancellation**:
   ```python
   async with asyncio.TaskGroup() as tg:
       task1 = tg.create_task(source1.scrape_with_timeout())
       task2 = tg.create_task(source2.scrape_with_timeout())
       # TaskGroup auto-cancels all on first exception
   ```
2. **If not using TaskGroup**: Use `asyncio.wait()` with explicit cancellation:
   ```python
   tasks = [
       asyncio.create_task(source_scrape(s, timeout=60))
       for s in sources
   ]
   done, pending = await asyncio.wait(tasks, timeout=300)
   for task in pending:
       task.cancel()
   ```
3. **Wrap every source scraper with a hard timeout**:
   ```python
   async def scrape_with_timeout(source_name, timeout_sec=120):
       try:
           async for record in scraper.scrape():
               yield record
       except asyncio.TimeoutError:
           logger.error(f"{source_name} timed out after {timeout_sec}s")
           raise
   ```
4. **Profile async behavior locally**: Use `asyncio.create_task()` debugging to detect orphaned tasks.

**Warning signs:**
- Apify actor progress bar at 99% but status frozen for >1 minute
- Memory usage climbs steadily toward limit
- Logs stop appearing but actor doesn't fail (hang, not crash)
- `ctrl+c` doesn't interrupt local dev run

**Phase to address:**
**Phase 1** — Async concurrency model must be designed upfront. Cannot debug after launch.

---

### Pitfall 6: Date Format Chaos Across Four Sources Breaks Risk Score Calculation

**What goes wrong:**
Risk score calculation crashes or produces wrong scores because dates are in inconsistent formats:
- PubMed: "2024-03", "2024", "January 2024", mixed formats in single source
- FAERS: YYYYMMDD (e.g., "20240315")
- ClinicalTrials.gov: ISO 8601 (e.g., "2024-03-15")
- FDA enforcement: RFC 2822 (e.g., "Thu, 15 Mar 2024")

Attempting to parse all to Python `datetime` fails silently or crashes. Risk score tries to calculate "days since signal" but gets None or wrong value.

**How to avoid:**
1. **Parse dates to ISO 8601 UTC datetime in each normalizer**:
   ```python
   def normalize_date(source_name: str, date_str: str) -> str | None:
       """Always returns ISO 8601 or None"""
       strategies = {
           "pubmed": [parse_pubmed_date, parse_year_only],
           "faers": [parse_yyyymmdd],
           "clinicaltrials": [parse_iso_8601],
           "fda": [parse_rfc2822, parse_iso_8601],
       }
       for parser in strategies[source_name]:
           try:
               return parser(date_str).isoformat() + "Z"
           except:
               continue
       logger.warning(f"Could not parse date from {source_name}: {date_str}")
       return None
   ```
2. **Reject records with unparseable dates** (fail parse, count as failure).
3. **Test date parsing thoroughly in Phase 1** with real samples from each source.
4. **Document date format assumptions** in schema comments.

**Warning signs:**
- Risk score calculation throws TypeError: `can't subtract datetime from NoneType`
- Risk scores are all 0 or all NaN
- Recency calculations show wrong age (e.g., signals marked as 5 years old when they're 5 days old)

**Phase to address:**
**Phase 1** — Date normalization strategy finalized before any scraper touches dates.

---

### Pitfall 7: Memory Bloat From Large Result Sets Before Pushing to Apify Dataset

**What goes wrong:**
Actor accumulates 100,000 records in memory before first push. Container memory limit exceeded. Process killed, zero output.

**Why it happens:**
Typical code pattern:
```python
all_records = []
async for source in sources:
    async for record in source.scrape():
        all_records.append(record)
# Only now push in batches
for batch in chunks(all_records, 1000):
    await Actor.push_data(batch)
```

This loads everything into memory upfront. For multi-source aggregation, this can easily exceed container limits.

**How to avoid:**
1. **Push data as soon as batch is full**, not after all sources are done:
   ```python
   batch = []
   async for source in sources:
       async for record in source.scrape():
           batch.append(record)
           if len(batch) >= 100:
               await Actor.push_data(batch)
               batch = []
   if batch:
       await Actor.push_data(batch)
   ```
2. **Track memory usage**: Log memory consumption after each push.
3. **Set batch_size based on expected record size**: ~1KB per record = 100 records per ~100MB batch.
4. **For unknown record sizes, start conservative**: batch_size = 50, increase after profiling.
5. **Use `gc.collect()` after each push** to ensure garbage collection:
   ```python
   await Actor.push_data(batch)
   batch = []
   gc.collect()
   ```

**Warning signs:**
- Process killed with "Out of memory" in Apify logs (no stack trace)
- Local test with 10k records uses 500MB+
- Actor completes but output is empty
- Memory usage graph in Apify shows linear increase with no plateaus

**Phase to address:**
**Phase 1** — Batching strategy and memory management must be in initial architecture.

---

### Pitfall 8: Risk Score Formula Produces Unreliable Results Due to Missing Data From Sources

**What goes wrong:**
Risk score differs wildly depending on which sources return data. If PubMed returns papers but FAERS has no data, score is low. Same drug with both sources has high score. Score is not comparable across drugs.

**Why it happens:**
Risk score v1 formula (from PROJECT.md): `adverse_event_count × severity + recall_flag + trial_failures`

Problem: Different drugs have different data availability:
- Popular drugs (e.g., aspirin) have 1000+ FAERS events but few recent ClinicalTrials
- New drugs have trials but few adverse events (safety data limited)
- Drug class queries may return papers but no enforcement actions

Simple weighted sum assumes all sources equally important, which is wrong.

**How to avoid:**
1. **Document score calculation with source weighting explicitly**:
   ```python
   def calculate_risk_score(signal: DrugSignal) -> float:
       """
       Risk score combines signals from multiple sources.
       Sources may not all be available for a given drug.

       Score = (faers_severity_weight * faers_score)
              + (trial_weight * trial_score)
              + (enforcement_weight * enforcement_score)
              + (pubmed_recency_weight * pubmed_score)

       Each weight normalized by data availability.
       """
       # Calculate per-source scores
       faers_score = calculate_faers_risk(signal.faers_events) if signal.faers_events else 0
       # ... etc

       # Normalize by available sources (don't penalize absence)
       weights = [
           (0.4, faers_score),
           (0.3, trial_score),
           (0.2, enforcement_score),
           (0.1, pubmed_score),
       ]
       available_weights = [(w, s) for w, s in weights if s > 0]
       if not available_weights:
           return 0.0

       total_weight = sum(w for w, _ in available_weights)
       return sum(w * s for w, s in available_weights) / total_weight
   ```
2. **Include source_coverage field in output**: `{"sources_with_data": ["faers", "pubmed"]}`
3. **v1: Use simple multiplier approach** (easy to understand)
4. **v2: Use ML model** to weight sources based on real outcomes
5. **Test score on known high-risk and low-risk drugs** (e.g., thalidomide vs. ibuprofen)

**Warning signs:**
- Risk scores for similar drugs differ by 10x
- Score is 0 for drug with known safety issues (missing source data)
- User: "Why is drug X rated higher than drug Y when Y has more adverse events?"

**Phase to address:**
**Phase 2** — Risk score tuning can wait until MVP is live. v1 formula is intentionally simple; document this limitation.

---

### Pitfall 9: Drug Name Normalization Causes Over-Aggregation or Under-Aggregation

**What goes wrong:**
Same drug appears under 5+ different names. Output has duplicate records. Or different drugs are merged because fuzzy match is too loose.

**Why it happens:**
APIs use different naming conventions:
- FAERS: medicinalproduct = trade name OR generic name (varies)
- PubMed: subject/keywords include both names
- ClinicalTrials.gov: condition + intervention names (not standardized)
- FDA: enforcement uses trade name primarily

Fuzzy matching without context is unreliable. E.g., "metformin" vs "MetforminER" vs "Metformin HCL" are same drug. But "lisinopril" vs "lisinopril + hydrochlorothiazide" are different.

**How to avoid:**
1. **NO fuzzy matching in v1**. Exact match only (case-insensitive, lowercase).
2. **Use user-provided drug name as filter**, not auto-deduplication.
   ```python
   # User asks for "ibuprofen"
   # Scraper filters results where drug_name.lower() == "ibuprofen"
   # Does NOT try to merge "ibuprofen" with "ibuprofen sodium"
   ```
3. **Include raw_drug_names array in output** so user can see all variants found
4. **Document in v1 README**: "This actor does NOT normalize drug names. Use exact drug name in input. For multi-name queries, make separate runs."
5. **v2: RxNorm API integration** for canonical drug name mapping (deferred to future)

**Warning signs:**
- Output has 10 records for "ibuprofen" but user only input "ibuprofen" (means fuzzy match grabbed extra)
- User finds duplicate records with slightly different drug names
- Over/under-aggregation noticed when comparing results across runs

**Phase to address:**
**Phase 1** — Accept limitation, document explicitly. v2 can add RxNorm normalization.

---

### Pitfall 10: Apify Actor Input Validation Doesn't Match Scraper Implementation

**What goes wrong:**
Input schema accepts parameters that scraper doesn't use or mishandles. Actor accepts "drug_class" filter but only searches "drug_name". Output is misleading.

**Why it happens:**
Input schema (`.actor/input_schema.json`) is defined separately from scraper code. When requirements change, one gets updated but not the other. Easy to miss in code review.

**How to avoid:**
1. **Generate input schema from Pydantic models**, not hand-crafted JSON:
   ```python
   # models.py
   class AggregatorInput(BaseModel):
       drug_name: str = Field(..., description="Required: drug to search for")
       drug_class: str = Field("", description="Optional: drug class for broader search")
       # ... all fields

       def validate_for_aggregation(self) -> str | None:
           """Validate that provided inputs are compatible with scraper"""
           if not self.drug_name and not self.drug_class:
               return "Provide either drug_name or drug_class"
           return None

   # In .actor/input_schema.json, embed this model's JSON schema
   ```
2. **Test input schema against actual scraper**: In Phase 1, run with real test inputs.
3. **Document which fields affect which sources** in README:
   ```
   - `drug_name`: Used by all 4 sources (exact match, case-insensitive)
   - `date_from`, `date_to`: PubMed, FAERS, ClinicalTrials only (ignored by FDA)
   - `severity_threshold`: FAERS only (ignored by other sources)
   ```

**Warning signs:**
- Input schema lists parameters that code doesn't reference
- User confusion: "I set this parameter but it had no effect"
- Code throws KeyError on input field expected from schema

**Phase to address:**
**Phase 1** — Input validation framework must be in place before MVP.

---

## Technical Debt Patterns

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| **One-source scraper before multi-source** | Faster to prototype | Have to refactor for coordination/resource sharing | Only if you commit to Phase 2 having time for refactor |
| **Fuzzy matching for drug names** | Catches typos, variations | Over-aggregation, false positives, confuses users | Never — use exact match, defer RxNorm to v2 |
| **Store all results in memory before pushing** | Simpler logic, easier to debug | OOM crashes, data loss | Never — push after every 100 records |
| **Single rate limiter for all sources** | Simpler code | Gets blocked by slowest API | Never — each source needs independent limiter + global coordinator |
| **Skip error handling, let exceptions bubble** | Fewer lines of code | Partial runs, data loss, confusing error messages | Never — log errors, track failure rates, fail gracefully |
| **No schema version in output** | Smaller JSON | Can't migrate schema in v2 without breaking consumers | Never — include `schema_version: "1.0"` in every record |
| **Manual input validation** | Done quickly | Inconsistencies, bugs, hard to test | Never — use Pydantic, auto-validate |

---

## Integration Gotchas

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| **NCBI E-utilities** | Forget tool/email in params → blocks requests | Always include `tool` and `email` query params; pre-set in fetch_xml() |
| **openFDA API** | Use global search without filters → 404 or no results | Build search query explicitly with field selectors (e.g., `patient.drug.medicinalproduct:...`) |
| **ClinicalTrials.gov API v2** | Assume all fields always present → NPE on access | Check field existence before accessing nested structures; use `.get()` on dicts |
| **FDA enforcement endpoint** | Parse RSS instead of structured JSON | Use openFDA `/drug/enforcement` endpoint (structured JSON, not RSS) |
| **Apify Dataset.push_data()** | Push 1000s of items in tight loop → API rate limits | Batch to 100-500 items per push, small delays between |
| **httpx.AsyncClient** | Create new client per request → resource leak | Use single `async with httpx.AsyncClient()` context, reuse client |
| **Pydantic model export** | Use `.dict()` then JSON-serialize → loses precision | Use `model.model_dump_json()` directly for safe serialization |

---

## Performance Traps

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|-----------|----------------|
| **Unbounded concurrent tasks** | CPU at 100%, memory climbing, timeout | Use `asyncio.Semaphore(max_concurrent=2)` to cap concurrent sources | >1000 records per source |
| **No batch pushing** | Memory grows linearly with results | Push after every 100 records | >10k total records |
| **XML parsing whole document** | High CPU, memory spikes on large records | Stream XML, parse incrementally with iterparse | PubMed returns 5000+ articles per query |
| **Retry with no exponential backoff** | Hammers API, triggers aggressive throttling | Use exponential backoff: 1s, 2s, 4s, 8s, 15s max | Any API returns 429 more than once |
| **Blocking sleep in tight loop** | 60 second fetch becomes 120+ seconds with rate limiting | Use async sleep, not sync | Multi-source queries with heavy rate limiting |
| **No timeout on HTTP requests** | Single hung request hangs entire actor | Always set `timeout=30` on client.get() | Network glitches, slow API server |

---

## Security Mistakes

| Mistake | Risk | Prevention |
|---------|------|-----------|
| **Log API responses without redaction** | Sensitive data (patient records, test data) in logs | Never log full response body; log only status + headers + truncated body (first 200 chars) |
| **Hardcode API keys/auth tokens in code** | Exposed in git history, Apify source | Use environment variables (`os.getenv()`), never commit secrets |
| **No HTTPS verification** | MITM attacks, data interception | httpx default is to verify HTTPS; don't disable unless absolutely necessary (never) |
| **Pass user input directly to API query** | SQL-injection analogue (query injection) | Validate and sanitize drug names (alphanumeric + common symbols only) |
| **No rate limit enforcement** | Banned IP, legal issues with data source | Implement rate limiter matching source's stated limits + monitor for 429s |
| **Download all records then filter client-side** | Download sensitive data (FAERS events) unnecessarily | Use source API filters, download only what's needed |

---

## UX Pitfalls

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| **Output CSV order different each run** | User's downstream scripts break | Ensure consistent column order in CSV export (use `csv.DictWriter` with fieldnames in fixed order) |
| **No source attribution in results** | User doesn't know where signal came from | Include `source` field and `source_record_id` in every record for traceability |
| **Risk score with no explanation** | User distrusts the number | Include `risk_score_breakdown` field showing per-source contributions |
| **Date formats inconsistent** | User confusion on signal recency | Always ISO 8601 in output JSON; clearly document in README |
| **Long actor runtime with no progress updates** | User thinks actor is hung | Call `Actor.set_status_message()` after every 100 records with count/ETA |
| **Silent failures** | User thinks run succeeded when it didn't | Always report final status: "X signals found, Y parse failures, Z records dropped" |
| **Input parameter names don't match API docs** | User provides wrong parameter | Use exact field names from drug_name, drug_class, etc. and document each clearly |

---

## "Looks Done But Isn't" Checklist

- [ ] **Scraper returns data:** Often missing — verify with real inputs (e.g., "ibuprofen", "aspirin") not just test queries
- [ ] **All 4 sources implemented:** Often missing one source's error handling — manually test each source in isolation
- [ ] **Data normalized:** Often missing date parsing, drug name handling — check output JSON schema validity
- [ ] **Rate limiting tested:** Often missing real-world throttling simulation — test with rate_limit_interval=0.5 (very slow) to verify robustness
- [ ] **Edge cases handled:** Often missing null/empty fields — test with drug names that return no FAERS data, no trials, etc.
- [ ] **Async cleanup:** Often missing task cancellation — test ctrl+c during run, verify no orphaned tasks
- [ ] **Input validation:** Often missing error messages — test with missing required fields, invalid dates
- [ ] **Memory profiling:** Often missing resource limits — run locally with `top` or `memory_profiler`, verify memory release after push
- [ ] **Output verified:** Often missing — manually inspect first 10 records from each source for format/content correctness
- [ ] **Marketplace README:** Often missing limitations (fuzzy matching, rate limits, data lag) — document known issues explicitly

---

## Recovery Strategies

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| **Partial data loss from a source** | LOW | Rerun actor (idempotent). If data was pushed to dataset, query dataset API to find records from that source, delete, rerun. |
| **Rate limit lockout (IP blocked)** | MEDIUM | Wait 1-2 hours. If using Apify, run from different IP (Apify proxy). Consider API key (v2 feature). |
| **Schema mismatch in output** | HIGH | Requires code change + re-run to regenerate dataset. If users already consumed output, may break downstream. Document migration. |
| **OOM crash (no output)** | LOW | Lower batch size (50 instead of 100), retry. If issue persists, reduce max_results. |
| **Async hang/timeout** | MEDIUM | Reduce number of concurrent sources, increase timeouts, check logs for which source hung. Requires debugging + rerun. |
| **Risk score corruption** | HIGH | Requires code fix + dataset cleanup. Potentially breaking for users relying on score. |

---

## Pitfall-to-Phase Mapping

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Uncontrolled resource exhaustion | Phase 1 | Profiling: run with all 4 sources, verify CPU/memory stable. Actor completes within 10 min for typical query. |
| Conflicting rate limits | Phase 1 | Test each source at its documented limit. Verify backoff logs show per-source rate limit hits. No 429 errors in successful runs. |
| Schema mismatches | Phase 1 | Validate 10 records from each source through Pydantic. JSON schema check passes. |
| Silent data loss | Phase 1 | Assert parse_failures < 5%. Actor status message lists failure count. |
| Async task leaks | Phase 1 | Stress test with max_results=10000. Verify memory stable, no timeout. |
| Date format chaos | Phase 1 | Date fields always ISO 8601 in output. Parse test samples from each source. |
| Memory bloat | Phase 1 | Memory stays <300MB for 5000-record runs. |
| Risk score unreliability | Phase 2 | Score calculation tested on known high/low risk drugs. Score explanation documented. |
| Drug name normalization | Phase 2 | RxNorm integration deferred. v1 uses exact match only. |
| Input validation mismatch | Phase 1 | Test with valid and invalid inputs. Error messages clear. |

---

## Sources

- **Existing actor patterns**: `/home/labrat/Github Projects/pubmed-scraper/src/`, `/home/labrat/Github Projects/fda-adverse-events-scraper/src/`
  - Rate limiting strategy: `utils.py` RateLimiter + exponential backoff in fetch_xml()
  - Async error handling: main.py exception handling, state tracking
  - Data normalization: models.py Pydantic schemas, parse_adverse_event() logic

- **NCBI E-utilities documentation** (observed from pubmed-scraper)
  - Rate limits: 3 req/sec without API key (0.34s interval default)
  - Tool identification required: tool + email params mandatory
  - Retry logic: Implemented in utils.py fetch_xml() with exponential backoff

- **openFDA API documentation** (observed from fda-adverse-events-scraper)
  - Rate limits: 100 req/minute per IP (rolling window)
  - Search syntax: Field-specific syntax with `field:"value"` required
  - Timeout handling: Long queries can exceed 30s, requires retry

- **Python async best practices** (asyncio documentation)
  - Task management: TaskGroup cancellation (Python 3.11+)
  - Resource management: AsyncClient context manager pattern
  - Timeout patterns: asyncio.wait() with timeout parameter

---

*Pitfalls research for: Drug Signal Radar (Apify actor, multi-source drug intelligence aggregation)*
*Researched: 2026-03-14*
*Confidence: HIGH (based on existing codebase patterns + domain requirements)*
