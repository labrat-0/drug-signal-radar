# Roadmap: Drug Signal Radar

**Project:** Multi-source drug intelligence aggregation actor
**Created:** 2026-03-14
**Granularity:** Coarse
**Total Requirements:** 32 v1 requirements
**Coverage:** 32/32 requirements mapped

---

## Phases

- [ ] **Phase 1: Architecture & Data Integration** - Build foundation for async multi-source fetching with rate limiting and input validation
- [ ] **Phase 2: Normalization & Output** - Unify schemas, implement risk scoring, finalize output formats
- [ ] **Phase 3: Marketplace & Launch** - Marketplace documentation, monitoring/logging, production validation

---

## Phase Details

### Phase 1: Architecture & Data Integration

**Goal:** Users can query any drug and retrieve raw data from all four sources with proper rate limiting, retry logic, and input validation.

**Depends on:** Nothing (first phase)

**Requirements:** AGG-01, AGG-02, AGG-03, AGG-04, INP-01, INP-02, INP-03, INP-04, INP-05, EXE-01, EXE-02, EXE-03, EXE-04, API-01, API-02, API-03, API-04, API-05 (18 requirements)

**Success Criteria** (what must be TRUE):
1. Actor accepts drug name, optional date range, optional severity threshold, and max results parameters without errors
2. Actor fetches and returns data from all four sources (PubMed, FAERS, ClinicalTrials, FDA Enforcement) concurrently without rate limit (429) errors
3. Actor implements exponential backoff retry (1s → 2s → 4s, max 5 retries) and gracefully handles partial source failures
4. Actor batches records in groups of 25 and pushes to Apify dataset without memory spikes
5. Actor completes typical multi-source query in under 10 minutes with visible progress messages

**Plans:** TBD

---

### Phase 2: Normalization & Output

**Goal:** Users receive unified, machine-readable JSON from all sources with consistent field names, standardized dates, and a risk score per drug.

**Depends on:** Phase 1

**Requirements:** NRM-01, NRM-02, NRM-03, NRM-04, NRM-05, OUT-01, OUT-02, OUT-03, SCO-01 (9 requirements)

**Success Criteria** (what must be TRUE):
1. Actor outputs unified JSON with all four source arrays (papers[], adverse_events[], trials[], fda_alerts[]) and per-drug risk_score
2. All dates across all sources are ISO 8601 format; no source-specific date formats in output
3. PubMed records include (pmid, title, abstract, pub_year, authors); FAERS include (event_id, reaction, serious_flag, report_date, patient_age); ClinicalTrials include (trial_id, title, status, phase, enrollment); FDA include (alert_id, action_type, description, report_date)
4. Actor includes schema_version and aggregated_at timestamp in output; each source shows success/partial_failure/failed status
5. Actor outputs support both JSON and CSV format via Apify dataset API

**Plans:** TBD

---

### Phase 3: Marketplace & Launch

**Goal:** Actor is production-ready and publicly available on Apify marketplace with clear documentation and proper monitoring.

**Depends on:** Phase 2

**Requirements:** MON-01, MON-02, MKT-01, MKT-02, MKT-03 (5 requirements)

**Success Criteria** (what must be TRUE):
1. Actor enforces free tier limits (max 25 results per source) via APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING environment variables
2. Actor provides clear logging throughout execution via Actor.log with status messages (e.g., "Fetching PubMed...", "✓ Complete: 45 papers")
3. Actor includes .actor/input_schema.json defining all parameters (drugName, dateFrom, dateTo, severityThreshold, maxResults) with types and defaults
4. Actor includes comprehensive README with example queries, output schema documentation, error codes, and usage instructions
5. Actor is published to Apify marketplace with title, description, tags, and link to GitHub repository

**Plans:** TBD

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Architecture & Data Integration | 0/? | Not started | - |
| 2. Normalization & Output | 0/? | Not started | - |
| 3. Marketplace & Launch | 0/? | Not started | - |

---

*Roadmap created: 2026-03-14*
