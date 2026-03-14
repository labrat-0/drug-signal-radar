# Feature Research: Multi-Source Drug Intelligence Aggregation

**Domain:** Healthcare data aggregation actor (Apify)
**Researched:** 2026-03-14
**Confidence:** HIGH — Analyzed 2 mature single-source actors, mapped Apify SDK patterns, studied marketplace expectations

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist. Missing these = product feels incomplete for aggregation actors.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Multi-source aggregation** | Product's core value prop — what differentiates from single-source actors | HIGH | Combine PubMed + FAERS + ClinicalTrials + FDA into one output |
| **Input filtering by drug** | Users query by drug name/class, not broad searches | MEDIUM | Fuzzy matching for drug name variants; pass to each source |
| **Unified JSON output** | Standard for Apify actors; enables downstream tooling | MEDIUM | Schema with source arrays (papers[], events[], trials[], alerts[]) |
| **Structured data normalization** | Raw API outputs differ; users expect consistent fields | HIGH | Map each source's schema to unified fields (date, severity, source_id) |
| **Rate limiting / retry logic** | Respects upstream API limits; prevents blocking/bans | MEDIUM | Built into existing actors; essential for multi-source parallelization |
| **Error handling & partial failure** | If one source fails, others should still return data | MEDIUM | Graceful degradation: skip failed source, continue aggregation |
| **Basic input validation** | Reject invalid inputs before making API calls | LOW | Validate drug name not empty, date ranges sensible |
| **Free tier / paid limits** | Monetization model; existing actors enforce 25 result free limit | LOW | Enforce free tier limits consistently across all sources |
| **Batch processing / streaming output** | Return data as it arrives rather than waiting for all sources | MEDIUM | Push data in batches via `Actor.push_data()` |
| **Status messages during execution** | Users monitor long-running jobs; show progress | LOW | Use `Actor.set_status_message()` as sources complete |
| **Date range filtering** | Temporal scoping; research often needs "last 6 months" | MEDIUM | Implement per-source with fallback defaults |
| **Severity/seriousness filtering** | FAERS users filter serious events only | MEDIUM | Apply severity thresholds where available (FAERS: serious flag) |
| **CSV export option** | Apify marketplace standard; enables spreadsheet workflows | LOW | Convert JSON dataset to CSV via Apify dataset export API |

### Differentiators (Competitive Advantage)

Features that set the product apart. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Risk score aggregation** | Single metric combining adverse events + trials + recalls — enables rapid triage | MEDIUM | Weighted formula v1: (event_count × severity) + trial_failure_rate + recall_flag |
| **Multi-source signal correlation** | Same drug appearing in multiple sources signals stronger evidence | HIGH | Detect overlaps (same drug in FAERS + ClinicalTrials = potential serious signal) |
| **Severity stratification** | Break results by risk level (critical/high/medium/low) for rapid scanning | MEDIUM | Separate output arrays by severity, highlight critical alerts |
| **Source credibility weighting** | FDA recalls > published trials > adverse event reports — weight accordingly | MEDIUM | Different weights per source type in risk calculation |
| **Company/manufacturer tracking** | Identify which company's version of drug is problematic | MEDIUM | Normalize manufacturer names, flag by company in output |
| **Publication recency highlighting** | Flag recent papers/events as more relevant than old ones | LOW | Add `days_since_published` field, boost recent events in risk score |
| **Citation count for papers** | Show PubMed citation count to identify influential research | LOW | Included in PubMed API; adds credibility signal |
| **Trial status summary** | Show count of active/completed/recruiting trials (not just raw list) | LOW | Aggregate trial statuses into summary counts |
| **Regulatory action timeline** | Show FDA recall/enforcement dates chronologically | LOW | Sort enforcement actions by date, highlight recency |
| **Structured MCP tool integration** | Expose as MCP tool for AI agents (like pubmed-scraper does) | MEDIUM | Support AI workflows via Claude, Cursor, etc. |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems.

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Real-time webhooks** | "Alert me immediately when adverse event appears" | Apify is batch-based; webhooks require persistent infrastructure and state management; cost/complexity explosion | Advise users to schedule actor runs hourly via Apify scheduler (free, out-of-the-box) |
| **Historical time-series tracking** | "Show me 12-month trend of adverse events" | Requires storing previous runs, diff logic, time-indexed DB — adds massive complexity; Apify datasets aren't built for this | Defer to v2; users can aggregate runs manually or build external time-series DB |
| **Machine learning risk scoring** | "Use ML to predict drug safety" | Regulatory liability (FDA scrutiny); training data requirements; model drift; hard to explain to users | Keep v1 simple: transparent weighted formula; makes rationale auditable |
| **RxNorm API integration** | "Auto-normalize drug names (ibuprofen → NSAIDs)" | External API adds dependency; requires additional auth; increases latency; fuzzy matching is 90% as good | Use fuzzy string matching (fuzzywuzzy) in v1; defer RxNorm to v2 |
| **Full-text paper retrieval** | "Give me the complete paper PDF, not just abstract" | Copyright/licensing complexity; storage costs; slow downloads; most papers behind paywalls anyway | Keep as metadata (links to PubMed Central, DOI); let users fetch themselves |
| **Detailed patient demographics aggregation** | "Show me adverse event breakdown by age/gender" | Privacy concerns (even de-identified); FAERS data isn't robust for this; complex aggregation logic | Return raw patient fields; let users aggregate themselves |
| **Manual report validation** | "Flag which adverse events are likely real vs noise" | Requires domain expertise + human labeling; not scalable; liability (you vouch for reports); users expect research, not validation | Clearly document: FAERS is voluntary, unvalidated data; caveat emptor |
| **Scheduled daily email digests** | "Email me new signals every morning" | Adds external email infrastructure; user management; unsubscribe handling; scope creep | Out of scope for v1; users can build automation via Zapier/Make |

## Feature Dependencies

```
Input Validation
    └──requires──> Basic Input Filtering (drug name, date range)
                       └──requires──> Data Source APIs (PubMed, FAERS, etc.)
                                          └──requires──> Rate Limiting / Retry Logic
                                          └──requires──> Error Handling & Partial Failure
                                                            └──requires──> Unified JSON Output
                                                                    └──enhances──> CSV Export
                                                                    └──enhances──> Status Messages

Unified JSON Output
    └──enhances──> Risk Score Aggregation
    └──enhances──> Signal Correlation (multi-source overlap detection)
    └──enhances──> Severity Stratification

Severity Filtering
    └──requires──> Structured Data Normalization (need severity field from each source)
```

### Dependency Notes

- **Input Validation requires Basic Input Filtering:** Can't filter effectively without validating drug name exists and date ranges make sense
- **Data Source APIs require Rate Limiting:** All four APIs have rate limits; without limiter, will get blocked or throttled
- **Rate Limiting requires Error Handling:** When rate limit is hit, must retry gracefully without losing data
- **Error Handling requires Unified JSON Output:** Must have consistent schema so downstream code can handle missing fields from failed sources
- **Risk Score Aggregation requires Structured Normalization:** Can't weight scores if you don't normalize severity/event count across sources
- **Signal Correlation enhances Unified Output:** The value of correlation is seeing the same drug in multiple sources — requires normalized lookups

## MVP Definition

### Launch With (v1)

Minimum viable product — what's needed to validate the concept.

- [x] **Multi-source aggregation** — Core value; fetch from all 4 sources, combine into single output
- [x] **Input filtering by drug name** — Users query by drug, not browse all data
- [x] **Unified JSON output per drug** — Arrays for papers[], events[], trials[], alerts[]
- [x] **Structured data normalization** — Consistent field names across sources (date, severity, source_id, title, description)
- [x] **Rate limiting & retry logic** — Respect API limits; don't get blocked
- [x] **Error handling & partial failure** — If FAERS fails, still return PubMed + Trials + FDA
- [x] **Basic input validation** — Reject empty drug names, invalid date ranges
- [x] **Date range filtering** — Allow "last 6 months" queries
- [x] **Severity threshold filtering** — FAERS: filter serious events only
- [x] **Basic risk score (v1 formula)** — Weighted: adverse_event_count × severity + trial_failure_rate + recall_flag
- [x] **Batch processing / streaming output** — Push data in chunks via Actor.push_data()
- [x] **Status messages** — Update progress as sources complete
- [x] **Free tier limits** — 25 results per source on free tier
- [x] **CSV export option** — Via Apify dataset API

### Add After Validation (v1.x)

Features to add once core is working and user feedback drives priorities.

- [ ] **Multi-source signal correlation** — Detect same drug appearing in multiple sources; boost risk score
- [ ] **Severity stratification in output** — Separate result arrays by risk level (critical/high/medium/low)
- [ ] **Source credibility weighting** — Different weights per source (FDA > Trials > FAERS > PubMed)
- [ ] **Publication recency highlighting** — `days_since_published` field, highlight recent signals
- [ ] **Trial status summaries** — Aggregate counts of active/recruiting/completed trials
- [ ] **Regulatory timeline** — Chronological FDA enforcement actions
- [ ] **Enhanced error reporting** — Detailed logs of which source failed and why
- [ ] **Manufacturer/company tracking** — Separate results by drug manufacturer

### Future Consideration (v2+)

Features to defer until product-market fit is established or operational complexity warrants.

- [ ] **Real-time webhook notifications** — Requires persistent infrastructure; defer until paid tier justifies it
- [ ] **Historical time-series tracking** — Requires external time-series DB; out of Apify's scope
- [ ] **RxNorm API drug name normalization** — Fuzzy matching is sufficient for v1; add official normalization in v2
- [ ] **Machine learning risk scoring** — Regulatory liability + training data complexity; stay with transparent formula longer
- [ ] **Full-text paper retrieval** — Copyright/licensing complexity; users can access via PubMed links
- [ ] **Patient demographics aggregation** — Privacy concerns; defer until user demand is clear
- [ ] **Scheduled daily digests / email alerts** — Out of Apify actor scope; requires separate workflow tool
- [ ] **Company enrichment (industry, location, stock ticker)** — Nice to have; defer until user need is clear

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Multi-source aggregation | HIGH | HIGH | **P1** |
| Input filtering (drug name) | HIGH | MEDIUM | **P1** |
| Unified JSON output | HIGH | MEDIUM | **P1** |
| Structured normalization | HIGH | HIGH | **P1** |
| Rate limiting / retry | HIGH | MEDIUM | **P1** |
| Error handling (partial failure) | HIGH | MEDIUM | **P1** |
| Basic risk score | HIGH | MEDIUM | **P1** |
| Batch processing / streaming | MEDIUM | MEDIUM | **P1** |
| Status messages | MEDIUM | LOW | **P1** |
| Date range filtering | HIGH | MEDIUM | **P1** |
| Severity threshold filtering | HIGH | LOW | **P1** |
| CSV export | MEDIUM | LOW | **P1** |
| Free tier limits | MEDIUM | LOW | **P1** |
| Input validation | MEDIUM | LOW | **P1** |
| **Signal correlation (multi-source)** | HIGH | HIGH | **P2** |
| **Severity stratification** | MEDIUM | MEDIUM | **P2** |
| **Source weighting** | MEDIUM | MEDIUM | **P2** |
| Recency highlighting | MEDIUM | LOW | **P2** |
| Trial status summary | MEDIUM | LOW | **P2** |
| Manufacturer tracking | MEDIUM | MEDIUM | **P2** |
| MCP tool integration | LOW | MEDIUM | **P3** |
| Regulatory timeline | MEDIUM | LOW | **P3** |
| Real-time webhooks | MEDIUM | VERY HIGH | **P4** (defer) |
| Historical time-series | MEDIUM | VERY HIGH | **P4** (defer) |
| ML scoring | LOW | VERY HIGH | **P4** (defer) |

**Priority key:**
- **P1 (v1, launch):** Must have for core concept validation
- **P2 (v1.x, early feedback):** Should have once core works; user feedback may shift priority
- **P3 (v2, established product):** Nice to have; build after PMF
- **P4 (defer):** High complexity, low immediate ROI; revisit after user adoption

## Input/Output Specification for MVP

### Input Schema (from Actor.get_input())

```json
{
  "drugName": "atorvastatin",
  "drugClass": "",
  "manufacturer": "",
  "dateFrom": "2023-01-01",
  "dateTo": "2024-12-31",
  "includeTrials": true,
  "includeAdverseEvents": true,
  "includePapers": true,
  "includeFDAAlerts": true,
  "severityThreshold": "serious",
  "maxResults": 100,
  "requestIntervalSecs": 0.5
}
```

### Output Schema (per drug)

```json
{
  "schema_version": "1.0",
  "aggregated_at": "2026-03-14T12:00:00Z",
  "drug_name": "atorvastatin",
  "drug_class": "statin",
  "risk_score": 7.2,
  "summary": {
    "total_papers": 45,
    "total_adverse_events": 234,
    "total_trials": 12,
    "total_fda_alerts": 2
  },
  "papers": [
    {
      "type": "article",
      "pmid": "33243215",
      "title": "...",
      "abstract": "...",
      "pub_year": 2023,
      "authors": [],
      "source": "pubmed"
    }
  ],
  "adverse_events": [
    {
      "type": "adverse_event",
      "event_id": "10003300",
      "reaction": "myocardial infarction",
      "serious": true,
      "report_date": "2023-06-15",
      "patient_age": "77",
      "source": "faers"
    }
  ],
  "trials": [
    {
      "type": "trial",
      "trial_id": "NCT03456789",
      "title": "...",
      "status": "recruiting",
      "phase": "phase_3",
      "enrollment": 450,
      "source": "clinicaltrials"
    }
  ],
  "fda_alerts": [
    {
      "type": "alert",
      "alert_id": "...",
      "action_type": "recall",
      "description": "...",
      "report_date": "2023-09-20",
      "source": "fda_enforcement"
    }
  ],
  "sources": {
    "pubmed": {
      "status": "success",
      "records_fetched": 45,
      "query_used": "atorvastatin"
    },
    "faers": {
      "status": "success",
      "records_fetched": 234,
      "query_used": "atorvastatin"
    },
    "clinicaltrials": {
      "status": "success",
      "records_fetched": 12,
      "query_used": "atorvastatin"
    },
    "fda_enforcement": {
      "status": "partial_failure",
      "records_fetched": 2,
      "error": "Request timeout; using cached enforcement data"
    }
  }
}
```

### Handling Multi-Source Variability

| Source | Strength | Limitation |
|--------|----------|-----------|
| **PubMed (via NCBI E-utilities)** | Peer-reviewed, rich metadata, global | Slower API, respects 3 req/sec limit |
| **FAERS (via openFDA)** | Real-world adverse events, high volume, structured | Voluntary reporting (noisy), no causality proof |
| **ClinicalTrials.gov (REST API v2)** | Authoritative trial data, structured, well-documented | Only registered trials, slower updates |
| **FDA Enforcement (via openFDA /drug/enforcement)** | Regulatory actions, high credibility, JSON structured | Lower volume, less granular than FAERS |

## Error Handling Strategy

### Per-Source Failure Modes

| Scenario | Handling |
|----------|----------|
| **Source API is down (503)** | Log error, return empty array for that source, continue aggregation |
| **Rate limit hit (429)** | Apply exponential backoff (1s → 2s → 4s), retry up to 5 times |
| **Malformed API response** | Log error, skip record, continue iteration (don't crash whole run) |
| **Timeout (30s+)** | Abort that source, use cached data if available, warn user |
| **All sources fail** | Fail the actor run; user sees error in Apify console |
| **One source partially fails** | Return partial results; include source status metadata so user knows what succeeded |

### User Communication

- **Status messages:** Update every 10-15 seconds per source completion
  - "Fetching PubMed papers..."
  - "✓ PubMed complete (45 papers)"
  - "Fetching FAERS adverse events..."
  - "⚠ FAERS partial (234/unknown due to timeout)"
  - "Done. 4 sources aggregated, 1 partial failure"

## Marketplace Requirements (Apify)

These are non-negotiable to publish on Apify marketplace:

| Requirement | Implementation |
|-------------|-----------------|
| **README with clear examples** | Document all input modes, show example queries, explain output |
| **Input schema JSON** | `.actor/input_schema.json` defining all input parameters |
| **Meaningful error messages** | Validate inputs, provide actionable feedback |
| **Free tier limits** | 25 results per source on free tier; up to 1,000 on paid |
| **Rate limiting** | Built-in respect for API limits; don't abuse upstream services |
| **Proper logging** | Use Actor.log for debugging; visible in Apify console |
| **Dataset export capability** | Output must be Apify dataset-compatible (JSON objects) |
| **Descriptive actor metadata** | Title, description, categories, tags for marketplace discovery |

## Sources

- **Existing actors analyzed:**
  - `/home/labrat/Github Projects/pubmed-scraper/` — Single-source pattern: input modes, validation, rate limiting, free tier enforcement
  - `/home/labrat/Github Projects/fda-adverse-events-scraper/` — Single-source pattern: search modes, error handling, batch processing

- **Project context:**
  - `/home/labrat/Github Projects/drug-signal-radar/.planning/PROJECT.md` — Core requirements, tech stack, constraints

- **Apify SDK patterns:**
  - Actor.get_input() / Actor.push_data() / Actor.set_status_message() — standard patterns from existing actors
  - Free tier model: 25 results default, checked via APIFY_IS_AT_HOME + APIFY_USER_IS_PAYING

- **Data source documentation (inferred from project):**
  - NCBI E-utilities API (PubMed) — 3 req/sec limit without key
  - openFDA API — documented openFDA enforcement endpoint for drug recalls
  - ClinicalTrials.gov API v2 — official REST API (project context)
  - openFDA /drug/enforcement — structured JSON drug enforcement endpoint (project context)

---

*Feature research for: Multi-source drug intelligence aggregation actor (Apify)*
*Researched: 2026-03-14*
