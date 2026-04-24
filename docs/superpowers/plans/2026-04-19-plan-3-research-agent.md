# Research Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the ResearchAgent coordinator and 7 SourceSubagents (ArXiv, SemanticScholar, OpenAlex, PubMed, Unpaywall, Firecrawl, GoogleScholar stub) that search for battery research papers, score relevance via Claude Haiku, deduplicate by DOI + title hash, and write downloaded content to `raw/inbox/`.

**Architecture:** `ResearchAgent` in `research/coordinator.py` owns the orchestration loop: fan-out to subagents, collect `CandidateDocument` objects, deduplicate, call Claude Haiku for 0.0–1.0 relevance scoring, filter by threshold, fetch content from subagents, write to `raw/inbox/`. Each subagent implements `search(topics) → list[CandidateDocument]` and `fetch(candidate) → tuple[bytes, str] | None`. All HTTP calls go through `httpx.AsyncClient`; all arxiv calls through `arxiv.Client`. No live network in tests.

**Tech Stack:** `arxiv` library, `httpx` (async), `anthropic` SDK, `firecrawl.V1FirecrawlApp`, `pydantic-settings` for config, `pytest` + `unittest.mock` for testing.

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/llm_rag/research/coordinator.py` | `CandidateDocument` dataclass, `SourceSubagent` Protocol, `ResearchAgent` class |
| `src/llm_rag/research/subagents/__init__.py` | Empty package marker |
| `src/llm_rag/research/subagents/arxiv.py` | `ArXivSubagent` — arxiv library + httpx PDF fetch |
| `src/llm_rag/research/subagents/semantic_scholar.py` | `SemanticScholarSubagent` — httpx to S2 graph API |
| `src/llm_rag/research/subagents/openalex.py` | `OpenAlexSubagent` — httpx to OpenAlex API |
| `src/llm_rag/research/subagents/pubmed.py` | `PubMedSubagent` — httpx to PubMed E-utils |
| `src/llm_rag/research/subagents/unpaywall.py` | `UnpaywallSubagent` — httpx DOI → PDF URL lookup |
| `src/llm_rag/research/subagents/firecrawl.py` | `FirecrawlSubagent` — V1FirecrawlApp.scrape_url |
| `src/llm_rag/research/subagents/google_scholar.py` | `GoogleScholarSubagent` — stub returning [] |
| `tests/research/__init__.py` | Empty package marker |
| `tests/research/test_coordinator.py` | Unit tests for CandidateDocument + ResearchAgent |
| `tests/research/test_arxiv.py` | ArXivSubagent tests (arxiv + httpx mocked) |
| `tests/research/test_semantic_scholar.py` | SemanticScholarSubagent tests (httpx mocked) |
| `tests/research/test_openalex.py` | OpenAlexSubagent tests (httpx mocked) |
| `tests/research/test_pubmed.py` | PubMedSubagent tests (httpx mocked) |
| `tests/research/test_unpaywall.py` | UnpaywallSubagent tests (httpx mocked) |
| `tests/research/test_firecrawl.py` | FirecrawlSubagent tests (V1FirecrawlApp mocked) |
| `tests/research/test_google_scholar.py` | GoogleScholarSubagent stub tests |
| `tests/research/test_research_integration.py` | Full ResearchAgent integration (all subagents mocked) |

---

### Task 1: CandidateDocument dataclass + SourceSubagent Protocol

**Files:**
- Modify: `src/llm_rag/research/coordinator.py`
- Create: `tests/research/__init__.py`
- Create: `tests/research/test_coordinator.py` (partial — CandidateDocument tests only)

- [ ] **Step 1: Create `tests/research/__init__.py`**

```python
```
(empty file)

- [ ] **Step 2: Write the failing tests for CandidateDocument**

Create `tests/research/test_coordinator.py`:

```python
from __future__ import annotations

import pytest

from llm_rag.research.coordinator import CandidateDocument


def test_candidate_document_content_key_with_doi():
    c = CandidateDocument(
        title="LFP Degradation",
        abstract="Abstract text.",
        source="arxiv",
        doi="10.1016/j.example.2024.001",
    )
    assert c.content_key == "doi:10.1016/j.example.2024.001"


def test_candidate_document_content_key_doi_lowercased():
    c1 = CandidateDocument(title="T", abstract="A", source="arxiv", doi="10.1016/J.EXAMPLE")
    c2 = CandidateDocument(title="T", abstract="A", source="arxiv", doi="10.1016/j.example")
    assert c1.content_key == c2.content_key


def test_candidate_document_content_key_without_doi_uses_title_hash():
    c = CandidateDocument(title="LFP Degradation", abstract="Abstract.", source="arxiv")
    assert c.content_key.startswith("title:")
    assert len(c.content_key) == len("title:") + 16


def test_candidate_document_content_key_title_hash_case_insensitive():
    c1 = CandidateDocument(title="LFP DEGRADATION", abstract="A", source="arxiv")
    c2 = CandidateDocument(title="lfp degradation", abstract="A", source="arxiv")
    assert c1.content_key == c2.content_key


def test_candidate_document_defaults():
    c = CandidateDocument(title="T", abstract="A", source="arxiv")
    assert c.doi is None
    assert c.arxiv_id is None
    assert c.pdf_url is None
    assert c.source_url is None
    assert c.published_year is None
    assert c.authors == []
    assert c.relevance_score == 0.0
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_coordinator.py -v
```

Expected: `ImportError` or `AttributeError` — `CandidateDocument` not yet defined.

- [ ] **Step 4: Implement CandidateDocument + SourceSubagent in coordinator.py**

```python
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class CandidateDocument:
    title: str
    abstract: str
    source: str  # "arxiv", "semantic_scholar", "openalex", "pubmed", "unpaywall", "firecrawl"
    doi: str | None = None
    arxiv_id: str | None = None
    pdf_url: str | None = None
    source_url: str | None = None
    published_year: int | None = None
    authors: list[str] = field(default_factory=list)
    relevance_score: float = 0.0

    @property
    def content_key(self) -> str:
        """Deduplication key: DOI if present, else 16-char title hash."""
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        return f"title:{hashlib.sha256(self.title.lower().strip().encode()).hexdigest()[:16]}"


@runtime_checkable
class SourceSubagent(Protocol):
    async def search(self, topics: list[str]) -> list[CandidateDocument]: ...
    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None: ...
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_coordinator.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add src/llm_rag/research/coordinator.py tests/research/__init__.py tests/research/test_coordinator.py
git commit -m "feat: add CandidateDocument dataclass and SourceSubagent protocol"
```

---

### Task 2: ResearchAgent coordinator

**Files:**
- Modify: `src/llm_rag/research/coordinator.py` (add ResearchAgent)
- Modify: `tests/research/test_coordinator.py` (add ResearchAgent tests)

- [ ] **Step 1: Write failing tests for ResearchAgent**

Append to `tests/research/test_coordinator.py`:

```python
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.config import Settings
from llm_rag.research.coordinator import CandidateDocument, ResearchAgent


def _make_settings(tmp_path: Path) -> Settings:
    s = Settings(
        anthropic_api_key="test-key",
        root_dir=tmp_path,
        relevance_threshold=0.6,
        model_relevance_scoring="claude-haiku-4-5-20251001",
    )
    return s


def _make_candidate(doi: str | None = None, title: str = "LFP Paper") -> CandidateDocument:
    return CandidateDocument(
        title=title,
        abstract="Study of LFP degradation mechanisms.",
        source="arxiv",
        doi=doi,
        pdf_url="https://arxiv.org/pdf/2301.00001",
    )


def _make_score_response(score: float) -> MagicMock:
    block = MagicMock()
    block.text = json.dumps({"score": score})
    response = MagicMock()
    response.content = [block]
    return response


async def test_research_agent_deduplicates_by_doi(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c1 = _make_candidate(doi="10.1016/same")
    c2 = _make_candidate(doi="10.1016/same")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c1, c2])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_score_response(0.9)

        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert len(written) == 1
    mock_subagent.fetch.assert_called_once()


async def test_research_agent_filters_low_relevance(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c = _make_candidate(doi="10.1016/low")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_score_response(0.3)

        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []
    mock_subagent.fetch.assert_not_called()


async def test_research_agent_writes_pdf_to_inbox(tmp_path: Path):
    settings = _make_settings(tmp_path)
    (tmp_path / "raw" / "inbox").mkdir(parents=True, exist_ok=True)
    c = _make_candidate(doi="10.1016/good")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4 content", "pdf"))

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_score_response(0.85)

        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert len(written) == 1
    assert written[0].suffix == ".pdf"
    assert written[0].read_bytes() == b"%PDF-1.4 content"


async def test_research_agent_skips_fetch_none(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c = _make_candidate(doi="10.1016/nofetch")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c])
    mock_subagent.fetch = AsyncMock(return_value=None)

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_score_response(0.9)

        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []


async def test_research_agent_subagent_search_exception_continues(tmp_path: Path):
    settings = _make_settings(tmp_path)

    failing_subagent = AsyncMock()
    failing_subagent.search = AsyncMock(side_effect=RuntimeError("network error"))

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        agent = ResearchAgent(settings=settings, subagents=[failing_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []


async def test_research_agent_deduplicates_by_title_when_no_doi(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c1 = CandidateDocument(title="LFP Paper", abstract="Abstract.", source="arxiv")
    c2 = CandidateDocument(title="LFP PAPER", abstract="Abstract.", source="semantic_scholar")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c1, c2])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = _make_score_response(0.9)

        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP"])

    assert len(written) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_coordinator.py -v -k "research_agent"
```

Expected: `ImportError` — `ResearchAgent` not yet defined.

- [ ] **Step 3: Implement ResearchAgent in coordinator.py**

Append to `src/llm_rag/research/coordinator.py`:

```python
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

import anthropic

from llm_rag.config import Settings

logger = logging.getLogger(__name__)


@dataclass
class CandidateDocument:
    title: str
    abstract: str
    source: str
    doi: str | None = None
    arxiv_id: str | None = None
    pdf_url: str | None = None
    source_url: str | None = None
    published_year: int | None = None
    authors: list[str] = field(default_factory=list)
    relevance_score: float = 0.0

    @property
    def content_key(self) -> str:
        if self.doi:
            return f"doi:{self.doi.lower().strip()}"
        return f"title:{hashlib.sha256(self.title.lower().strip().encode()).hexdigest()[:16]}"


@runtime_checkable
class SourceSubagent(Protocol):
    async def search(self, topics: list[str]) -> list[CandidateDocument]: ...
    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None: ...


class ResearchAgent:
    def __init__(self, settings: Settings, subagents: list[SourceSubagent]) -> None:
        self.settings = settings
        self.subagents = subagents
        self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    async def run(self, topics: list[str]) -> list[Path]:
        candidates: list[CandidateDocument] = []
        for subagent in self.subagents:
            try:
                found = await subagent.search(topics)
                candidates.extend(found)
            except Exception as exc:
                logger.warning("Subagent %s search failed: %s", type(subagent).__name__, exc)

        candidates = self._deduplicate(candidates)
        candidates = await self._score_all(candidates, topics)

        inbox = self.settings.raw_dir / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)

        written: list[Path] = []
        for candidate in candidates:
            if candidate.relevance_score < self.settings.relevance_threshold:
                logger.debug(
                    "Skipping low-relevance candidate: %s (%.2f)",
                    candidate.title,
                    candidate.relevance_score,
                )
                continue
            for subagent in self.subagents:
                try:
                    result = await subagent.fetch(candidate)
                    if result is not None:
                        content, ext = result
                        path = self._write_to_inbox(inbox, candidate, content, ext)
                        written.append(path)
                        break
                except Exception as exc:
                    logger.warning(
                        "Fetch failed from %s: %s", type(subagent).__name__, exc
                    )
        return written

    def _deduplicate(self, candidates: list[CandidateDocument]) -> list[CandidateDocument]:
        seen: set[str] = set()
        deduped: list[CandidateDocument] = []
        for c in candidates:
            key = c.content_key
            if key not in seen:
                seen.add(key)
                deduped.append(c)
        return deduped

    async def _score_all(
        self, candidates: list[CandidateDocument], topics: list[str]
    ) -> list[CandidateDocument]:
        for candidate in candidates:
            candidate.relevance_score = self._score(candidate, topics)
        return candidates

    def _score(self, candidate: CandidateDocument, topics: list[str]) -> float:
        topics_str = ", ".join(topics)
        prompt = (
            f"Rate the relevance of this paper to battery research topics: {topics_str}\n\n"
            f"Title: {candidate.title}\n"
            f"Abstract: {candidate.abstract[:500]}\n\n"
            'Return JSON only: {"score": <float 0.0-1.0>}'
        )
        try:
            response = self.client.messages.create(
                model=self.settings.model_relevance_scoring,
                max_tokens=64,
                messages=[{"role": "user", "content": prompt}],
            )
            block = response.content[0]
            text: str | None = getattr(block, "text", None)
            if not isinstance(text, str):
                return 0.0
            data = json.loads(text.strip())
            return float(data.get("score", 0.0))
        except Exception as exc:
            logger.warning("Relevance scoring failed: %s", exc)
            return 0.0

    def _write_to_inbox(
        self, inbox: Path, candidate: CandidateDocument, content: bytes, ext: str
    ) -> Path:
        safe_key = candidate.content_key.replace(":", "_").replace("/", "_")[:32]
        filename = f"{candidate.source}_{safe_key}.{ext}"
        path = inbox / filename
        path.write_bytes(content)
        return path
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_coordinator.py -v
```

Expected: 11 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/coordinator.py tests/research/test_coordinator.py
git commit -m "feat: implement ResearchAgent coordinator with dedup and relevance scoring"
```

---

### Task 3: ArXivSubagent

**Files:**
- Create: `src/llm_rag/research/subagents/__init__.py`
- Create: `src/llm_rag/research/subagents/arxiv.py`
- Create: `tests/research/test_arxiv.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_arxiv.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.arxiv import ArXivSubagent


def _make_arxiv_result(
    title: str = "LFP Degradation Study",
    summary: str = "We study LFP capacity fade.",
    doi: str | None = "10.1016/j.electacta.2024.001",
    entry_id: str = "http://arxiv.org/abs/2301.00001v1",
    pdf_url: str | None = "https://arxiv.org/pdf/2301.00001",
    year: int = 2024,
) -> MagicMock:
    result = MagicMock()
    result.title = title
    result.summary = summary
    result.doi = doi
    result.entry_id = entry_id
    result.pdf_url = pdf_url
    result.published = MagicMock(year=year)
    author = MagicMock()
    author.__str__ = lambda self: "A. Researcher"
    result.authors = [author]
    return result


async def test_arxiv_search_returns_candidates():
    mock_result = _make_arxiv_result()

    with patch("llm_rag.research.subagents.arxiv.arxiv.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.results.return_value = iter([mock_result])

        subagent = ArXivSubagent(max_results=20)
        candidates = await subagent.search(["LFP degradation"])

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "LFP Degradation Study"
    assert c.abstract == "We study LFP capacity fade."
    assert c.doi == "10.1016/j.electacta.2024.001"
    assert c.arxiv_id == "2301.00001v1"
    assert c.pdf_url == "https://arxiv.org/pdf/2301.00001"
    assert c.published_year == 2024
    assert c.authors == ["A. Researcher"]
    assert c.source == "arxiv"


async def test_arxiv_search_multiple_topics_aggregated():
    r1 = _make_arxiv_result(title="Paper 1", doi="10.1/a")
    r2 = _make_arxiv_result(title="Paper 2", doi="10.1/b")

    with patch("llm_rag.research.subagents.arxiv.arxiv.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.results.side_effect = [iter([r1]), iter([r2])]

        subagent = ArXivSubagent(max_results=20)
        candidates = await subagent.search(["topic A", "topic B"])

    assert len(candidates) == 2


async def test_arxiv_search_null_doi_handled():
    mock_result = _make_arxiv_result(doi=None)

    with patch("llm_rag.research.subagents.arxiv.arxiv.Client") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client
        mock_client.results.return_value = iter([mock_result])

        subagent = ArXivSubagent(max_results=20)
        candidates = await subagent.search(["LFP"])

    assert candidates[0].doi is None


async def test_arxiv_fetch_returns_pdf_bytes():
    candidate = CandidateDocument(
        title="LFP Paper",
        abstract="Abstract.",
        source="arxiv",
        pdf_url="https://arxiv.org/pdf/2301.00001",
    )
    mock_response = AsyncMock()
    mock_response.content = b"%PDF-1.4 test"
    mock_response.raise_for_status = MagicMock()

    with patch("llm_rag.research.subagents.arxiv.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)

        subagent = ArXivSubagent(max_results=20)
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 test"


async def test_arxiv_fetch_returns_none_when_no_pdf_url():
    candidate = CandidateDocument(
        title="LFP Paper", abstract="Abstract.", source="arxiv", pdf_url=None
    )
    subagent = ArXivSubagent(max_results=20)
    result = await subagent.fetch(candidate)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_arxiv.py -v
```

Expected: `ModuleNotFoundError` — `ArXivSubagent` not yet defined.

- [ ] **Step 3: Create the subagents package and ArXivSubagent**

Create `src/llm_rag/research/subagents/__init__.py` (empty).

Create `src/llm_rag/research/subagents/arxiv.py`:

```python
from __future__ import annotations

import httpx

import arxiv

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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_arxiv.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/__init__.py src/llm_rag/research/subagents/arxiv.py tests/research/test_arxiv.py
git commit -m "feat: add ArXivSubagent with search and PDF fetch"
```

---

### Task 4: SemanticScholarSubagent

**Files:**
- Create: `src/llm_rag/research/subagents/semantic_scholar.py`
- Create: `tests/research/test_semantic_scholar.py`

The Semantic Scholar Graph API endpoint:
`GET https://api.semanticscholar.org/graph/v1/paper/search?query={q}&limit=15&fields=title,abstract,year,authors,externalIds,openAccessPdf`

Response format:
```json
{
  "data": [
    {
      "paperId": "abc123",
      "title": "LFP Degradation",
      "abstract": "We study...",
      "year": 2024,
      "authors": [{"authorId": "1", "name": "A. Researcher"}],
      "externalIds": {"DOI": "10.1016/j.xxx", "ArXiv": "2301.00001"},
      "openAccessPdf": {"url": "https://...pdf", "status": "GREEN"}
    }
  ]
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_semantic_scholar.py`:

```python
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.semantic_scholar import SemanticScholarSubagent

_S2_RESPONSE = {
    "data": [
        {
            "paperId": "abc123",
            "title": "LFP Capacity Fade Analysis",
            "abstract": "This paper investigates LFP capacity fade.",
            "year": 2024,
            "authors": [{"authorId": "1", "name": "Alice Researcher"}],
            "externalIds": {"DOI": "10.1016/j.example.2024.001", "ArXiv": "2301.00001"},
            "openAccessPdf": {"url": "https://example.com/paper.pdf", "status": "GREEN"},
        }
    ]
}


def _mock_s2_get(response_data: dict) -> AsyncMock:
    mock_response = AsyncMock()
    mock_response.status_code = 200
    mock_response.json = MagicMock(return_value=response_data)
    mock_response.raise_for_status = MagicMock()
    return mock_response


async def test_s2_search_returns_candidates():
    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_s2_get(_S2_RESPONSE))

        subagent = SemanticScholarSubagent(max_results=15)
        candidates = await subagent.search(["LFP degradation"])

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "LFP Capacity Fade Analysis"
    assert c.abstract == "This paper investigates LFP capacity fade."
    assert c.doi == "10.1016/j.example.2024.001"
    assert c.arxiv_id == "2301.00001"
    assert c.pdf_url == "https://example.com/paper.pdf"
    assert c.published_year == 2024
    assert c.authors == ["Alice Researcher"]
    assert c.source == "semantic_scholar"


async def test_s2_search_handles_missing_abstract():
    data = {
        "data": [
            {
                "paperId": "xyz",
                "title": "No Abstract Paper",
                "abstract": None,
                "year": 2023,
                "authors": [],
                "externalIds": {},
                "openAccessPdf": None,
            }
        ]
    }

    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_s2_get(data))

        subagent = SemanticScholarSubagent(max_results=15)
        candidates = await subagent.search(["topic"])

    assert candidates[0].abstract == ""
    assert candidates[0].doi is None
    assert candidates[0].pdf_url is None


async def test_s2_search_handles_empty_data():
    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_s2_get({"data": []}))

        subagent = SemanticScholarSubagent(max_results=15)
        candidates = await subagent.search(["topic"])

    assert candidates == []


async def test_s2_fetch_returns_pdf_bytes():
    candidate = CandidateDocument(
        title="LFP Paper",
        abstract="Abstract.",
        source="semantic_scholar",
        pdf_url="https://example.com/paper.pdf",
    )
    mock_response = AsyncMock()
    mock_response.content = b"%PDF-1.4 s2"
    mock_response.raise_for_status = MagicMock()

    with patch("llm_rag.research.subagents.semantic_scholar.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)

        subagent = SemanticScholarSubagent(max_results=15)
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 s2"


async def test_s2_fetch_returns_none_when_no_pdf_url():
    candidate = CandidateDocument(
        title="LFP Paper", abstract="Abstract.", source="semantic_scholar", pdf_url=None
    )
    subagent = SemanticScholarSubagent(max_results=15)
    result = await subagent.fetch(candidate)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_semantic_scholar.py -v
```

Expected: `ModuleNotFoundError` — `SemanticScholarSubagent` not yet defined.

- [ ] **Step 3: Implement SemanticScholarSubagent**

Create `src/llm_rag/research/subagents/semantic_scholar.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_semantic_scholar.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/semantic_scholar.py tests/research/test_semantic_scholar.py
git commit -m "feat: add SemanticScholarSubagent"
```

---

### Task 5: OpenAlexSubagent

**Files:**
- Create: `src/llm_rag/research/subagents/openalex.py`
- Create: `tests/research/test_openalex.py`

OpenAlex API: `GET https://api.openalex.org/works?search={query}&per-page=20&select=id,title,abstract_inverted_index,doi,publication_year,authorships,primary_location`

The `abstract_inverted_index` field is a dict mapping words to their positions in the abstract. Reconstruct by placing words at their sorted positions. The `doi` field is a full URI: `https://doi.org/10.1016/...` — strip the prefix.

Response shape:
```json
{
  "results": [
    {
      "id": "https://openalex.org/W123",
      "title": "LFP Study",
      "abstract_inverted_index": {"We": [0], "study": [1], "LFP": [2]},
      "doi": "https://doi.org/10.1016/j.example.2024",
      "publication_year": 2024,
      "authorships": [{"author": {"display_name": "A. Researcher"}}],
      "primary_location": {"pdf_url": "https://example.com/paper.pdf"}
    }
  ]
}
```

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_openalex.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.openalex import OpenAlexSubagent

_OA_RESPONSE = {
    "results": [
        {
            "id": "https://openalex.org/W123456",
            "title": "LFP Structural Stability",
            "abstract_inverted_index": {
                "We": [0],
                "investigate": [1],
                "LFP": [2],
                "stability.": [3],
            },
            "doi": "https://doi.org/10.1016/j.example.2024.001",
            "publication_year": 2024,
            "authorships": [{"author": {"display_name": "B. Scientist"}}],
            "primary_location": {"pdf_url": "https://example.com/oa-paper.pdf"},
        }
    ]
}


def _mock_oa_get(response_data: dict) -> AsyncMock:
    mock_response = AsyncMock()
    mock_response.json = MagicMock(return_value=response_data)
    mock_response.raise_for_status = MagicMock()
    return mock_response


async def test_openalex_search_returns_candidates():
    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_oa_get(_OA_RESPONSE))

        subagent = OpenAlexSubagent(max_results=20)
        candidates = await subagent.search(["LFP stability"])

    assert len(candidates) == 1
    c = candidates[0]
    assert c.title == "LFP Structural Stability"
    assert c.abstract == "We investigate LFP stability."
    assert c.doi == "10.1016/j.example.2024.001"
    assert c.pdf_url == "https://example.com/oa-paper.pdf"
    assert c.published_year == 2024
    assert c.authors == ["B. Scientist"]
    assert c.source == "openalex"


async def test_openalex_search_handles_null_abstract():
    data = {
        "results": [
            {
                "id": "https://openalex.org/W999",
                "title": "No Abstract",
                "abstract_inverted_index": None,
                "doi": None,
                "publication_year": None,
                "authorships": [],
                "primary_location": None,
            }
        ]
    }

    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_oa_get(data))

        subagent = OpenAlexSubagent(max_results=20)
        candidates = await subagent.search(["topic"])

    assert candidates[0].abstract == ""
    assert candidates[0].doi is None
    assert candidates[0].pdf_url is None


async def test_openalex_doi_prefix_stripped():
    data = {
        "results": [
            {
                "id": "https://openalex.org/W1",
                "title": "Test",
                "abstract_inverted_index": None,
                "doi": "https://doi.org/10.1234/test",
                "publication_year": 2024,
                "authorships": [],
                "primary_location": None,
            }
        ]
    }

    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_oa_get(data))

        subagent = OpenAlexSubagent(max_results=20)
        candidates = await subagent.search(["topic"])

    assert candidates[0].doi == "10.1234/test"


async def test_openalex_fetch_returns_pdf_bytes():
    candidate = CandidateDocument(
        title="OA Paper", abstract="Abstract.", source="openalex",
        pdf_url="https://example.com/oa.pdf",
    )
    mock_response = AsyncMock()
    mock_response.content = b"%PDF-1.4 oa"
    mock_response.raise_for_status = MagicMock()

    with patch("llm_rag.research.subagents.openalex.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=mock_response)

        subagent = OpenAlexSubagent(max_results=20)
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 oa"


async def test_openalex_fetch_returns_none_when_no_pdf_url():
    candidate = CandidateDocument(
        title="OA Paper", abstract="Abstract.", source="openalex", pdf_url=None
    )
    subagent = OpenAlexSubagent(max_results=20)
    result = await subagent.fetch(candidate)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_openalex.py -v
```

Expected: `ModuleNotFoundError` — `OpenAlexSubagent` not yet defined.

- [ ] **Step 3: Implement OpenAlexSubagent**

Create `src/llm_rag/research/subagents/openalex.py`:

```python
from __future__ import annotations

import httpx

from llm_rag.research.coordinator import CandidateDocument

_OA_BASE = "https://api.openalex.org/works"
_OA_FIELDS = "id,title,abstract_inverted_index,doi,publication_year,authorships,primary_location"


def _reconstruct_abstract(inverted_index: dict[str, list[int]] | None) -> str:
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_openalex.py -v
```

Expected: 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/openalex.py tests/research/test_openalex.py
git commit -m "feat: add OpenAlexSubagent"
```

---

### Task 6: PubMedSubagent

**Files:**
- Create: `src/llm_rag/research/subagents/pubmed.py`
- Create: `tests/research/test_pubmed.py`

PubMed E-utils (two-step):
1. `esearch.fcgi?db=pubmed&term={query}&retmax=10&retmode=json` → `{"esearchresult": {"idlist": ["38000000", ...]}}`
2. `esummary.fcgi?db=pubmed&id=38000000,...&retmode=json` → `{"result": {"38000000": {"title": "...", "authors": [...], "pubdate": "2024 Jan", "articleids": [{"idtype": "doi", "value": "10.x/y"}]}}}`

Note: PubMed esummary does not provide abstracts in JSON. Abstract is set to `""`.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_pubmed.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.pubmed import PubMedSubagent

_ESEARCH_RESPONSE = {
    "esearchresult": {"idlist": ["38000001", "38000002"]}
}

_ESUMMARY_RESPONSE = {
    "result": {
        "uids": ["38000001", "38000002"],
        "38000001": {
            "uid": "38000001",
            "title": "LFP Battery Cycle Life Study",
            "authors": [{"name": "C. Researcher"}],
            "pubdate": "2024 Jan",
            "articleids": [{"idtype": "doi", "value": "10.1016/j.example.2024.001"}, {"idtype": "pubmed", "value": "38000001"}],
        },
        "38000002": {
            "uid": "38000002",
            "title": "NMC Cathode Structural Analysis",
            "authors": [],
            "pubdate": "2023 Nov",
            "articleids": [],
        },
    }
}


async def test_pubmed_search_returns_candidates():
    responses = [
        _mock_response(_ESEARCH_RESPONSE),
        _mock_response(_ESUMMARY_RESPONSE),
    ]

    with patch("llm_rag.research.subagents.pubmed.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=responses)

        subagent = PubMedSubagent(max_results=10)
        candidates = await subagent.search(["LFP degradation"])

    assert len(candidates) == 2
    c = candidates[0]
    assert c.title == "LFP Battery Cycle Life Study"
    assert c.doi == "10.1016/j.example.2024.001"
    assert c.published_year == 2024
    assert c.authors == ["C. Researcher"]
    assert c.source == "pubmed"
    assert c.abstract == ""


async def test_pubmed_search_handles_no_doi():
    with patch("llm_rag.research.subagents.pubmed.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        esearch = _mock_response({"esearchresult": {"idlist": ["38000002"]}})
        esummary = _mock_response({
            "result": {
                "uids": ["38000002"],
                "38000002": {
                    "uid": "38000002",
                    "title": "No DOI Paper",
                    "authors": [],
                    "pubdate": "2023",
                    "articleids": [],
                },
            }
        })
        mock_http.get = AsyncMock(side_effect=[esearch, esummary])

        subagent = PubMedSubagent(max_results=10)
        candidates = await subagent.search(["topic"])

    assert candidates[0].doi is None


async def test_pubmed_search_empty_idlist():
    with patch("llm_rag.research.subagents.pubmed.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_response({"esearchresult": {"idlist": []}}))

        subagent = PubMedSubagent(max_results=10)
        candidates = await subagent.search(["topic"])

    assert candidates == []


async def test_pubmed_fetch_returns_none():
    candidate = CandidateDocument(title="T", abstract="A", source="pubmed")
    subagent = PubMedSubagent(max_results=10)
    result = await subagent.fetch(candidate)
    assert result is None


def _mock_response(data: dict) -> AsyncMock:
    r = AsyncMock()
    r.json = MagicMock(return_value=data)
    r.raise_for_status = MagicMock()
    return r
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_pubmed.py -v
```

Expected: `ModuleNotFoundError` — `PubMedSubagent` not yet defined.

- [ ] **Step 3: Implement PubMedSubagent**

Create `src/llm_rag/research/subagents/pubmed.py`:

```python
from __future__ import annotations

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
                    params={"db": "pubmed", "term": topic, "retmax": self.max_results, "retmode": "json"},
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
                result_map: dict[str, dict] = esummary_resp.json().get("result", {})

                for pmid in idlist:
                    item = result_map.get(pmid)
                    if not item:
                        continue
                    candidates.append(
                        CandidateDocument(
                            title=item.get("title") or "",
                            abstract="",
                            source="pubmed",
                            doi=_extract_doi(item.get("articleids") or []),
                            published_year=_parse_year(item.get("pubdate") or ""),
                            authors=[a["name"] for a in (item.get("authors") or []) if a.get("name")],
                        )
                    )
        return candidates

    async def fetch(self, candidate: CandidateDocument) -> tuple[bytes, str] | None:
        return None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_pubmed.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/pubmed.py tests/research/test_pubmed.py
git commit -m "feat: add PubMedSubagent (esearch + esummary, no full-text fetch)"
```

---

### Task 7: UnpaywallSubagent

**Files:**
- Create: `src/llm_rag/research/subagents/unpaywall.py`
- Create: `tests/research/test_unpaywall.py`

Unpaywall API: `GET https://api.unpaywall.org/v2/{doi}?email={email}`

Response (relevant fields):
```json
{
  "doi": "10.1016/j.example",
  "title": "LFP Study",
  "z_authors": [{"given": "A.", "family": "Researcher"}],
  "year": 2024,
  "best_oa_location": {
    "url_for_pdf": "https://example.com/paper.pdf",
    "url": "https://example.com/paper"
  }
}
```

`UnpaywallSubagent.search()` always returns `[]` — it is on-demand only (called via `fetch_by_doi`). The `fetch()` method takes a `CandidateDocument` with a DOI, looks up the best OA PDF URL via Unpaywall, downloads it, and returns `(bytes, "pdf")`.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_unpaywall.py`:

```python
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.unpaywall import UnpaywallSubagent

_UNPAYWALL_RESPONSE = {
    "doi": "10.1016/j.example.2024",
    "title": "LFP Open Access Study",
    "z_authors": [{"given": "D.", "family": "Researcher"}],
    "year": 2024,
    "best_oa_location": {
        "url_for_pdf": "https://example.com/oa-paper.pdf",
        "url": "https://example.com/oa-paper",
    },
}


def _mock_resp(data: dict) -> AsyncMock:
    r = AsyncMock()
    r.json = MagicMock(return_value=data)
    r.raise_for_status = MagicMock()
    return r


def _mock_pdf_resp() -> AsyncMock:
    r = AsyncMock()
    r.content = b"%PDF-1.4 unpaywall"
    r.raise_for_status = MagicMock()
    return r


async def test_unpaywall_search_returns_empty():
    subagent = UnpaywallSubagent(email="test@example.com")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_unpaywall_fetch_resolves_doi_and_downloads_pdf():
    candidate = CandidateDocument(
        title="LFP Study",
        abstract="Abstract.",
        source="unpaywall",
        doi="10.1016/j.example.2024",
    )

    with patch("llm_rag.research.subagents.unpaywall.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(side_effect=[
            _mock_resp(_UNPAYWALL_RESPONSE),
            _mock_pdf_resp(),
        ])

        subagent = UnpaywallSubagent(email="test@example.com")
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "pdf"
    assert content == b"%PDF-1.4 unpaywall"


async def test_unpaywall_fetch_returns_none_when_no_doi():
    candidate = CandidateDocument(
        title="No DOI", abstract="Abstract.", source="unpaywall", doi=None
    )
    subagent = UnpaywallSubagent(email="test@example.com")
    result = await subagent.fetch(candidate)
    assert result is None


async def test_unpaywall_fetch_returns_none_when_no_oa_location():
    candidate = CandidateDocument(
        title="Paywalled", abstract="Abstract.", source="unpaywall", doi="10.1/paywalled"
    )
    no_oa = {"doi": "10.1/paywalled", "title": "Paywalled", "year": 2024, "best_oa_location": None}

    with patch("llm_rag.research.subagents.unpaywall.httpx.AsyncClient") as mock_cls:
        mock_http = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_http.get = AsyncMock(return_value=_mock_resp(no_oa))

        subagent = UnpaywallSubagent(email="test@example.com")
        result = await subagent.fetch(candidate)

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_unpaywall.py -v
```

Expected: `ModuleNotFoundError` — `UnpaywallSubagent` not yet defined.

- [ ] **Step 3: Implement UnpaywallSubagent**

Create `src/llm_rag/research/subagents/unpaywall.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_unpaywall.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/unpaywall.py tests/research/test_unpaywall.py
git commit -m "feat: add UnpaywallSubagent for on-demand DOI → open-access PDF"
```

---

### Task 8: FirecrawlSubagent

**Files:**
- Create: `src/llm_rag/research/subagents/firecrawl.py`
- Create: `tests/research/test_firecrawl.py`

`FirecrawlSubagent` wraps `V1FirecrawlApp`. It is on-demand — `search()` returns `[]`. `fetch()` calls `V1FirecrawlApp.scrape_url(url, formats=["markdown"])` and returns `(markdown_bytes, "md")`.

Note: `V1FirecrawlApp.scrape_url()` is a synchronous call (no await). It returns a `V1ScrapeResponse` object with a `.markdown` attribute.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_firecrawl.py`:

```python
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.firecrawl import FirecrawlSubagent


async def test_firecrawl_search_returns_empty():
    subagent = FirecrawlSubagent(api_key="test-key")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_firecrawl_fetch_returns_markdown():
    candidate = CandidateDocument(
        title="LFP Web Page",
        abstract="Abstract.",
        source="firecrawl",
        source_url="https://example.com/lfp-paper",
    )

    mock_response = MagicMock()
    mock_response.markdown = "# LFP Paper\n\nAbstract content here."

    with patch("llm_rag.research.subagents.firecrawl.V1FirecrawlApp") as mock_cls:
        mock_app = MagicMock()
        mock_cls.return_value = mock_app
        mock_app.scrape_url.return_value = mock_response

        subagent = FirecrawlSubagent(api_key="test-key")
        result = await subagent.fetch(candidate)

    assert result is not None
    content, ext = result
    assert ext == "md"
    assert content == b"# LFP Paper\n\nAbstract content here."
    mock_app.scrape_url.assert_called_once_with(
        "https://example.com/lfp-paper", formats=["markdown"]
    )


async def test_firecrawl_fetch_returns_none_when_no_source_url():
    candidate = CandidateDocument(
        title="No URL", abstract="Abstract.", source="firecrawl", source_url=None
    )
    subagent = FirecrawlSubagent(api_key="test-key")
    result = await subagent.fetch(candidate)
    assert result is None


async def test_firecrawl_fetch_returns_none_when_markdown_empty():
    candidate = CandidateDocument(
        title="Empty Page",
        abstract="Abstract.",
        source="firecrawl",
        source_url="https://example.com/empty",
    )

    mock_response = MagicMock()
    mock_response.markdown = None

    with patch("llm_rag.research.subagents.firecrawl.V1FirecrawlApp") as mock_cls:
        mock_app = MagicMock()
        mock_cls.return_value = mock_app
        mock_app.scrape_url.return_value = mock_response

        subagent = FirecrawlSubagent(api_key="test-key")
        result = await subagent.fetch(candidate)

    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_firecrawl.py -v
```

Expected: `ModuleNotFoundError` — `FirecrawlSubagent` not yet defined.

- [ ] **Step 3: Implement FirecrawlSubagent**

Create `src/llm_rag/research/subagents/firecrawl.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_firecrawl.py -v
```

Expected: 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/firecrawl.py tests/research/test_firecrawl.py
git commit -m "feat: add FirecrawlSubagent for on-demand URL scraping"
```

---

### Task 9: GoogleScholarSubagent stub

**Files:**
- Create: `src/llm_rag/research/subagents/google_scholar.py`
- Create: `tests/research/test_google_scholar.py`

`GoogleScholarSubagent` returns `[]` from both `search()` and `fetch()`. It logs a warning if `serpapi_key` is empty. This is a stub for a future SerpAPI integration.

- [ ] **Step 1: Write the failing tests**

Create `tests/research/test_google_scholar.py`:

```python
from __future__ import annotations

import pytest

from llm_rag.research.coordinator import CandidateDocument
from llm_rag.research.subagents.google_scholar import GoogleScholarSubagent


async def test_google_scholar_search_returns_empty():
    subagent = GoogleScholarSubagent(serpapi_key="")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_google_scholar_search_returns_empty_with_key():
    subagent = GoogleScholarSubagent(serpapi_key="fake-key")
    results = await subagent.search(["LFP"])
    assert results == []


async def test_google_scholar_fetch_returns_none():
    candidate = CandidateDocument(
        title="LFP Paper", abstract="Abstract.", source="google_scholar"
    )
    subagent = GoogleScholarSubagent(serpapi_key="")
    result = await subagent.fetch(candidate)
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/research/test_google_scholar.py -v
```

Expected: `ModuleNotFoundError` — `GoogleScholarSubagent` not yet defined.

- [ ] **Step 3: Implement GoogleScholarSubagent stub**

Create `src/llm_rag/research/subagents/google_scholar.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/research/test_google_scholar.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/research/subagents/google_scholar.py tests/research/test_google_scholar.py
git commit -m "feat: add GoogleScholarSubagent stub (SerpAPI integration deferred)"
```

---

### Task 10: Integration test — ResearchAgent with all subagents wired

**Files:**
- Create: `tests/research/test_research_integration.py`

This test builds a full `ResearchAgent` with all 7 subagents. Each subagent is mocked (no live HTTP). It verifies:
1. Candidates from multiple subagents are combined and deduplicated.
2. Only candidates above the relevance threshold get written to inbox.
3. The written files have the correct extension.
4. The final test count across all modules is reported.

- [ ] **Step 1: Write the failing test**

Create `tests/research/test_research_integration.py`:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llm_rag.config import Settings
from llm_rag.research.coordinator import CandidateDocument, ResearchAgent
from llm_rag.research.subagents.arxiv import ArXivSubagent
from llm_rag.research.subagents.firecrawl import FirecrawlSubagent
from llm_rag.research.subagents.google_scholar import GoogleScholarSubagent
from llm_rag.research.subagents.openalex import OpenAlexSubagent
from llm_rag.research.subagents.pubmed import PubMedSubagent
from llm_rag.research.subagents.semantic_scholar import SemanticScholarSubagent
from llm_rag.research.subagents.unpaywall import UnpaywallSubagent


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        firecrawl_api_key="fc-test",
        serpapi_key="",
        root_dir=tmp_path,
        relevance_threshold=0.6,
        model_relevance_scoring="claude-haiku-4-5-20251001",
    )


def _score_response(score: float) -> MagicMock:
    block = MagicMock()
    block.text = json.dumps({"score": score})
    resp = MagicMock()
    resp.content = [block]
    return resp


async def test_research_agent_end_to_end_with_all_subagents(tmp_path: Path):
    """
    ArXiv returns one candidate (high relevance, PDF fetch succeeds).
    SemanticScholar returns same paper by DOI (deduplicated).
    OpenAlex returns one new candidate (low relevance, filtered out).
    PubMed, Unpaywall, Firecrawl, GoogleScholar return empty.
    """
    lfp_candidate = CandidateDocument(
        title="LFP Capacity Fade at High Temperatures",
        abstract="We study LFP fade mechanisms at elevated temperatures.",
        source="arxiv",
        doi="10.1016/j.xxx.2024.001",
        pdf_url="https://arxiv.org/pdf/2401.00001",
    )
    lfp_duplicate = CandidateDocument(
        title="LFP Capacity Fade at High Temperatures",
        abstract="We study LFP fade mechanisms at elevated temperatures.",
        source="semantic_scholar",
        doi="10.1016/j.xxx.2024.001",
        pdf_url="https://example.com/paper.pdf",
    )
    low_relevance = CandidateDocument(
        title="Polymer Chemistry Applications",
        abstract="Study of polymer applications in industrial settings.",
        source="openalex",
        doi="10.1016/j.polymer.2024",
        pdf_url="https://example.com/polymer.pdf",
    )

    mock_arxiv = AsyncMock(spec=ArXivSubagent)
    mock_arxiv.search = AsyncMock(return_value=[lfp_candidate])
    mock_arxiv.fetch = AsyncMock(return_value=(b"%PDF-1.4 lfp", "pdf"))

    mock_s2 = AsyncMock(spec=SemanticScholarSubagent)
    mock_s2.search = AsyncMock(return_value=[lfp_duplicate])
    mock_s2.fetch = AsyncMock(return_value=(b"%PDF-1.4 lfp-s2", "pdf"))

    mock_oa = AsyncMock(spec=OpenAlexSubagent)
    mock_oa.search = AsyncMock(return_value=[low_relevance])
    mock_oa.fetch = AsyncMock(return_value=(b"%PDF-1.4 polymer", "pdf"))

    mock_pubmed = AsyncMock(spec=PubMedSubagent)
    mock_pubmed.search = AsyncMock(return_value=[])
    mock_pubmed.fetch = AsyncMock(return_value=None)

    mock_unpaywall = AsyncMock(spec=UnpaywallSubagent)
    mock_unpaywall.search = AsyncMock(return_value=[])
    mock_unpaywall.fetch = AsyncMock(return_value=None)

    mock_firecrawl = AsyncMock(spec=FirecrawlSubagent)
    mock_firecrawl.search = AsyncMock(return_value=[])
    mock_firecrawl.fetch = AsyncMock(return_value=None)

    mock_gs = AsyncMock(spec=GoogleScholarSubagent)
    mock_gs.search = AsyncMock(return_value=[])
    mock_gs.fetch = AsyncMock(return_value=None)

    subagents = [mock_arxiv, mock_s2, mock_oa, mock_pubmed, mock_unpaywall, mock_firecrawl, mock_gs]
    scores = iter([0.9, 0.2])

    with patch("anthropic.Anthropic") as mock_anthropic_cls:
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.side_effect = lambda **kwargs: _score_response(next(scores))

        settings = _settings(tmp_path)
        agent = ResearchAgent(settings=settings, subagents=subagents)
        written = await agent.run(topics=["LFP degradation", "battery capacity fade"])

    # Only one file: duplicate deduplicated, low-relevance filtered
    assert len(written) == 1
    assert written[0].suffix == ".pdf"
    assert written[0].read_bytes() == b"%PDF-1.4 lfp"

    # Dedup: fetch called only once (on arxiv, first in list)
    mock_arxiv.fetch.assert_called_once()
    mock_s2.fetch.assert_not_called()
    mock_oa.fetch.assert_not_called()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
uv run pytest tests/research/test_research_integration.py -v
```

Expected: `AssertionError` or import error as integration is not yet wired.

- [ ] **Step 3: Run all research tests and verify full suite passes**

The integration test should already pass once all Task 1–9 implementations are in place. Run:

```bash
uv run pytest tests/research/ -v
```

Expected: all tests PASS (roughly 31 tests across coordinator, arxiv, semantic_scholar, openalex, pubmed, unpaywall, firecrawl, google_scholar, and integration).

- [ ] **Step 4: Run full test suite to verify no regressions**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASS (95 Plan 2 tests + ~31 Plan 3 tests = ~126 total).

- [ ] **Step 5: Type check and lint**

```bash
uv run mypy src/
uv run ruff check src/ tests/
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add tests/research/test_research_integration.py
git commit -m "test: add ResearchAgent end-to-end integration test with all subagents"
```

---

## Self-Review

### Spec Coverage

Checking against `docs/superpowers/specs/2026-04-18-battery-research-os-design.md` and CLAUDE.md Plan 3 requirements:

- ✅ `ResearchAgent` coordinator in `research/coordinator.py`
- ✅ `CandidateDocument` dataclass with all required fields
- ✅ `SourceSubagent` Protocol for type-safe subagent dispatch
- ✅ Deduplication by DOI + title content hash
- ✅ Claude Haiku relevance scoring (0.0–1.0 via `model_relevance_scoring`)
- ✅ `relevance_threshold` filter before downloading
- ✅ Write downloaded content to `raw/inbox/`
- ✅ ArXivSubagent (`arxiv` library + httpx PDF fetch)
- ✅ SemanticScholarSubagent (httpx to S2 Graph API)
- ✅ OpenAlexSubagent (httpx with abstract reconstruction)
- ✅ PubMedSubagent (httpx E-utils two-step)
- ✅ UnpaywallSubagent (on-demand DOI → PDF)
- ✅ FirecrawlSubagent (V1FirecrawlApp.scrape_url → markdown)
- ✅ GoogleScholarSubagent stub (returns `[]`, logs if no SERPAPI_KEY)
- ✅ All HTTP calls mocked in tests
- ✅ `search()` + `fetch()` interface on each subagent

### Placeholder Scan

None found.

### Type Consistency

- `fetch()` returns `tuple[bytes, str] | None` consistently across all subagents and is handled by `ResearchAgent._write_to_inbox` which receives `content, ext = result`.
- `CandidateDocument.content_key` used in `_deduplicate` matches the `@property` definition.
- `Settings.relevance_threshold` (float) compared against `candidate.relevance_score` (float) — consistent.
- `Settings.raw_dir` used in `_write_to_inbox` inbox construction — consistent with Plan 2 usage.
