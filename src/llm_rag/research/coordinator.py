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

    async def run(
        self,
        topics: list[str],
        subagent_names: list[str] | None = None,
    ) -> list[Path]:
        """Run research across subagents.

        Args:
            topics: Research topics to search for.
            subagent_names: If provided, only run subagents whose class name
                matches (case-insensitive, with 'Subagent' suffix stripped).
                E.g. ["arxiv", "pubmed"] runs ArXivSubagent and PubMedSubagent.
                If None, all subagents are run.
        """
        active = self._filter_subagents(subagent_names)
        candidates: list[CandidateDocument] = []
        for subagent in active:
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

    @staticmethod
    def subagent_key(subagent: SourceSubagent) -> str:
        """Derive a config key from a subagent class name.

        ArXivSubagent → 'arxiv', SemanticScholarSubagent → 'semantic_scholar'.
        """
        name = type(subagent).__name__
        # Strip 'Subagent' suffix
        if name.endswith("Subagent"):
            name = name[: -len("Subagent")]
        # CamelCase → snake_case
        result: list[str] = []
        for i, ch in enumerate(name):
            if ch.isupper() and i > 0:
                result.append("_")
            result.append(ch.lower())
        return "".join(result)

    def _filter_subagents(
        self, subagent_names: list[str] | None
    ) -> list[SourceSubagent]:
        if subagent_names is None:
            return self.subagents
        names_lower = {n.lower() for n in subagent_names}
        return [
            s for s in self.subagents if self.subagent_key(s) in names_lower
        ]

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
        except FileNotFoundError:
            raise
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
