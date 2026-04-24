# SP4: Research Subagents on SDK — Design Spec

**Date:** 2026-04-20
**Status:** Approved

---

## Goal

Remove the direct `anthropic.Anthropic` client from `ResearchAgent` by replacing the single relevance-scoring call with `run_agent()`. The six HTTP client subagents (ArXiv, SemanticScholar, OpenAlex, PubMed, Unpaywall, Firecrawl) remain as plain Python — they make no LLM calls and need no migration.

---

## What Changes

- `ResearchAgent.__init__` loses `self.client = anthropic.Anthropic(...)` and gains `self._scorer = AgentDefinition(...)`
- `ResearchAgent.run()` opens `async with MCPPool(servers=[]) as pool:` around `_score_all`
- `_score_all(candidates, topics)` gains a `pool: MCPPool` parameter
- `_score(candidate, topics)` becomes `async def _score(..., pool: MCPPool)` and calls `run_agent()`
- `import anthropic` is removed from `coordinator.py`
- New file `agents/prompts/relevance_scorer.md` is added
- `tests/research/test_coordinator.py` — mock updated (no new tests)

## What Stays

- All six source subagents (`arxiv.py`, `semantic_scholar.py`, `openalex.py`, `pubmed.py`, `unpaywall.py`, `firecrawl.py`) — untouched
- `CandidateDocument`, `SourceSubagent` protocol, `_deduplicate`, `_write_to_inbox` — untouched
- `pyproject.toml` — `anthropic` remains (transitive dep; only the direct client usage is removed)

---

## Section 1: `coordinator.py` Changes

### Constructor

Remove:
```python
import anthropic
...
self.client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
```

Add:
```python
from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.mcp.pool import MCPPool
...
self._scorer = AgentDefinition(
    name="relevance_scorer",
    model=settings.model_relevance_scoring,
    mcp_servers=[],
    max_tokens=64,
)
```

### `run()` method

Wrap the scoring call in a lightweight pool (no subprocesses — `servers=[]`):

```python
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
                logger.warning("Fetch failed from %s: %s", type(subagent).__name__, exc)
    return written
```

### `_score_all()` and `_score()`

```python
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
```

---

## Section 2: `agents/prompts/relevance_scorer.md`

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

---

## Section 3: Testing Changes

### `tests/research/test_coordinator.py`

**Deleted:** `_make_score_response()` helper (was building a mock Anthropic response object).

**Unchanged:** all 5 synchronous `test_candidate_document_*` tests.

**Updated:** all 6 async `test_research_agent_*` tests. Replace `patch("anthropic.Anthropic")` with:

```python
with patch("llm_rag.research.coordinator.run_agent", new_callable=AsyncMock) as mock_score, \
     patch("llm_rag.research.coordinator.MCPPool") as mock_pool_cls:
    mock_pool_cls.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
    mock_pool_cls.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_score.return_value = json.dumps({"score": 0.9})

    agent = ResearchAgent(settings=settings, subagents=[mock_subagent])
    written = await agent.run(topics=["LFP degradation"])
```

For `test_research_agent_filters_low_relevance`: `mock_score.return_value = json.dumps({"score": 0.3})`.

No new tests are needed — the existing 6 tests cover deduplication, relevance filtering, file writing, fetch-none, search exceptions, and title-based dedup.

---

## File Layout Summary

**Created:**
```
agents/prompts/relevance_scorer.md
```

**Modified:**
```
src/llm_rag/research/coordinator.py   — remove anthropic client, add AgentDefinition + run_agent
tests/research/test_coordinator.py    — update mock pattern for all async tests
```
