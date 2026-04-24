from __future__ import annotations

import arxiv
import httpx

from llm_rag.research.coordinator import CandidateDocument


class ArXivSubagent:
    def __init__(self, max_results: int = 20) -> None:
        self.max_results = max_results

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        client = arxiv.Client()
        candidates: list[CandidateDocument] = []
        for topic in topics:
            search = arxiv.Search(
                query=topic,
                max_results=self.max_results,
                sort_by=arxiv.SortCriterion.SubmittedDate,
            )
            for result in client.results(search):
                arxiv_id = result.entry_id.split("/")[-1]
                candidates.append(
                    CandidateDocument(
                        title=result.title,
                        abstract=result.summary,
                        source="arxiv",
                        doi=result.doi or None,
                        arxiv_id=arxiv_id,
                        pdf_url=result.pdf_url,
                        published_year=result.published.year if result.published else None,
                        authors=[str(a) for a in result.authors],
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
