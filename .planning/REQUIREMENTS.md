# Requirements: Drug Signal Radar

**Defined:** 2026-03-14
**Core Value:** A researcher or analyst queries a drug name and gets one structured JSON combining papers, adverse events, trials, and recall alerts — no manual cross-referencing.

## v1 Requirements

MVP scope: 14 features for initial launch. All features grounded in research analysis of existing Apify actors and multi-source aggregation patterns.

### Data Aggregation & Sources

- [x] **AGG-01**: Actor fetches PubMed papers via NCBI E-utilities API (reuse pubmed-scraper fetcher)
- [x] **AGG-02**: Actor fetches FAERS adverse events via openFDA API (reuse fda-adverse-events-scraper fetcher)
- [x] **AGG-03**: Actor fetches ClinicalTrials.gov trials via REST API v2
- [x] **AGG-04**: Actor fetches FDA drug enforcement alerts via openFDA /drug/enforcement endpoint
- [x] **AGG-05**: Actor combines all four sources into single unified JSON output per drug

### Input & Filtering

- [x] **INP-01**: Actor accepts `drugName` input parameter (string, required)
- [x] **INP-02**: Actor accepts optional `dateFrom` and `dateTo` for temporal filtering (ISO 8601 format)
- [x] **INP-03**: Actor accepts optional `severityThreshold` for FAERS filtering (e.g., "serious_only")
- [x] **INP-04**: Actor accepts optional `maxResults` limit per source (default 100, free tier capped at 25)
- [x] **INP-05**: Actor validates inputs (non-empty drug name, sensible date ranges) and rejects invalid input with clear error message

### Data Normalization & Output

- [ ] **NRM-01**: Actor normalizes PubMed records to standard schema (pmid, title, abstract, pub_year, authors, source)
- [ ] **NRM-02**: Actor normalizes FAERS records to standard schema (event_id, reaction, serious_flag, report_date, patient_age, source)
- [ ] **NRM-03**: Actor normalizes ClinicalTrials records to standard schema (trial_id, title, status, phase, enrollment, source)
- [ ] **NRM-04**: Actor normalizes FDA enforcement records to standard schema (alert_id, action_type, description, report_date, source)
- [ ] **NRM-05**: Unified JSON output includes `schema_version` and `aggregated_at` timestamp
- [ ] **OUT-01**: Actor outputs unified JSON with drug_name, risk_score, summary counts, and four source arrays (papers[], adverse_events[], trials[], fda_alerts[])
- [ ] **OUT-02**: Actor outputs source status metadata (success/partial_failure/failed) for each data source
- [ ] **OUT-03**: Actor supports CSV export via Apify dataset API

### API Coordination & Reliability

- [x] **API-01**: Actor implements rate limiting (0.5 req/sec default, per-source adjustment for PubMed/openFDA limits)
- [x] **API-02**: Actor implements exponential backoff retry on rate limit hits (1s → 2s → 4s, max 5 retries)
- [x] **API-03**: Actor handles partial source failures gracefully (if one source fails, others still return data)
- [x] **API-04**: Actor implements per-source error handling (skip malformed records, continue iteration)
- [x] **API-05**: Actor aborts run if any source fails (after exhausting retries); all-or-nothing semantics ensure users get complete drug signal intelligence or a clear failure signal to retry

### Execution & Monitoring

- [x] **EXE-01**: Actor uses Apify SDK async patterns (Actor.get_input(), Actor.push_data(), Actor context manager)
- [x] **EXE-02**: Actor pushes data in batches of 25 records via Actor.push_data() to balance throughput vs. memory
- [x] **EXE-03**: Actor uses Actor.set_status_message() to show progress (e.g., "Fetching PubMed...", "✓ Complete: 45 papers")
- [x] **EXE-04**: Actor tracks execution state (records_fetched, records_failed per source) via Actor.use_state()

### Risk Scoring & Free Tier

- [ ] **SCO-01**: Actor computes basic risk_score per drug using v1 formula: (adverse_event_count × severity_multiplier) + trial_failure_rate + recall_flag
- [ ] **MON-01**: Actor enforces free tier limits (max 25 results per source on free tier via APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING)
- [ ] **MON-02**: Actor provides clear logging and error messages via Actor.log

### Marketplace & Documentation

- [ ] **MKT-01**: Actor includes `.actor/input_schema.json` defining all input parameters and defaults
- [ ] **MKT-02**: Actor includes comprehensive README with example queries, input modes, output schema, and error documentation
- [ ] **MKT-03**: Actor is published to Apify marketplace with clear title, description, and tags

## v1.x Requirements (Deferred Post-Launch)

Features to add once v1 is live and user feedback drives priorities.

### Enhancement & Enrichment

- **ENH-01**: Multi-source signal correlation (detect same drug in multiple sources, boost risk score)
- **ENH-02**: Severity stratification (separate results by risk level: critical/high/medium/low)
- **ENH-03**: Source credibility weighting (different weights per source: FDA > Trials > FAERS > PubMed)
- **ENH-04**: Publication recency highlighting (`days_since_published` field, boost recent signals)
- **ENH-05**: Trial status summaries (aggregate counts of active/recruiting/completed trials)
- **ENH-06**: Regulatory timeline (chronological FDA enforcement actions)
- **ENH-07**: Manufacturer/company tracking (separate results by drug manufacturer)
- **ENH-08**: Enhanced error reporting (detailed logs of source failures and retry attempts)

## Out of Scope (v2+ or Explicit Exclusions)

| Feature | Reason |
|---------|--------|
| Real-time webhook notifications | Apify is batch-based; webhooks require persistent infrastructure. Users can schedule hourly runs via Apify scheduler. |
| Historical time-series tracking | Requires external time-series database. Apify datasets are designed for batch output, not time-indexed storage. |
| ML-based risk scoring | Regulatory liability (FDA scrutiny), training data complexity, model drift. v1 uses transparent weighted formula. |
| RxNorm drug name normalization | External API dependency adds complexity. Fuzzy string matching is 90% as effective. |
| Full-text paper retrieval | Copyright/licensing complexity, storage costs. Return metadata + links; users access papers themselves. |
| Patient demographics aggregation | Privacy concerns even with de-identified data. Return raw fields; users aggregate themselves. |
| Daily email digests | Out of Apify actor scope; requires separate email workflow tool. |
| Company enrichment (industry, location, stock ticker) | Nice-to-have; defer until clear user demand. |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| AGG-01 | 1 | Complete |
| AGG-02 | 1 | Complete |
| AGG-03 | 1 | Complete |
| AGG-04 | 1 | Complete |
| AGG-05 | 1 | Complete (01-05) |
| INP-01 | 1 | Complete (01-01) |
| INP-02 | 1 | Complete (01-01) |
| INP-03 | 1 | Complete (01-01) |
| INP-04 | 1 | Complete (01-01) |
| INP-05 | 1 | Complete |
| NRM-01 | 2 | Pending |
| NRM-02 | 2 | Pending |
| NRM-03 | 2 | Pending |
| NRM-04 | 2 | Pending |
| NRM-05 | 2 | Pending |
| OUT-01 | 2 | Pending |
| OUT-02 | 2 | Pending |
| OUT-03 | 2 | Pending |
| API-01 | 1 | Complete (01-01) |
| API-02 | 1 | Complete (01-01) |
| API-03 | 1 | Complete |
| API-04 | 1 | Complete |
| API-05 | 1 | Complete (01-05) |
| EXE-01 | 1 | Complete (01-01) |
| EXE-02 | 1 | Complete (01-05) |
| EXE-03 | 1 | Complete |
| EXE-04 | 1 | Complete (01-05) |
| SCO-01 | 2 | Pending |
| MON-01 | 3 | Pending |
| MON-02 | 3 | Pending |
| MKT-01 | 3 | Pending |
| MKT-02 | 3 | Pending |
| MKT-03 | 3 | Pending |

**Coverage:**
- v1 requirements: 32 total
- Mapped to phases: 32 (Phase 1: 18, Phase 2: 9, Phase 3: 5)
- Unmapped: 0 ✓

---
*Requirements defined: 2026-03-14*
*Traceability updated: 2026-03-14 after roadmap creation*
