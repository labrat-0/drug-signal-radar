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
        """Fetch full records for a batch of PMIDs. Returns list of valid PubMedRecord."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "rettype": "abstract",
            "retmode": "json",
            "tool": TOOL_NAME,
            "email": TOOL_EMAIL,
        }
        data = await fetch_with_backoff(self.client, EFETCH_URL, self.rate_limiter, params)
        if not data:
            return []

        records = []
        articles = data.get("PubmedArticleSet", {}).get("PubmedArticle", [])
        if isinstance(articles, dict):
            articles = [articles]  # Single result comes back as dict, not list

        for article in articles:
            try:
                record = self._parse_article(article)
                records.append(record)
            except Exception as e:
                pmid = self._safe_get_pmid(article)
                Actor.log.warning(f"PubMed: skipping article pmid={pmid}: {e}")
                self.state["pubmed_failed"] = self.state.get("pubmed_failed", 0) + 1
                self.state["failed"] = self.state.get("failed", 0) + 1

        return records

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

    def _safe_get_pmid(self, article: dict) -> str:
        try:
            return str(article["MedlineCitation"]["PMID"])
        except Exception:
            return "unknown"
