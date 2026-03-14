# Drug Signal Radar

> **Unified drug intelligence from four authoritative sources — PubMed, FDA adverse events, clinical trials, and enforcement actions. One query, complete picture.**

Aggregate pharmaceutical intelligence from multiple federal sources into a single, structured dataset. Perfect for drug safety monitoring, competitive analysis, and research.

[![Apify](https://img.shields.io/badge/Apify-Actor-blue)](https://apify.com)
[![Python](https://img.shields.io/badge/python-3.12-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## What This Actor Does

Drug Signal Radar queries **four authoritative public health data sources simultaneously** and returns unified JSON combining:

- **PubMed** — 35M+ medical literature articles via NCBI E-utilities
- **FDA Adverse Events (FAERS)** — Safety reports from openFDA FAERS endpoint
- **ClinicalTrials.gov** — Active/completed trials via ClinicalTrials.gov v2 API
- **FDA Enforcement** — Drug recalls, market withdrawals, enforcement actions via openFDA

All with **proper rate limiting, retry logic, and error handling** — no 429 errors or cascading failures.

## 🚀 Key Features

- **No API Keys Required** — All four sources are free public APIs
- **Concurrent Multi-Source Fetching** — Fetch from all 4 sources in parallel (with semaphore-based rate limiting)
- **Unified Output Schema** — Consistent, normalized JSON across all sources
- **Intelligent Rate Limiting** — Global 0.5 req/sec with exponential backoff (1s→2s→4s, max 5 retries)
- **Batch Processing** — Pushes data in batches of 25 records for efficiency
- **Free Tier Available** — Max 25 results per source for free users
- **Progress Tracking** — Real-time status messages showing fetch progress

## 📊 Use Cases & ROI

### Pharmaceutical & Biotech
- **Drug Safety Monitoring** — Track adverse events for your products vs competitors
- **Competitive Intelligence** — Analyze competitor trial pipelines and safety signals
- **Target Validation** — Identify safety risks and clinical trial data for drug targets
- **Regulatory Preparation** — Gather comprehensive safety and trial data for FDA submissions

### Healthcare & Research
- **Formulary Decisions** — Compare drug safety, trial outcomes, and adverse events
- **Literature Reviews** — Combine academic papers with real-world safety and trial data
- **Patient Safety Programs** — Identify emerging safety signals across all sources
- **Clinical Research** — Find relevant trials and adverse event patterns for your therapeutic area

### Market Intelligence
- **Pipeline Analysis** — Track competitor clinical trials and pipeline maturity
- **Safety Signal Detection** — Early detection of drug safety issues across sources
- **Market Entry Risk** — Assess regulatory, safety, and competitive landscape before launch

## 🎯 Input Configuration

### Basic Query

```json
{
  "drugName": "Aspirin",
  "maxResults": 100
}
```

Returns up to 100 results per source for Aspirin from all four sources.

### Advanced Filtering

```json
{
  "drugName": "Metformin",
  "dateFrom": "2023-01-01",
  "dateTo": "2024-12-31",
  "severityThreshold": "serious",
  "maxResults": 50
}
```

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `drugName` | string | ✓ | — | Drug name or brand name to search |
| `dateFrom` | date (ISO 8601) | | — | Start date for results (YYYY-MM-DD) |
| `dateTo` | date (ISO 8601) | | — | End date for results (YYYY-MM-DD) |
| `severityThreshold` | string | | — | Filter FAERS to "serious" events only |
| `maxResults` | number | | 25 | Max results per source (free tier: 25, paid: unlimited) |

## 📋 Output Format

Returns unified JSON with all four source arrays plus metadata:

```json
{
  "drug_name": "Aspirin",
  "aggregated_at": "2024-03-14T12:34:56Z",
  "schema_version": "1.0",
  "papers": [
    {
      "pmid": "12345678",
      "title": "Aspirin efficacy in cardiovascular disease",
      "abstract": "...",
      "pub_year": "2023",
      "authors": ["Smith, J", "Jones, M"]
    }
  ],
  "adverse_events": [
    {
      "event_id": "FAE123456",
      "reaction": "Gastrointestinal bleeding",
      "serious_flag": true,
      "report_date": "2024-03-10",
      "patient_age": 65
    }
  ],
  "trials": [
    {
      "trial_id": "NCT12345678",
      "title": "Phase 3 Trial: Aspirin in Primary Prevention",
      "status": "Active, recruiting",
      "phase": "Phase 3",
      "enrollment": 500
    }
  ],
  "fda_alerts": [
    {
      "alert_id": "ENFD123456",
      "action_type": "Market Withdrawal",
      "description": "Aspirin formulation recall due to...",
      "report_date": "2023-06-15"
    }
  ],
  "sources": {
    "papers": "success",
    "adverse_events": "success",
    "trials": "success",
    "fda_alerts": "partial_failure"
  }
}
```

### Source Status Values

- `success` — All records fetched successfully
- `partial_failure` — Some records failed, partial data returned
- `failed` — Source failed completely, empty array

## ⚙️ Technical Details

### Architecture

- **Async/concurrent execution** with asyncio + httpx
- **Global rate limiter** (Semaphore(2)) prevents cascading failures
- **Exponential backoff** on 429/503/502/500 errors (1s → 2s → 4s, max 5 retries)
- **Batch push** every 25 records to Apify dataset
- **10-minute execution timeout** for typical multi-source queries

### Deployment

- **Python 3.12** with Apify SDK 2.0+
- **Docker** deployment to Apify platform
- **Free tier**: Max 25 results per source
- **Paid tier**: Unlimited results, higher rate limits

### Dependencies

- `apify>=2.0.0` — Apify SDK for actor framework
- `httpx>=0.27.0` — Async HTTP client for concurrent requests
- `pydantic>=2.0.0` — Data validation and schema enforcement

## 🔧 Local Testing

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables (optional for local testing)
export APIFY_IS_AT_HOME=False

# Run locally
python -m src
```

When running locally, the actor will push data to a local dataset (if APIFY_IS_AT_HOME=False) or to Apify platform (if APIFY_TOKEN is set).

## 📝 License

Apache 2.0 — Free for personal and commercial use.

---

*Built on Apify platform. Queries public health APIs: NCBI E-utilities, openFDA, ClinicalTrials.gov, Apify.*
