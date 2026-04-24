from __future__ import annotations

import httpx

from llm_rag.research.coordinator import CandidateDocument

_UNPAYWALL_BASE = "https://api.unpaywall.org/v2"


class UnpaywallSubagent:
    def __init__(self, email: str) -> None:
        self.email = email

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        return []

    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None:
        if not candidate.doi:
            return None
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{_UNPAYWALL_BASE}/{candidate.doi}",
                params={"email": self.email},
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            location = data.get("best_oa_location")
            if not location:
                return None
            pdf_url: str | None = location.get("url_for_pdf")
            if not pdf_url:
                return None
            pdf_response = await client.get(pdf_url, follow_redirects=True, timeout=60.0)
            pdf_response.raise_for_status()
            return pdf_response.content, "pdf"
