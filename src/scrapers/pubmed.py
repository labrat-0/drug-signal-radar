from __future__ import annotations

import logging
from typing import AsyncGenerator

import httpx
from apify import Actor

from src.models import PubMedRecord, ScraperInput
from src.utils.rate_limiter import RateLimiter, fetch_with_backoff

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
EFETCH_BATCH = 20  # NCBI recommends max 20 per EFetch batch
TOOL_NAME = "DrugSignalRadar"
TOOL_EMAIL = "actor@apify.com"


class PubMedFetcher:
    """Fetches PubMed papers via NCBI E-utilities ESearch + EFetch.

    Uses two-step pattern:
    1. ESearch: Get list of PMIDs matching drug + date range
    2. EFetch: Retrieve full records in batches of 20

    Yields PubMedRecord for each valid paper.
    Skips malformed records (logs warning, increments failed count).
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        rate_limiter: RateLimiter,
        config: ScraperInput,
        state: dict,
    ) -> None:
        self.client = client
        self.rate_limiter = rate_limiter
        self.config = config
        self.state = state

        # Warn if unsupported filter provided
        if config.severity_threshold:
            Actor.log.warning(
                f"severityThreshold='{config.severity_threshold}' is not applicable "
                "to PubMed. Filtering FAERS only."
            )

    async def fetch(self) -> AsyncGenerator[PubMedRecord, None]:
        """Async generator yielding PubMedRecord instances."""
        pmids = await self._esearch()
        if not pmids:
            Actor.log.info("PubMed: no results found for query.")
            return

        # Fetch in batches of EFETCH_BATCH
        fetched = 0
        for i in range(0, len(pmids), EFETCH_BATCH):
            batch_ids = pmids[i : i + EFETCH_BATCH]
            records = await self._efetch(batch_ids)
            for record in records:
                if fetched >= self.config.max_results:
                    return
                yield record
                self.state["pubmed_count"] = self.state.get("pubmed_count", 0) + 1
                self.state["scraped"] = self.state.get("scraped", 0) + 1
                fetched += 1

        await Actor.set_status_message(f"PubMed: complete ({fetched} papers)")

    async def _esearch(self) -> list[str]:
        """Run ESearch to get list of PMIDs matching drug name + date range."""
        term = self.config.drug_name
        params: dict = {
            "db": "pubmed",
            "term": term,
            "retmax": min(self.config.max_results, 10000),
            "retmode": "json",
            "usehistory": "n",
            "tool": TOOL_NAME,
            "email": TOOL_EMAIL,
        }
        if self.config.date_from:
            # NCBI date format: YYYY/MM/DD
            params["mindate"] = self.config.date_from.replace("-", "/")
            params["datetype"] = "pdat"
        if self.config.date_to:
            params["maxdate"] = self.config.date_to.replace("-", "/")
            params["datetype"] = "pdat"

        await Actor.set_status_message("PubMed: searching...")
        data = await fetch_with_backoff(self.client, ESEARCH_URL, self.rate_limiter, params)
        if not data:
            return []

        try:
            ids = data["esearchresult"]["idlist"]
            total = int(data["esearchresult"].get("count", 0))
            Actor.log.info(f"PubMed: found {total} total results, fetching up to {len(ids)}")
            return ids
        except (KeyError, ValueError) as e:
            Actor.log.error(f"PubMed ESearch response parsing failed: {e}")
            return []

    async def _efetch(self, pmids: list[str]) -> list[PubMedRecord]:
        """Fetch full records for a batch of PMIDs in MEDLINE format. Returns list of valid PubMedRecord."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "medline",
            "retmode": "text",
            "tool": TOOL_NAME,
            "email": TOOL_EMAIL,
        }
        Actor.log.info(f"PubMed EFetch: requesting {len(pmids)} PMIDs (ids={params['id'][:50]}...)")
        response_text = await self._fetch_medline(params)
        if not response_text:
            Actor.log.warning(f"PubMed EFetch: no response for batch of {len(pmids)} PMIDs")
            return []

        records = []
        # MEDLINE format: records separated by blank lines
        record_blocks = response_text.split("\n\n")
        for block in record_blocks:
            if not block.strip():
                continue
            try:
                record = self._parse_medline_record(block)
                if record:
                    records.append(record)
            except Exception as e:
                Actor.log.warning(
                    f"PubMed: skipping MEDLINE record: {type(e).__name__}: {e}"
                )
                self.state["pubmed_failed"] = self.state.get("pubmed_failed", 0) + 1
                self.state["failed"] = self.state.get("failed", 0) + 1

        return records

    async def _fetch_medline(self, params: dict) -> str | None:
        """Fetch MEDLINE format (returns text, not JSON). Uses fetch_with_backoff but handles text response."""
        from src.utils.rate_limiter import RateLimiter
        await self.rate_limiter.wait()
        try:
            response = await self.client.get(EFETCH_URL, params=params, timeout=30.0)
            if response.status_code == 200:
                return response.text
            if response.status_code == 404:
                return None
            if response.status_code in {429, 500, 502, 503}:
                Actor.log.warning(f"HTTP {response.status_code} from EFetch, treating as retriable")
                return None
            Actor.log.warning(f"Unexpected HTTP {response.status_code} from EFetch")
            return None
        except Exception as e:
            Actor.log.warning(f"Error fetching MEDLINE: {type(e).__name__}: {e}")
            return None

    def _parse_article(self, article: dict) -> PubMedRecord:
        """Parse a single PubmedArticle JSON dict into PubMedRecord."""
        medline = article["MedlineCitation"]
        pmid = str(medline["PMID"])

        article_data = medline["Article"]
        title = article_data.get("ArticleTitle", "")
        if isinstance(title, dict):
            title = title.get("#text", str(title))

        # Abstract may be structured (list of sections) or simple string
        abstract_raw = article_data.get("Abstract", {}).get("AbstractText", "")
        if isinstance(abstract_raw, list):
            abstract = " ".join(
                item.get("#text", str(item)) if isinstance(item, dict) else str(item)
                for item in abstract_raw
            )
        elif isinstance(abstract_raw, dict):
            abstract = abstract_raw.get("#text", "")
        else:
            abstract = str(abstract_raw)

        # Authors: list of LastName + ForeName
        authors_list = article_data.get("AuthorList", {}).get("Author", [])
        if isinstance(authors_list, dict):
            authors_list = [authors_list]
        authors = []
        for author in authors_list:
            last = author.get("LastName", "")
            first = author.get("ForeName", "")
            if last:
                authors.append(f"{last}, {first}".strip(", "))

        # Publication year from PubDate
        pub_date = article_data.get("Journal", {}).get("JournalIssue", {}).get("PubDate", {})
        pub_year = pub_date.get("Year", pub_date.get("MedlineDate", ""))[:4]

        return PubMedRecord(
            pmid=pmid,
            title=str(title),
            abstract=abstract,
            pub_year=pub_year,
            authors=authors,
        )

    def _parse_medline_record(self, medline_text: str) -> PubMedRecord | None:
        """Parse a MEDLINE format record (text format).

        MEDLINE format:
        PMID- 12345678
        OWN - NLM
        STAT- PubMed
        TI  - Article title
        AB  - Abstract text
        AU  - Author name
        FAU - Full Author name
        ...
        """
        lines = medline_text.strip().split("\n")
        fields = {}
        current_field = None
        current_value = []

        for line in lines:
            if not line:
                continue
            # Field lines start with a 4-char code followed by "- "
            if len(line) >= 6 and line[4:6] == "- ":
                # Save previous field if exists
                if current_field:
                    field_code = current_field.strip()
                    field_value = " ".join(current_value).strip()
                    if field_code not in fields:
                        fields[field_code] = []
                    fields[field_code].append(field_value)
                # Start new field
                current_field = line[:4]
                current_value = [line[6:]]
            elif current_field:
                # Continuation of previous field (indented)
                current_value.append(line)

        # Don't forget the last field
        if current_field:
            field_code = current_field.strip()
            field_value = " ".join(current_value).strip()
            if field_code not in fields:
                fields[field_code] = []
            fields[field_code].append(field_value)

        # Extract required fields
        pmid_list = fields.get("PMID", [])
        if not pmid_list:
            return None
        pmid = pmid_list[0]

        title = fields.get("TI", [""])[0]
        abstract = " ".join(fields.get("AB", []))
        authors = [author.split(" (")[0] for author in fields.get("AU", [])]  # Remove affiliations

        # Extract year from publication date (DP field)
        pub_date = fields.get("DP", [""])[0]
        pub_year = pub_date[:4] if pub_date and pub_date[0].isdigit() else ""

        return PubMedRecord(
            pmid=pmid,
            title=title,
            abstract=abstract,
            pub_year=pub_year,
            authors=authors,
        )

    def _safe_get_pmid(self, article: dict) -> str:
        try:
            return str(article["MedlineCitation"]["PMID"])
        except Exception:
            return "unknown"
