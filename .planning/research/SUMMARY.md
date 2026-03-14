# Project Research Summary

**Project:** Drug Signal Radar
**Domain:** Apify actor for multi-source drug intelligence aggregation (healthcare data pipeline)
**Researched:** 2026-03-14
**Confidence:** HIGH

## Executive Summary

Drug Signal Radar is a multi-source data aggregation actor that combines intelligence from four healthcare APIs (PubMed, FAERS/openFDA, ClinicalTrials.gov, FDA Enforcement) into unified drug safety signals. This is a production data pipeline built on Apify's actor framework, requiring careful async orchestration, rate limit coordination across heterogeneous APIs, and robust data normalization. The recommended approach uses Python 3.12 with httpx for async HTTP, Pydantic for schema validation, and a layered pipeline architecture with separate fetcher, parser, and aggregation components.

The core challenge is not individual API integration—existing actors (pubmed-scraper, fda-adverse-events-scraper) already handle single sources well. The challenge is coordinating four concurrent fetchers with conflicting rate limits, aggregating heterogeneous schemas into a unified output, and managing memory/CPU in Apify's constrained environment. Success depends on upfront architecture decisions around async task management, batching strategy, and schema design, all of which must be correct before Phase 1 launches.

Three major risks require Phase 1 attention: uncontrolled resource exhaustion from concurrent fetchers, silent data loss from parsing failures across 40K+ potential records, and schema mismatches causing score calculations to fail. All three are architectural concerns that can't be fixed post-launch without breaking consumers.

## Key Findings

### Recommended Stack

The stack is well-established from working existing actors: Python 3.12 (Apify's standard base image), apify>=2.0.0 SDK for actor context management, httpx>=0.27.0 for async HTTP with built-in connection pooling and retries, and Pydantic>=2.0.0 for schema validation. Supporting libraries include python-dateutil for heterogeneous date format parsing, xmltodict for PubMed XML responses, and tenacity for complex retry scenarios (optional; existing exponential backoff in utils is proven). Development tools must include pytest+pytest-asyncio, black, ruff, and mypy for type safety.

**Core technologies:**
- **Python 3.12**: Apify actor base image with excellent async/await support and type hints
- **apify SDK >=2.0.0**: Actor framework providing context manager, push_data(), input/output handling, state management
- **httpx >=0.27.0**: Modern async HTTP client replacing requests; required for concurrent multi-API aggregation with connection pooling
- **pydantic >=2.0.0**: Schema validation for input, models, and output records with v2 performance improvements (50x faster than v1)
- **python-dateutil >=2.8.2**: Essential for normalizing dates across four sources returning different formats (ISO 8601, YYYYMMDD, RFC 2822, partial dates)

### Expected Features

MVP table stakes are multi-source aggregation, input filtering by drug name, unified JSON output, structured data normalization, rate limiting with retry logic, error handling with partial failure recovery, basic validation, date range filtering, severity thresholds, and a simple risk score formula. Marketplace requirements include README with examples, input schema JSON, meaningful errors, free tier limits (25 results per source), proper logging, and dataset export compatibility.

**Must have (v1 table stakes):**
- Multi-source aggregation from all four APIs
- Input filtering by drug name, date range, severity threshold
- Unified JSON output with separate arrays per source type (papers[], events[], trials[], alerts[])
- Structured data normalization (consistent field names, types, and dates across sources)
- Rate limiting and retry logic respecting each API's constraints
- Error handling with partial failure recovery (if one source fails, others continue)
- Basic risk score combining adverse event count, severity, trial data, and FDA alerts
- Batch processing and streaming output via Actor.push_data()
- Free tier enforcement (25 results per source)
- Input validation and status messages during execution

**Should have (v1.x competitive features, deferred until core working):**
- Multi-source signal correlation (same drug appearing in multiple sources signals stronger evidence)
- Severity stratification (separate output arrays by risk level)
- Source credibility weighting (FDA recalls weighted higher than adverse event reports)
- Publication recency highlighting (flag recent signals as more relevant)
- Trial status summaries and regulatory action timelines
- Company/manufacturer tracking

**Defer (v2+, not essential for launch):**
- Real-time webhooks (requires persistent infrastructure; Apify scheduling sufficient for v1)
- Historical time-series tracking (requires external DB; defer until product-market fit established)
- RxNorm API for drug name normalization (fuzzy matching adequate for v1; defer official canonical mapping)
- Machine learning risk scoring (regulatory liability and training complexity; keep transparent formula in v1)
- Full-text paper retrieval (copyright/licensing complexity; links to PDFs sufficient)

### Architecture Approach

The architecture follows a **layered pipeline pattern** with clear separation of concerns: input validation → concurrent fetchers (reusing code from existing actors) → per-source parsers normalizing to Pydantic models → aggregator merging by drug_name → risk scorer enriching with weighted signals → batch exporter to Apify dataset. Each source gets an isolated fetcher yielding records via async generator (memory efficient), a dedicated parser converting source-specific JSON/XML to standard *Record models (Pydantic), and a central aggregator grouping by normalized drug name. This structure allows swapping individual sources without refactoring others.

**Major components:**
1. **Fetchers (PubMed, FAERS, ClinicalTrials, FDA)** — AsyncGenerator yielding raw API responses; each with independent RateLimiter
2. **Parsers** — Convert source JSON/XML to Pydantic models (ArticleRecord, AdverseEventRecord, TrialRecord, AlertRecord) with date normalization
3. **Aggregator** — Merge records by drug_name, compile unified DrugSignal objects nesting all source arrays
4. **Risk Scorer** — Calculate weighted score from per-source signals; normalized by source availability
5. **Exporter** — Batch results to Actor.push_data() with memory flushing; support CSV flattening

### Critical Pitfalls

1. **Uncontrolled resource exhaustion from parallel fetchers** — Four concurrent API calls without global coordination will spike CPU, exhaust connection pool, and trigger rate limits. Use asyncio.Semaphore(max_concurrent=2) to coordinate across sources, not just per-source rate limiting. Push data after each source completes, not after loading all into memory. Never store all results in lists; use async generators throughout.

2. **Conflicting rate limits across four APIs** — NCBI E-utilities (3 req/sec), openFDA (100 req/min), ClinicalTrials.gov (100 req/min), FDA enforcement (unknown). Different backoff strategies compound. Document rate limits as constants; use conservative 0.5 req/sec default; separate retry logic (exponential backoff) from rate limiting (deterministic wait); fail fast if source returns >2 consecutive 429s.

3. **Silent data loss from parsing failures** — Each source has edge cases (missing fields, malformed data, encoding issues). Typical pattern: try/except with continue loses records silently. Track parse failures per source and type; fail run if >10% failure rate; store partial records with error annotations. Test parsing against 100 worst-case records from each source before Phase 1 launch.

4. **Schema mismatches causing downstream breakage** — Normalize dates to ISO 8601 in each parser; inconsistent date formats break risk score calculations. Use Pydantic models with strict types; validate every normalized record. Design unified schema (DrugSignal) with versioning before coding any scraper.

5. **Date format chaos across sources** — PubMed returns mixed formats (YYYY, YYYY-MM, "January 2024"), FAERS uses YYYYMMDD, ClinicalTrials uses ISO 8601, FDA uses RFC 2822. Parse each in source-specific normalizer to ISO 8601; reject unparseable dates (count as parse failure); test with 50 real samples from each source before Phase 1 completes.

## Implications for Roadmap

Based on research, the project has two major phases: Phase 1 (Core Aggregation) finalizes the layered architecture with all async/rate-limiting patterns in place, Phase 2 (Signal Enrichment) adds competitive features like multi-source correlation and severity stratification.

### Phase 1: Core Aggregation & Resource Management
**Rationale:** Core aggregation pipeline and resource management must be correct from the start. Cannot add async patterns, rate limiting, or memory management later without breaking existing consumers. Existing single-source actors (pubmed-scraper, fda-adverse-events-scraper) provide proven patterns for individual sources; Phase 1 focuses on coordinating four sources safely.

**Delivers:**
- Multi-source data aggregation from all four APIs (PubMed, FAERS, ClinicalTrials, FDA Enforcement)
- Unified JSON output schema with source arrays and per-drug metadata
- Input validation and error handling with partial failure recovery
- Rate limiting coordination across four APIs with different policies
- Memory-efficient batching to Apify dataset (async generators, batch push after 100 records)
- Status messages tracking progress per source

**Addresses features:**
- Multi-source aggregation, input filtering, unified output, data normalization, rate limiting, error handling, basic validation, date filtering, severity thresholds, basic risk score, batch processing, status messages, free tier limits

**Avoids pitfalls:**
- Uncontrolled resource exhaustion (via Semaphore + batch-push pattern)
- Conflicting rate limits (via documented constants + conservative defaults + fast-fail on 429s)
- Schema mismatches (via Pydantic models with strict types + pre-designed unified schema)
- Silent data loss (via parse failure tracking, <5% threshold enforcement)
- Async task leaks (via TaskGroup cancellation + per-source timeouts)
- Memory bloat (via async generator streaming + batch push every 100 records)
- Date format chaos (via source-specific normalizers to ISO 8601)

**Architecture pattern:** Layered pipeline with isolated fetchers, per-source parsers, central aggregator, risk scorer, and batch exporter. Reuse existing scraper logic from pubmed-scraper and fda-adverse-events-scraper as base for fetchers. Add new fetchers for ClinicalTrials.gov and FDA Enforcement following same pattern.

**Success criteria:**
- All four sources return data with no 429 errors on typical queries
- Peak memory <300MB for 5000-record runs
- Actor completes in <10 minutes for typical query
- Output JSON validates against Pydantic DrugSignal schema
- Parse failure rate <5%
- All dates in output are ISO 8601

### Phase 2: Signal Enrichment & Competitive Features
**Rationale:** Once core pipeline is stable and Phase 1 users provide feedback, add competitive features that differentiate from basic aggregation. These require the foundation from Phase 1 (unified schema, reliable normalization) but are not essential for MVP validation.

**Delivers:**
- Multi-source signal correlation (detect same drug in multiple sources; boost risk score)
- Severity stratification (output organized by risk level: critical/high/medium/low)
- Source credibility weighting (FDA recalls weighted higher than adverse event reports)
- Publication recency highlighting (days_since_published field, boost recent signals)
- Trial status summaries (count active/recruiting/completed trials)
- Regulatory timeline (chronological FDA enforcement actions)
- Enhanced error reporting (detailed logs of per-source failures)

**Uses:** Risk scorer enhancement, Pydantic model extensions for risk_score_breakdown field, aggregator enhancements for deduplication/correlation logic

**Implements:** Risk score v2 with weighted sources and confidence breakdown

**Success criteria:**
- Risk score explains per-source contributions
- Multi-source signals have higher confidence than single-source
- User feedback confirms competitive value over individual source actors

### Phase 3: Scale & Production Hardening (Post-MVP)
**Rationale:** Once product reaches consistent user load and patterns stabilize, optimize for scale and add operational features.

**Delivers:**
- Performance optimization (source-specific actor parallelization via Apify actor.call())
- Caching layer for frequently queried drugs (Redis or Apify KVS)
- Pre-aggregated indexes for top drugs (materialized views)
- Advanced monitoring and alerting
- Cost optimization for high-volume queries

**Success criteria:** Handle 100K+ signal queries/month with <5s per-query latency

### Phase Ordering Rationale

Phase 1 comes first because async coordination, rate limiting, and schema design are architectural constraints that cannot be refactored later. The pitfalls research clearly shows that uncontrolled concurrency, resource exhaustion, and data loss happen at the fundamental level—attempting to bolt on fixes post-launch breaks existing consumers.

Phase 2 follows once Phase 1 is stable because competitive features depend on the Phase 1 foundation (reliable multi-source normalization, unified schema, proven resource management). Risk score v2, signal correlation, and recency highlighting all require that base layer working correctly.

Phase 3 comes last because it's performance optimization and operational hardening, not MVP validation. Defer until product-market fit is established or user load demands scale.

### Research Flags

**Phases likely needing deeper research during planning:**
- **Phase 1, Data Integration:** ClinicalTrials.gov API v2 and FDA enforcement endpoint specifics need endpoint verification (test actual API responses, confirm pagination, verify rate limit behavior in real conditions). FAERS field mapping needs validation against current API schema (openFDA has evolved since existing actor was built).
- **Phase 2, Risk Scoring:** Risk score formula needs domain expert validation (medical/pharmaceutical safety experts should review weighting). Current formula is placeholder (adverse_event_count × severity + recall_flag + trial_failure_rate); needs evidence-based tuning.

**Phases with standard patterns (can skip detailed research-phase):**
- **Phase 1, Fetchers:** PubMed and FAERS patterns are well-proven in existing actors; existing code can be reused with minor async wrapper changes. RateLimiter and exponential backoff strategies are battle-tested.
- **Phase 1, Async Coordination:** Python 3.11+ asyncio.TaskGroup is standard pattern; no research needed beyond verifying Apify base image supports Python 3.12.
- **Phase 3, Caching/Scale:** Apify KVS documentation is standard; Redis caching follows well-known patterns; can defer deep research until Phase 3 planning.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Verified with existing working actors (pubmed-scraper, fda-adverse-events-scraper); all dependencies documented with version compatibility checks. Apify SDK patterns confirmed across multiple implementations. |
| Features | HIGH | Analyzed two mature single-source actors, mapped marketplace expectations, derived MVP from common Apify actor patterns. Feature prioritization aligns with existing monetization model (free tier limits, paid enhancements). |
| Architecture | HIGH | Layered pipeline pattern extracted from two working codebases. Async generator pattern, Pydantic schema versioning, RateLimiter, and batch push all proven in production. Component boundaries align with existing scraper separation. |
| Pitfalls | HIGH | Top 10 pitfalls synthesized from existing codebase observations, async best practices (TaskGroup, timeout patterns), domain knowledge (medical data sensitivity), and Apify platform constraints. Recovery strategies documented based on failure modes seen in related projects. |

**Overall confidence:** HIGH

All four research areas are based on verified implementations, official documentation, or established best practices. No speculative architecture or untested patterns. The main uncertainty is not in core technology choices or architectural patterns, but in the specific rate limit behavior of ClinicalTrials.gov and FDA enforcement endpoints in production, and in risk score formula tuning (deferred to Phase 2).

### Gaps to Address

1. **ClinicalTrials.gov API v2 rate limits and pagination behavior** — Research inferred from documentation, but actual behavior under load during Phase 1 should be tested against real API. Rate limit enforcement behavior (rolling window vs. hard limit) needs verification.
   - *How to handle:* Include ClinicalTrials API endpoint testing in Phase 1 milestone before MVP launch. Test with max_results=10000 to verify rate limit response. Document actual behavior in code comments.

2. **FDA Enforcement endpoint specifics** — Unclear if endpoint exists as structured JSON or only as RSS. Conflict between project context (mentions "openFDA /drug/enforcement") and PITFALLS research uncertainty.
   - *How to handle:* In Phase 1 planning, validate endpoint exists and returns JSON (not RSS). If only RSS available, use RSS parser (xml.etree) or switch to openFDA FAERS endpoint as primary enforcement data source.

3. **Risk score formula validation** — Current v1 formula is placeholder; lacks domain expert validation. Different drugs may have wildly different signal distributions (popular drugs > adverse events; new drugs > trials). Weighting formula may not be comparable across drug types.
   - *How to handle:* In Phase 2 planning, engage pharmacovigilance domain expert or healthcare researcher to validate scoring formula. Test against known high-risk drugs (thalidomide, rofecoxib) and low-risk (ibuprofen, aspirin) to calibrate weights.

4. **FAERS field schema evolution** — openFDA FAERS endpoint may have changed since fda-adverse-events-scraper was last updated (2026-03-06). Patient/drug/reaction field structure needs verification.
   - *How to handle:* In Phase 1, fetch real sample FAERS data and validate parser against current schema. Update field mappings if openFDA schema has evolved.

5. **Apify actor memory limits in production** — Research assumes 512MB–2GB constraints; actual limits depend on Apify plan tier. Need to verify memory profiling assumptions during Phase 1 testing.
   - *How to handle:* Profile Phase 1 locally with memory_profiler; test on Apify staging environment with different batch sizes (25, 50, 100 records). Document actual memory usage per batch size in Phase 1 completion report.

## Sources

### Primary (HIGH confidence)
- **Existing implementations**: `/home/labrat/Github Projects/pubmed-scraper/` and `/home/labrat/Github Projects/fda-adverse-events-scraper/` — Verified working code for async fetching, rate limiting, Pydantic validation, and Apify SDK integration patterns (created 2026-03-06, actively maintained)
- **Apify SDK documentation** — Actor.get_input(), Actor.push_data(), Actor.use_state() patterns, free tier model via APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING
- **Python asyncio best practices** — TaskGroup cancellation (Python 3.11+), timeout patterns, connection pooling with httpx
- **NCBI E-utilities API** — Rate limits (3 req/sec without key), required parameters (tool, email), XML response structure (verified via pubmed-scraper implementation)
- **openFDA API documentation** — FAERS endpoint rate limits (100 req/min per IP), search query syntax, enforcement endpoint structure (verified via fda-adverse-events-scraper implementation)

### Secondary (MEDIUM confidence)
- **ClinicalTrials.gov API v2 documentation** — REST endpoint structure, pagination via pageNumber, query parameters, response schema (inferred from project context; needs endpoint verification in Phase 1)
- **Python ecosystem standards** — httpx as modern async HTTP client, Pydantic v2 as validation standard, pytest + pytest-asyncio for testing, black + ruff + mypy for code quality
- **Apify marketplace patterns** — Input schema JSON, free tier enforcement, CSV export via dataset API (inferred from pubmed-scraper and fda-adverse-events-scraper implementations)

### Tertiary (LOW confidence / needs validation)
- **FDA Enforcement endpoint format** — Project mentions openFDA /drug/enforcement as JSON endpoint, but PITFALLS research notes uncertainty about format (RSS vs. structured JSON). Needs Phase 1 verification.
- **Risk score formula appropriateness** — Current formula from PROJECT.md is placeholder; lacks domain expert validation. Weighting (adverse_event_count × severity + recall_flag + trial_failure_rate) is heuristic, not evidence-based.
- **FAERS field schema stability** — Assumed current openFDA FAERS response structure matches fda-adverse-events-scraper expectations; needs verification against live API in Phase 1.

---

*Research completed: 2026-03-14*
*Synthesized by: Claude Code (Haiku 4.5)*
*Ready for roadmap creation: YES*
