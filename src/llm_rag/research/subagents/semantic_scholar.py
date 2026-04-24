from __future__ import annotations

import httpx

from llm_rag.research.coordinator import CandidateDocument

_S2_BASE = "https://api.semanticscholar.org/graph/v1/paper/search"
_S2_FIELDS = "title,abstract,year,authors,externalIds,openAccessPdf"


class SemanticScholarSubagent:
    def __init__(self, max_results: int = 15) -> None:
        self.max_results = max_results

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        candidates: list[CandidateDocument] = []
        async with httpx.AsyncClient() as client:
            for topic in topics:
                response = await client.get(
                    _S2_BASE,
                    params={"query": topic, "limit": self.max_results, "fields": _S2_FIELDS},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                for item in data.get("data", []):
                    ext_ids: dict[str, str] = item.get("externalIds") or {}
                    oa_pdf = item.get("openAccessPdf")
                    candidates.append(
                        CandidateDocument(
                            title=item.get("title") or "",
                            abstract=item.get("abstract") or "",
                            source="semantic_scholar",
                            doi=ext_ids.get("DOI"),
                            arxiv_id=ext_ids.get("ArXiv"),
                            pdf_url=oa_pdf["url"] if oa_pdf else None,
                            published_year=item.get("year"),
                            authors=[a["name"] for a in (item.get("authors") or [])],
                        )
                    )
        return candidates

    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None:
        if not candidate.pdf_url:
            return None
        async with httpx.AsyncClient() as client:
            response = await client.get(
                candidate.pdf_url, follow_redirects=True, timeout=30.0
            )
            response.raise_for_status()
            return response.content, "pdf"
