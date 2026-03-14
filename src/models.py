from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel


class ScraperInput(BaseModel):
    drug_name: str = ""
    date_from: str = ""  # ISO 8601, optional
    date_to: str = ""  # ISO 8601, optional
    severity_threshold: str = ""  # FAERS-only; "serious_only" or ""
    max_results: int = 100

    @classmethod
    def from_actor_input(cls, raw: dict[str, Any]) -> ScraperInput:
        return cls(
            drug_name=raw.get("drugName", ""),
            date_from=raw.get("dateFrom", ""),
            date_to=raw.get("dateTo", ""),
            severity_threshold=raw.get("severityThreshold", ""),
            max_results=raw.get("maxResults", 100),
        )

    def validate_for_mode(self) -> str | None:
        if not self.drug_name.strip():
            return "drugName is required and cannot be empty"
        if self.max_results < 1 or self.max_results > 10000:
            return "maxResults must be between 1 and 10000"
        # Date validation: if both set, from must be <= to
        if self.date_from and self.date_to:
            if self.date_from > self.date_to:
                return f"dateFrom ({self.date_from}) must be before dateTo ({self.date_to})"
        return None


class PubMedRecord(BaseModel):
    source: str = "pubmed"
    pmid: str
    title: str
    abstract: str = ""
    pub_year: str = ""  # ISO 8601 year or YYYY-MM-DD
    authors: list[str] = []


class FAERSRecord(BaseModel):
    source: str = "faers"
    event_id: str
    reaction: str
    serious_flag: bool = False
    report_date: str = ""  # ISO 8601
    patient_age: str = ""  # raw string (age units vary in FAERS)


class ClinicalTrialRecord(BaseModel):
    source: str = "clinicaltrials"
    trial_id: str  # NCT number
    title: str
    status: str = ""  # Recruiting, Completed, etc.
    phase: str = ""  # Phase 1, Phase 2, N/A, etc.
    enrollment: int | None = None


class FDAEnforcementRecord(BaseModel):
    source: str = "fda_enforcement"
    alert_id: str
    action_type: str  # Recall, Warning, Market Withdrawal
    description: str = ""
    report_date: str = ""  # ISO 8601


class SourceState(str, Enum):
    SUCCESS = "success"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


class SourceStatus(BaseModel):
    source: str
    state: SourceState
    records_fetched: int = 0
    records_failed: int = 0
    error_message: str = ""
