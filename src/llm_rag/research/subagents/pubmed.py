from __future__ import annotations

from typing import Any

import httpx

from llm_rag.research.coordinator import CandidateDocument

_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
_ESUMMARY = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"


def _parse_year(pubdate: str) -> int | None:
    parts = pubdate.strip().split()
    if parts and parts[0].isdigit() and len(parts[0]) == 4:
        return int(parts[0])
    return None


def _extract_doi(articleids: list[dict[str, str]]) -> str | None:
    for item in articleids:
        if item.get("idtype") == "doi":
            return item.get("value")
    return None


class PubMedSubagent:
    def __init__(self, max_results: int = 10) -> None:
        self.max_results = max_results

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        candidates: list[CandidateDocument] = []
        async with httpx.AsyncClient() as client:
            for topic in topics:
                esearch_resp = await client.get(
                    _ESEARCH,
                    params={
                        "db": "pubmed",
                        "term": topic,
                        "retmax": self.max_results,
                        "retmode": "json",
                    },
                    timeout=30.0,
                )
                esearch_resp.raise_for_status()
                idlist: list[str] = esearch_resp.json()["esearchresult"]["idlist"]
                if not idlist:
                    continue

                esummary_resp = await client.get(
                    _ESUMMARY,
                    params={"db": "pubmed", "id": ",".join(idlist), "retmode": "json"},
                    timeout=30.0,
                )
                esummary_resp.raise_for_status()
                result_map: dict[str, Any] = esummary_resp.json().get(
                    "result", {}
                )

                for pmid in idlist:
                    item = result_map.get(pmid)
                    if not item:
                        continue
                    author_list = [
                        a["name"]
                        for a in (item.get("authors") or [])
                        if a.get("name")
                    ]
                    candidates.append(
                        CandidateDocument(
                            title=item.get("title") or "",
                            abstract="",
                            source="pubmed",
                            doi=_extract_doi(item.get("articleids") or []),
                            published_year=_parse_year(item.get("pubdate") or ""),
                            authors=author_list,
                        )
                    )
        return candidates

    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None:
        return None
