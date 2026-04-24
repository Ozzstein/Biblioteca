# SP4: Research Subagents on SDK — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the direct `anthropic.Anthropic` client from `ResearchAgent` by replacing the single relevance-scoring call with `run_agent()` + `AgentDefinition`.

**Architecture:** `ResearchAgent` gains a `self._scorer = AgentDefinition(...)` in its constructor. `run()` opens a lightweight `MCPPool(servers=[])` (no subprocesses — empty list) around the scoring step and passes it down to `_score_all()` and `_score()`. `_score()` becomes async and calls `run_agent()`, parsing the same `{"score": 0.x}` JSON format. The six HTTP client subagents are untouched.

**Tech Stack:** `claude-code-sdk` (`run_agent`, `AgentDefinition`), `llm_rag.mcp.pool.MCPPool`, `unittest.mock` (AsyncMock, patch), pytest asyncio_mode=auto.

---

## File Layout

| File | Action | Purpose |
|------|--------|---------|
| `agents/prompts/relevance_scorer.md` | **Create** | System prompt instructing Claude to return `{"score": 0.x}` JSON |
| `src/llm_rag/research/coordinator.py` | **Modify** | Remove `anthropic` client; add `AgentDefinition`, `run_agent`, `MCPPool`; make `_score` async |
| `tests/research/test_coordinator.py` | **Modify** | Replace `patch("anthropic.Anthropic")` with `patch("...run_agent")` + `patch("...MCPPool")` |

---

## Task 1: Create the relevance scorer prompt

**Files:**
- Create: `agents/prompts/relevance_scorer.md`

- [ ] **Step 1: Create the prompt file**

```markdown
You are a relevance scorer for a battery research knowledge base.

The user will provide a list of research topics, a paper title, and an abstract.
Rate how relevant the paper is to the given topics on a scale from 0.0 to 1.0.

Respond with JSON only, no explanation:
{"score": <float between 0.0 and 1.0>}

Scoring guide:
- 1.0: Directly addresses the topic (core subject matter)
- 0.7–0.9: Highly relevant (closely related methods, materials, or findings)
- 0.4–0.6: Somewhat relevant (tangential connection to the topic)
- 0.1–0.3: Weak relevance (topic mentioned incidentally)
- 0.0: Not relevant
```

Save this to `agents/prompts/relevance_scorer.md`.

- [ ] **Step 2: Verify it exists**

```bash
cat agents/prompts/relevance_scorer.md
```

Expected: the prompt text above.

- [ ] **Step 3: Commit**

```bash
git add agents/prompts/relevance_scorer.md
git commit -m "feat: add relevance_scorer agent prompt"
```

---

## Task 2: Update coordinator.py and its tests

The tests are rewritten first (TDD). They mock `run_agent` and `MCPPool` so no real API calls are made.

**Files:**
- Modify: `src/llm_rag/research/coordinator.py`
- Test: `tests/research/test_coordinator.py`

- [ ] **Step 1: Rewrite the test file**

Replace the entire contents of `tests/research/test_coordinator.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.config import Settings
from llm_rag.research.coordinator import CandidateDocument, ResearchAgent


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


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        root_dir=tmp_path,
        relevance_threshold=0.6,
        model_relevance_scoring="claude-haiku-4-5-20251001",
    )


def _make_candidate(doi: str | None = None, title: str = "LFP Paper") -> CandidateDocument:
    return CandidateDocument(
        title=title,
        abstract="Study of LFP degradation mechanisms.",
        source="arxiv",
        doi=doi,
        pdf_url="https://arxiv.org/pdf/2301.00001",
    )


def _mock_pool() -> tuple[MagicMock, MagicMock]:
    """Return (mock_pool_cls, mock_pool_instance) with async context manager wired up."""
    mock_pool_instance = MagicMock()
    mock_pool_cls = MagicMock()
    mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=mock_pool_instance)
    mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    return mock_pool_cls, mock_pool_instance


async def test_research_agent_deduplicates_by_doi(tmp_path: Path):
    settings = _make_settings(tmp_path)
    c1 = _make_candidate(doi="10.1016/same")
    c2 = _make_candidate(doi="10.1016/same")

    mock_subagent = AsyncMock()
    mock_subagent.search = AsyncMock(return_value=[c1, c2])
    mock_subagent.fetch = AsyncMock(return_value=(b"%PDF-1.4", "pdf"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.9})
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

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.3})
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

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.85})
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

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.9})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP degradation"])

    assert written == []


async def test_research_agent_subagent_search_exception_continues(tmp_path: Path):
    settings = _make_settings(tmp_path)

    failing_subagent = AsyncMock()
    failing_subagent.search = AsyncMock(side_effect=RuntimeError("network error"))

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock), \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
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

    mock_pool_cls, _ = _mock_pool()
    with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
         patch("llm_rag.research.coordinator.MCPPool", mock_pool_cls):
        mock_score.return_value = json.dumps({"score": 0.9})
        agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
        written = await agent.run(topics=["LFP"])

    assert len(written) == 1
```

- [ ] **Step 2: Run updated tests — verify they fail**

```bash
uv run pytest tests/research/test_coordinator.py -v
```

Expected: the 6 async tests FAIL (coordinator.py still uses `anthropic.Anthropic`). The 5 sync `test_candidate_document_*` tests still PASS.

- [ ] **Step 3: Rewrite coordinator.py**

Replace the entire contents of `src/llm_rag/research/coordinator.py` with:

```python
from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings
from llm_rag.mcp.pool import MCPPool

logger = logging.getLogger(__name__)


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


class ResearchAgent:
    def __init__(self, settings: Settings, subagents: list[SourceSubagent]) -> None:
        self.settings = settings
        self.subagents = subagents
        self._scorer = AgentDefinition(
            name="relevance_scorer",
            model=settings.model_relevance_scoring,
            mcp_servers=[],
            max_tokens=64,
        )

    async def run(self, topics: list[str]) -> list[Path]:
        candidates: list[CandidateDocument] = []
        for subagent in self.subagents:
            try:
                found = await subagent.search(topics)
                candidates.extend(found)
            except Exception as exc:
                logger.warning("Subagent %s search failed: %s", type(subagent).__name__, exc)

        candidates = self._deduplicate(candidates)

        async with MCPPool(servers=[]) as pool:
            candidates = await self._score_all(candidates, topics, pool)

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
        self, candidates: list[CandidateDocument], topics: list[str], pool: MCPPool
    ) -> list[CandidateDocument]:
        for candidate in candidates:
            candidate.relevance_score = await self._score(candidate, topics, pool)
        return candidates

    async def _score(
        self, candidate: CandidateDocument, topics: list[str], pool: MCPPool
    ) -> float:
        topics_str = ", ".join(topics)
        user_message = (
            f"Rate the relevance of this paper to battery research topics: {topics_str}\n\n"
            f"Title: {candidate.title}\n"
            f"Abstract: {candidate.abstract[:500]}"
        )
        try:
            text = await run_agent(self._scorer, user_message, self.settings, pool)
            data = json.loads(text.strip())
            return float(data.get("score", 0.0))
        except Exception as exc:
            logger.warning("Relevance scoring failed: %s", exc)
            return 0.0

    def _write_to_inbox(
        self, inbox: Path, candidate: CandidateDocument, content: bytes, ext: str
    ) -> Path:
        safe_key = candidate.content_key.replace(":", "_").replace("/", "_")
        filename = f"{candidate.source}_{safe_key}.{ext}"
        path = inbox / filename
        path.write_bytes(content)
        return path
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
uv run pytest tests/research/test_coordinator.py -v
```

Expected: 11 tests PASS (5 sync + 6 async).

- [ ] **Step 5: Run mypy**

```bash
uv run mypy src/llm_rag/research/coordinator.py
```

Expected: `Success: no issues found in 1 source file`

- [ ] **Step 6: Run full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests pass (same count as before this task + nothing regressed).

- [ ] **Step 7: Commit**

```bash
git add src/llm_rag/research/coordinator.py tests/research/test_coordinator.py
git commit -m "feat: replace direct anthropic client in ResearchAgent with run_agent()"
```
