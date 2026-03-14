# Project State: Drug Signal Radar

**Last Updated:** 2026-03-14
**Mode:** YOLO (coarse granularity, auto-advance enabled after plan verification)
**Current Focus:** Phase 1 execution

---

## Project Reference

**Core Value:** A researcher or analyst queries a drug name and gets one structured JSON combining papers, adverse events, trials, and recall alerts — no manual cross-referencing.

**One-Sentence Goal:** Build an Apify actor that aggregates drug intelligence from four public health APIs into unified, queryable output.

**Current Position:**
- Phase: 1 (Architecture & Data Integration)
- Current Plan: 2 of 5
- Last Completed: 01-01-PLAN.md (Project scaffold, models, rate limiter, HTTP client)

---

## Current Phase Progress

**Phase 1: Architecture & Data Integration**
- Status: In progress
- Current Plan: 2 of 5
- Requirements: 18 (AGG-01-05, INP-01-05, EXE-01-04, API-01-05)
- Success Criteria: 5
- Progress: ██▁▁▁ 20% (1/5 plans complete)

---

## Architecture Decisions

| Decision | Status | Notes |
|----------|--------|-------|
| Python 3.12 + apify SDK | Approved (from PROJECT.md) | Stack consistent with pubmed-scraper and fda-adverse-events-scraper |
| Layered pipeline (Fetchers → Parsers → Aggregator → Scorer → Exporter) | Approved (from research) | Reuse existing scraper patterns; isolate each source |
| Pydantic models for schema validation | Approved (from research) | Strict types prevent silent data loss; version schema from day 1 |
| AsyncIO + Semaphore(2) for rate limit coordination | Approved (from research) | Prevents resource exhaustion; max 2 concurrent sources at a time |
| Batch push every 25 records via Actor.push_data() | Approved (from research) | Balance throughput vs. memory; matches free tier limits |
| Exponential backoff (1s → 2s → 4s, max 5 retries) on 429 errors | Approved (from research) | Documented in API-02 requirement; conservative defaults |

---

## Research Flags (Phase 1 Planning)

**MUST VALIDATE BEFORE LAUNCHING:**

1. **ClinicalTrials.gov API v2 rate limits** — Test actual endpoint behavior under load. Document rate limit response format.
2. **FDA Enforcement endpoint format** — Verify endpoint exists and returns JSON (not RSS). If only RSS, plan RSS parser or use FAERS as fallback.
3. **FAERS field schema** — Fetch real sample data from openFDA FAERS endpoint. Verify field mappings match current schema (not fda-adverse-events-scraper's old schema).
4. **Apify memory limits** — Profile Phase 1 locally with memory_profiler. Test on staging environment with batch sizes (25, 50, 100 records).

**For Planning Later (Phase 2+):**
- Risk score formula needs domain expert validation (current formula is placeholder)
- Scale/caching architecture deferred until product-market fit established

---

## Key Risks & Mitigations

| Risk | Severity | Mitigation |
|------|----------|-----------|
| Uncontrolled concurrency causing resource exhaustion | HIGH | Use asyncio.Semaphore(max_concurrent=2) for global coordination; profile memory early |
| Silent data loss from parsing failures | HIGH | Track parse failures per source; fail run if >5% failure rate; test against 100 worst-case records per source |
| Rate limit cascades across four heterogeneous APIs | HIGH | Document per-source rate limits as constants; use conservative 0.5 req/sec default; separate retry logic from rate limiting |
| Schema mismatches causing downstream breakage | HIGH | Finalize Pydantic models before coding any scraper; validate every normalized record; use strict types |
| Date format chaos across sources | MEDIUM | Normalize to ISO 8601 in each parser; reject unparseable dates; test with 50 real samples per source |
| Free tier enforcement not working | MEDIUM | Test APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING environment variables on staging before marketplace publish |

---

## Accumulated Context

### Session Notes (2026-03-14)
- Roadmap created with 3 phases derived from requirements and research recommendations
- Phase 1 focuses on async architecture and multi-source coordination (architectural must-have)
- Phase 2 focuses on unified schema and output normalization (integration)
- Phase 3 focuses on marketplace publication and monitoring (launch)
- All 32 v1 requirements mapped; no orphans
- Research confidence: HIGH (based on verified existing actors and official API documentation)
- Main unknowns: ClinicalTrials rate limits, FDA enforcement endpoint format, FAERS schema evolution

### Dependencies Between Requirements
- Phases ordered by natural dependency: must have fetchers (Phase 1) before normalizers (Phase 2) before marketplace (Phase 3)
- Within Phase 1: Input validation (INP) required before aggregation (AGG); rate limiting (API) required concurrent with fetching
- Within Phase 2: Normalization (NRM) required before output (OUT); output requires normalization complete
- Within Phase 3: Risk scoring (SCO) required before monitoring (MON); all required before marketplace (MKT)

### Code Reuse Opportunities
- **PubMed fetcher:** Reuse src/scrapers/pubmed.py from pubmed-scraper with async wrapper
- **FAERS fetcher:** Reuse src/scrapers/faers.py from fda-adverse-events-scraper with async wrapper
- **RateLimiter:** Reuse utils/rate_limiter.py from fda-adverse-events-scraper
- **Pydantic models:** Reference academic-paper-scraper and pubmed-scraper for field structure patterns

---

## Blockers & Open Questions

None currently. Research is complete. Roadmap is approved. Ready to plan Phase 1.

---

## Session Continuity

**Last session:** 2026-03-14T19:00:52Z
**Stopped at:** Completed 01-01-PLAN.md

**For next session:**
1. Execute 01-02-PLAN.md (Actor entry point, input validation, free tier enforcement)
2. Continue through plans 01-03 through 01-05
3. During Phase 1 execution, validate research flags (ClinicalTrials rate limits, FDA endpoint format, FAERS schema)

---

*State initialized: 2026-03-14*
