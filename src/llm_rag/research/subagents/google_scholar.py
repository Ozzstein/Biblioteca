from __future__ import annotations

import logging

from llm_rag.research.coordinator import CandidateDocument

logger = logging.getLogger(__name__)


class GoogleScholarSubagent:
    """Stub — requires SERPAPI_KEY and SerpAPI integration (not yet implemented)."""

    def __init__(self, serpapi_key: str) -> None:
        self.serpapi_key = serpapi_key
        if not serpapi_key:
            logger.info("GoogleScholarSubagent: no SERPAPI_KEY — returning empty results")

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        return []

    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None:
        return None
