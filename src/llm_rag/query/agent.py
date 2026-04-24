from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool

logger = logging.getLogger(__name__)


class CitationType(str, Enum):
    """Distinguishes the provenance layer a citation comes from."""

    EVIDENCE = "evidence"
    WIKI = "wiki"
    GRAPH = "graph"


class Citation(BaseModel):
    """Structured citation linking an answer claim back to a specific source."""

    source_doc_id: str = Field(min_length=1)
    chunk_id: str | None = None
    quote: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)
    citation_type: CitationType = CitationType.EVIDENCE


class EvidenceHit(BaseModel):
    """Reference to a retrieved evidence chunk from the vector store."""

    document_id: str = Field(min_length=1)
    chunk_id: str = Field(min_length=1)
    score: float = Field(ge=0.0, le=1.0)
    snippet: str = ""


class WikiHit(BaseModel):
    """Reference to a matched wiki page section."""

    page_path: str = Field(min_length=1)
    section: str = ""
    snippet: str = ""


class GraphExpansion(BaseModel):
    """Reference to an entity or relation found via graph traversal."""

    entity_id: str = Field(min_length=1)
    relation_type: str | None = None
    connected_ids: list[str] = Field(default_factory=list)


class QueryContextBundle(BaseModel):
    """Separates evidence, wiki, and graph retrieval results before answer synthesis."""

    evidence_hits: list[EvidenceHit] = Field(default_factory=list)
    wiki_hits: list[WikiHit] = Field(default_factory=list)
    graph_expansions: list[GraphExpansion] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    @property
    def total_hits(self) -> int:
        return len(self.evidence_hits) + len(self.wiki_hits) + len(self.graph_expansions)

    @property
    def is_empty(self) -> bool:
        return self.total_hits == 0


@dataclass
class QueryResult:
    answer: str
    sources: list[str] = field(default_factory=list)
    context_bundle: QueryContextBundle = field(default_factory=QueryContextBundle)


def _classify_source(source: str) -> EvidenceHit | WikiHit | None:
    """Classify a raw source string into an evidence or wiki hit."""
    if source.startswith("wiki/"):
        parts = source.split(" §", 1)
        return WikiHit(
            page_path=parts[0],
            section=parts[1] if len(parts) > 1 else "",
        )
    # Treat anything with a chunk reference as an evidence hit
    if "(chunk" in source or source.startswith("papers/") or source.startswith("raw/"):
        doc_id = source.split(" (")[0].strip()
        chunk_id = ""
        if "(chunk" in source:
            chunk_part = source.split("(chunk")[1].rstrip(")")
            chunk_id = chunk_part.strip()
        return EvidenceHit(
            document_id=doc_id,
            chunk_id=chunk_id or "0",
            score=1.0,
        )
    return None


def _build_context_bundle(sources: list[str]) -> QueryContextBundle:
    """Build a QueryContextBundle from parsed source strings."""
    evidence: list[EvidenceHit] = []
    wiki: list[WikiHit] = []
    for src in sources:
        hit = _classify_source(src)
        if isinstance(hit, EvidenceHit):
            evidence.append(hit)
        elif isinstance(hit, WikiHit):
            wiki.append(hit)
    return QueryContextBundle(evidence_hits=evidence, wiki_hits=wiki)


# ---------------------------------------------------------------------------
# Citation marker parsing
# ---------------------------------------------------------------------------

# Matches [EVIDENCE:doc_id:chunk_id], [WIKI:page_path], [GRAPH:entity_id]
_CITATION_RE = re.compile(
    r"\[EVIDENCE:(?P<ev_doc>[^:\]]+):(?P<ev_chunk>[^\]]+)\]"
    r"|\[WIKI:(?P<wiki_path>[^\]]+)\]"
    r"|\[GRAPH:(?P<graph_id>[^\]]+)\]"
)


def _parse_citations(text: str) -> list[Citation]:
    """Extract structured Citation objects from inline citation markers in *text*."""
    citations: list[Citation] = []
    seen: set[str] = set()
    for m in _CITATION_RE.finditer(text):
        if m.group("ev_doc"):
            key = f"evidence:{m.group('ev_doc')}:{m.group('ev_chunk')}"
            if key not in seen:
                seen.add(key)
                citations.append(
                    Citation(
                        source_doc_id=m.group("ev_doc"),
                        chunk_id=m.group("ev_chunk"),
                        quote=_surrounding_context(text, m.start(), m.end()),
                        confidence=1.0,
                        citation_type=CitationType.EVIDENCE,
                    )
                )
        elif m.group("wiki_path"):
            key = f"wiki:{m.group('wiki_path')}"
            if key not in seen:
                seen.add(key)
                citations.append(
                    Citation(
                        source_doc_id=m.group("wiki_path"),
                        quote=_surrounding_context(text, m.start(), m.end()),
                        confidence=1.0,
                        citation_type=CitationType.WIKI,
                    )
                )
        elif m.group("graph_id"):
            key = f"graph:{m.group('graph_id')}"
            if key not in seen:
                seen.add(key)
                citations.append(
                    Citation(
                        source_doc_id=m.group("graph_id"),
                        quote=_surrounding_context(text, m.start(), m.end()),
                        confidence=1.0,
                        citation_type=CitationType.GRAPH,
                    )
                )
    return citations


def _surrounding_context(text: str, start: int, end: int, window: int = 60) -> str:
    """Return the text surrounding a citation marker as a quote snippet."""
    left = max(0, start - window)
    right = min(len(text), end + window)
    snippet = text[left:right].strip()
    # Remove the marker itself from the snippet
    return _CITATION_RE.sub("", snippet).strip() or text[left:right].strip()


def _strip_citation_markers(text: str) -> str:
    """Remove inline citation markers from text for clean display."""
    return _CITATION_RE.sub("", text)


def _parse_result(raw: str) -> QueryResult:
    # Extract inline citation markers before other parsing
    citations = _parse_citations(raw)

    if "## Sources" in raw:
        answer_part, _, sources_part = raw.partition("## Sources")
        sources = [
            line.removeprefix("- ").strip()
            for line in sources_part.strip().splitlines()
            if line.strip().startswith("-")
        ]
        bundle = _build_context_bundle(sources)
        bundle.citations = citations
        return QueryResult(
            answer=answer_part.strip(),
            sources=sources,
            context_bundle=bundle,
        )
    bundle = QueryContextBundle(citations=citations)
    return QueryResult(answer=raw.strip(), sources=[], context_bundle=bundle)


def _query_terms(query: str, min_length: int = 3) -> list[str]:
    """Extract lowercase search terms from a query string, filtering short words."""
    return [t for t in query.lower().split() if len(t) >= min_length]


# ---------------------------------------------------------------------------
# Phased retrieval helpers — call MCP tool functions directly
# ---------------------------------------------------------------------------


async def retrieve_evidence(query: str, n_results: int = 5) -> list[EvidenceHit]:
    """Phase 1: Search corpus chunks for evidence matching *query*."""
    from llm_rag.mcp.corpus_io import search_chunks

    try:
        results: list[dict[str, Any]] = await search_chunks(query, n_results=n_results)
    except Exception:
        logger.warning("Evidence retrieval failed for query: %s", query, exc_info=True)
        return []
    hits: list[EvidenceHit] = []
    for r in results:
        doc_id = r.get("doc_id", "")
        if not doc_id:
            continue
        hits.append(
            EvidenceHit(
                document_id=doc_id,
                chunk_id=str(r.get("chunk_index", 0)),
                score=1.0,
                snippet=(r.get("text", "") or "")[:200],
            )
        )
    return hits


async def retrieve_wiki(query: str) -> list[WikiHit]:
    """Phase 2: Find wiki pages whose paths match query terms."""
    from llm_rag.mcp.wiki_io import list_pages, read_page

    try:
        pages: list[str] = await list_pages()
    except Exception:
        logger.warning("Wiki retrieval failed for query: %s", query, exc_info=True)
        return []
    terms = _query_terms(query)
    if not terms:
        return []
    hits: list[WikiHit] = []
    for page in pages:
        page_lower = page.lower()
        if not any(term in page_lower for term in terms):
            continue
        snippet = ""
        try:
            content = await read_page(page)
            snippet = content[:200]
        except Exception:
            pass
        hits.append(WikiHit(page_path=page, snippet=snippet))
    return hits


async def retrieve_graph(query: str) -> list[GraphExpansion]:
    """Phase 3: Expand entities whose IDs match query terms via graph traversal."""
    from llm_rag.mcp.graph_io import get_neighbors, list_entities

    try:
        entities: list[dict[str, Any]] = await list_entities()
    except Exception:
        logger.warning("Graph retrieval failed for query: %s", query, exc_info=True)
        return []
    terms = _query_terms(query)
    if not terms:
        return []
    expansions: list[GraphExpansion] = []
    for entity in entities:
        eid = entity.get("entity_id", "")
        if not eid:
            continue
        if not any(term in eid.lower() for term in terms):
            continue
        try:
            neighbors = await get_neighbors(eid)
        except Exception:
            neighbors = []
        expansions.append(GraphExpansion(entity_id=eid, connected_ids=neighbors))
    return expansions


def _format_context(bundle: QueryContextBundle) -> str:
    """Render a QueryContextBundle into a text block for the synthesis prompt."""
    parts: list[str] = []
    if bundle.evidence_hits:
        parts.append("## Evidence Chunks")
        for h in bundle.evidence_hits:
            parts.append(f"- [{h.document_id} chunk {h.chunk_id}] {h.snippet}")
    if bundle.wiki_hits:
        parts.append("## Wiki Pages")
        for h in bundle.wiki_hits:
            label = f"{h.page_path} §{h.section}" if h.section else h.page_path
            parts.append(f"- [{label}] {h.snippet}")
    if bundle.graph_expansions:
        parts.append("## Graph Entities")
        for g in bundle.graph_expansions:
            neighbors = ", ".join(g.connected_ids[:10]) if g.connected_ids else "none"
            parts.append(f"- {g.entity_id} → [{neighbors}]")
    if not parts:
        parts.append("No retrieval results found. Answer based on general knowledge.")
    return "\n".join(parts)


_SYNTHESIS_INSTRUCTION = """\
Answer the query using the retrieved context above. Structure your answer with
these sections where applicable:

## Direct Evidence
Claims supported directly by corpus chunks. Cite each with [EVIDENCE:doc_id:chunk_id].

## Wiki Synthesis
Claims drawn from wiki pages. Cite each with [WIKI:page_path].

## Graph Inferences
Claims inferred from entity relationships in the knowledge graph. Cite each with [GRAPH:entity_id].

Rules:
- Every factual claim MUST have at least one citation marker.
- Use the exact document IDs, page paths, and entity IDs from the context above.
- If no evidence, wiki, or graph context is available for a section, omit that section.
- If you must state something not grounded in the provided context, prefix it with "Note:" and do not add a citation marker.
"""


def _build_synthesis_prompt(context: str, query: str) -> str:
    """Construct the full synthesis prompt with citation instructions."""
    return f"{context}\n\n---\n\nQuery: {query}\n\n{_SYNTHESIS_INSTRUCTION}"


class QueryAgent:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._agent = AgentDefinition(
            name="query_agent",
            model=self.settings.model_query_synthesis,
            mcp_servers=[],
            max_tokens=4096,
        )

    async def ask(self, query: str, pool: MCPPool) -> QueryResult:
        # Phase 1–3: Explicit retrieval from each layer
        evidence = await retrieve_evidence(query)
        wiki = await retrieve_wiki(query)
        graph = await retrieve_graph(query)

        bundle = QueryContextBundle(
            evidence_hits=evidence,
            wiki_hits=wiki,
            graph_expansions=graph,
        )

        # Phase 4: Synthesis — pass collected context to the agent
        context = _format_context(bundle)
        synthesis_prompt = _build_synthesis_prompt(context, query)
        raw = await run_agent(self._agent, synthesis_prompt, self.settings, pool)
        result = _parse_result(raw)
        # Merge actual retrieval results with parsed citations
        bundle.citations = result.context_bundle.citations
        result.context_bundle = bundle
        return result
