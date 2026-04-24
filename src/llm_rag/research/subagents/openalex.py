from __future__ import annotations

import httpx

from llm_rag.research.coordinator import CandidateDocument

_OA_BASE = "https://api.openalex.org/works"
_OA_FIELDS = "id,title,abstract_inverted_index,doi,publication_year,authorships,primary_location"


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
    """Reconstruct abstract from OpenAlex inverted index format.

    OpenAlex returns abstracts as a dict mapping words to position lists:
    {"We": [0], "study": [1], "LFP": [2]}
    This reconstructs the original string by placing words at their positions.
    """
    if not inverted_index:
        return ""
    total = max(pos for positions in inverted_index.values() for pos in positions) + 1
    words: list[str] = [""] * total
    for word, positions in inverted_index.items():
        for pos in positions:
            words[pos] = word
    return " ".join(words)


class OpenAlexSubagent:
    def __init__(self, max_results: int = 20) -> None:
        self.max_results = max_results

    async def search(self, topics: list[str]) -> list[CandidateDocument]:
        candidates: list[CandidateDocument] = []
        async with httpx.AsyncClient() as client:
            for topic in topics:
                response = await client.get(
                    _OA_BASE,
                    params={"search": topic, "per-page": self.max_results, "select": _OA_FIELDS},
                    headers={"User-Agent": "llm-rag/1.0 (mailto:research@example.com)"},
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()
                for item in data.get("results", []):
                    doi_raw: str | None = item.get("doi")
                    doi = doi_raw.removeprefix("https://doi.org/") if doi_raw else None
                    location = item.get("primary_location") or {}
                    candidates.append(
                        CandidateDocument(
                            title=item.get("title") or "",
                            abstract=_reconstruct_abstract(item.get("abstract_inverted_index")),
                            source="openalex",
                            doi=doi or None,
                            pdf_url=location.get("pdf_url"),
                            published_year=item.get("publication_year"),
                            authors=[
                                a["author"]["display_name"]
                                for a in (item.get("authorships") or [])
                                if a.get("author")
                            ],
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
