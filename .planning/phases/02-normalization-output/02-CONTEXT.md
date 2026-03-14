# Phase 2: Normalization & Output - Context

**Gathered:** 2026-03-14
**Status:** Ready for planning
**Source:** Requirements & Roadmap

---

## Phase Boundary

Phase 2 transforms Phase 1's raw, source-specific data into a unified, normalized JSON output with:
- **Consistent field names** across all four sources (papers[], adverse_events[], trials[], fda_alerts[])
- **ISO 8601 date standardization** (no source-specific date formats in final output)
- **Unified output schema** with schema_version, aggregated_at, and source status metadata
- **Basic risk scoring** per drug using v1 formula
- **CSV export support** via Apify dataset API

Input: Raw records from Phase 1 fetchers (PubMed, FAERS, ClinicalTrials, FDA Enforcement)
Output: Single unified JSON per drug query with all four source arrays normalized to standard schema

---

## Implementation Decisions

### Data Normalization: Locked by Requirements

**NRM-01: PubMed Record Schema**
- Input: Raw PubMed/EFetch JSON from Phase 1
- Normalize to: `{pmid, title, abstract, pub_year, authors[], source: "pubmed"}`
- Locked: Field names and order per .actor/dataset_schema.json

**NRM-02: FAERS Record Schema**
- Input: Raw openFDA FAERS JSON from Phase 1
- Normalize to: `{event_id, reaction, serious_flag, report_date (ISO 8601), patient_age, source: "faers"}`
- Locked: Date format is ISO 8601 only (convert YYYYMMDD if needed)

**NRM-03: ClinicalTrials Record Schema**
- Input: Raw ClinicalTrials.gov v2 API JSON from Phase 1
- Normalize to: `{trial_id (NCT...), title, status, phase, enrollment, source: "clinical_trials"}`
- Locked: Phase field must be string ("Phase 1", "Phase 2", etc. or "N/A" if not applicable)

**NRM-04: FDA Enforcement Record Schema**
- Input: Raw openFDA /drug/enforcement JSON from Phase 1
- Normalize to: `{alert_id, action_type, description, report_date (ISO 8601), source: "fda_enforcement"}`
- Locked: Date format is ISO 8601 only

**NRM-05: Unified Output Metadata**
- Every output MUST include `schema_version: "1.0"` and `aggregated_at: <ISO 8601 timestamp>`
- Locked decision: Version 1.0, timestamp in UTC

### Output Format: Locked by Requirements

**OUT-01: Unified JSON Structure**
- Output format: Top-level object with drug_name, aggregated_at, schema_version, papers[], adverse_events[], trials[], fda_alerts[], sources {}
- Locked by: dataset_schema.json definition
- Per .planning/phases/01-architecture-data-integration/01-CONTEXT.md: "Output: single unified JSON"

**OUT-02: Source Status Metadata**
- Every output includes `sources: {papers: "success|partial_failure|failed", adverse_events: ..., trials: ..., fda_alerts: ...}`
- Locked: Status values are exactly "success", "partial_failure", or "failed" (per Phase 1 design)

**OUT-03: CSV Export Support**
- Must support export via Apify dataset API (native feature once data is pushed)
- Locked: No special CSV export code needed; Apify handles CSV serialization on top of JSON dataset

### Risk Scoring: Locked by Requirements

**SCO-01: Basic Risk Score Formula**
- Formula: `risk_score = (adverse_event_count × serious_event_multiplier) + trial_failure_rate + fda_recall_flag`
- Locked constants:
  - serious_event_multiplier = 5.0 (serious events weighted 5x higher than non-serious)
  - trial_failure_rate = (failed_trials / total_trials) if total_trials > 0 else 0.0
  - fda_recall_flag = 1.0 if any FDA enforcement action is a "recall", else 0.0
- Output: risk_score as float per drug in final JSON
- Note: This is a v1 placeholder formula for transparency. ML-based scoring deferred to v2 per requirements.

### Claude's Discretion

1. **Normalization error handling:** How to handle records that don't match expected schema (e.g., missing pmid in PubMed record)? Decision: Log warning, skip record, increment error counter but don't fail entire run (per Phase 1's "graceful failure" pattern)

2. **Date parsing edge cases:** Some sources may have invalid or missing dates. Decision: If date cannot be parsed to ISO 8601, set date field to null and log warning.

3. **Author/reaction list normalization:** PubMed authors come as list; FAERS reactions may be list or string. Decision: Always output as arrays (for consistency), converting single strings to [string].

4. **NULL vs empty array distinction:** When a record field is missing (e.g., no ClinicalTrials found), should output be null or []? Decision: Use empty array [] for source collections (papers: [], adverse_events: []) to avoid null-checking in downstream consumers.

5. **Risk score per source:** Should we compute risk_score per source or per drug? Decision: Per drug (single risk_score in output), computed from all four sources combined.

---

## Specific Ideas

- Normalization functions should be modular (one function per source) so Phase 2 plans can test each independently
- Each normalizer should validate output against dataset_schema.json before final output
- Consider using Pydantic models (already imported in Phase 1) to enforce schema during normalization
- Risk score should be rounded to 2 decimal places for readability

---

## Deferred Ideas

Per requirements, these are out of scope for v1:
- Multi-source signal correlation (ENH-01)
- Severity stratification beyond serious_flag (ENH-02)
- Source credibility weighting (ENH-03)
- Publication recency highlighting (ENH-04)
- ML-based risk scoring (scope creep protection)

---

*Phase: 02-normalization-output*
*Context gathered: 2026-03-14 from ROADMAP.md and REQUIREMENTS.md*
