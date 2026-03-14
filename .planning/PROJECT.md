# Drug Signal Radar

## What This Is

An Apify actor that aggregates real-time drug intelligence signals from four public sources (PubMed, FAERS, ClinicalTrials.gov, FDA alerts/recalls), normalizes them into a unified per-drug JSON output, and publishes to the Apify marketplace. It reuses parsing logic from existing actors (`pubmed-scraper`, `fda-adverse-events-scraper`) and follows the same Python/Apify SDK pattern as those repos.

## Core Value

A researcher or analyst queries a drug name and gets one structured JSON combining papers, adverse events, trials, and recall alerts — no manual cross-referencing.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Actor accepts drug name/class/company filters, optional date range, optional severity threshold
- [ ] Fetches and normalizes PubMed papers (reuse pubmed-scraper logic)
- [ ] Fetches and normalizes FAERS adverse events (reuse fda-adverse-events-scraper logic)
- [ ] Fetches and normalizes ClinicalTrials.gov trials (new source)
- [ ] Fetches and normalizes FDA drug alerts and recalls (new source)
- [ ] Outputs unified JSON per drug with all four source arrays
- [ ] Outputs CSV format option via Apify dataset API
- [ ] Includes a simple risk score (weighted formula, v1)
- [ ] Published to Apify marketplace with full README and input schema

### Out of Scope

- Real-time webhook notifications — v2, requires persistent run infrastructure
- Historical data tracking / time series — v2
- Company/manufacturer enrichment — v2
- Daily scheduled updates — v2 (Apify scheduler can be configured by user post-launch)
- RxNorm API integration for drug name normalization — v2 (use fuzzy matching in v1)
- Local Ollama models at actor runtime — actors run on Apify cloud; local models are dev-workflow only

## Context

- **Existing repos to reuse:** `pubmed-scraper` (Python, NCBI E-utilities API), `fda-adverse-events-scraper` (Python, openFDA API), `academic-paper-scraper` (DOI cross-referencing)
- **Tech stack:** Python, `apify` SDK (async with Actor pattern), `httpx` for HTTP, `pydantic` or dataclasses for models — consistent with existing actors
- **Repo pattern:** `src/main.py`, `src/models.py`, `src/scrapers/`, `src/utils/`, `.actor/` directory for Apify metadata
- **New data sources:** ClinicalTrials.gov (REST API v2 at clinicaltrials.gov/api/v2), FDA recall RSS/enforcement endpoint (openFDA /drug/enforcement)
- **Dev workflow:** Use local RAG (Qdrant + nomic-embed-text) to reference indexed existing repos during planning and coding phases

## Constraints

- **Tech stack:** Python (consistent with all existing actors) — not JS despite original spec
- **Apify platform:** Must use `apify` SDK patterns: `Actor.get_input()`, `Actor.push_data()`, `Actor.set_status_message()`, `.actor/input_schema.json`
- **APIs:** All four data sources have public APIs — no scraping required, no auth needed for basic access
- **Risk score v1:** Simple weighted formula only — no ML, no external scoring service

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over JS | All existing actors are Python; reuse logic directly without port | — Pending |
| openFDA for recalls | `/drug/enforcement` endpoint is structured JSON, far cleaner than RSS/HTML parsing | — Pending |
| ClinicalTrials.gov API v2 | Official REST API, no scraping needed | — Pending |
| Risk score in v1 | Simple formula (adverse event count × severity + recall flag + trial failures) — unblocks downstream use | — Pending |

---
*Last updated: 2026-03-14 after initialization*
