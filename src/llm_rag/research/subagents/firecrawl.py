from __future__ import annotations

from firecrawl import V1FirecrawlApp

from llm_rag.research.coordinator import CandidateDocument


class FirecrawlSubagent:
    def __init__(self, api_key: str) -> None:
        self._app = V1FirecrawlApp(api_key=api_key)

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        return []

    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None:
        if not candidate.source_url:
            return None
        response = self._app.scrape_url(candidate.source_url, formats=["markdown"])
        markdown = response.markdown
        if not markdown:
            return None
        return markdown.encode("utf-8"), "md"
