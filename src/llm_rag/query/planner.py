from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool
from llm_rag.query.agent import QueryAgent, QueryResult


class QueryIntent(StrEnum):
    REPORTING = "reporting"
    KNOW_HOW = "know-how"
    INSIGHT = "insight"
    OTHER = "other"


class QueryMode(StrEnum):
    AUTO = "auto"
    WIKI = "wiki"
    VECTOR = "vector"
    GRAPH = "graph"
    HYBRID = "hybrid"


@dataclass(frozen=True)
class QueryPlan:
    intent: QueryIntent
    confidence: float
    mode: QueryMode
    reason: str


_CONFIDENCE_THRESHOLD = 0.7

_INTENT_PATTERNS: tuple[tuple[QueryIntent, QueryMode, float, tuple[str, ...]], ...] = (
    (
        QueryIntent.REPORTING,
        QueryMode.HYBRID,
        0.9,
        (
            "draft",
            "write",
            "compose",
            "report",
            "summary",
            "summarize",
            "brief",
            "memo",
            "slides",
            "progress update",
            "literature review",
            "citation",
            "cite",
            "section",
            "manuscript",
        ),
    ),
    (
        QueryIntent.KNOW_HOW,
        QueryMode.WIKI,
        0.88,
        (
            "how do",
            "how to",
            "what is our sop",
            "sop",
            "procedure",
            "protocol",
            "recipe",
            "steps",
            "assemble",
            "assembly",
            "equipment",
            "safety",
            "troubleshoot",
            "setup",
        ),
    ),
    (
        QueryIntent.INSIGHT,
        QueryMode.GRAPH,
        0.84,
        (
            "trend",
            "correlation",
            "compare",
            "relationship",
            "relate",
            "connected",
            "which batch",
            "best",
            "worst",
            "metric",
            "metrics",
            "performance",
            "data",
            "outlier",
            "rank",
            "drivers",
        ),
    ),
    (
        QueryIntent.KNOW_HOW,
        QueryMode.VECTOR,
        0.78,
        (
            "evidence",
            "paper",
            "papers",
            "study",
            "studies",
            "support",
            "show",
            "mechanism",
            "mechanistic",
            "cause",
            "causes",
            "why",
        ),
    ),
)


def _normalize_query(query: str) -> str:
    return re.sub(r"\s+", " ", query.lower()).strip()


def classify_intent(query: str) -> QueryPlan:
    """Classify a user query into a user-job intent and retrieval route.

    This is deliberately deterministic for v1: it is fast, testable, and does
    not require live model credentials. The planner still uses the existing
    model assignment boundary: answer synthesis stays on
    ``Settings.model_query_synthesis`` unless ``--quality`` asks for
    ``Settings.model_deep_analysis``.
    """
    normalized = _normalize_query(query)
    if not normalized:
        return QueryPlan(
            intent=QueryIntent.OTHER,
            confidence=0.0,
            mode=QueryMode.HYBRID,
            reason="empty query",
        )

    for intent, mode, confidence, patterns in _INTENT_PATTERNS:
        for pattern in patterns:
            if pattern in normalized:
                return QueryPlan(
                    intent=intent,
                    confidence=confidence,
                    mode=mode,
                    reason=f"matched {pattern!r}",
                )

    return QueryPlan(
        intent=QueryIntent.OTHER,
        confidence=0.55,
        mode=QueryMode.HYBRID,
        reason="no strong intent signal",
    )


def plan_query(query: str, mode: QueryMode | str = QueryMode.AUTO) -> QueryPlan:
    """Resolve explicit mode or auto-classified route into a concrete plan."""
    requested = QueryMode(mode)
    if requested != QueryMode.AUTO:
        return QueryPlan(
            intent=QueryIntent.OTHER,
            confidence=1.0,
            mode=requested,
            reason="explicit mode",
        )

    plan = classify_intent(query)
    if plan.confidence < _CONFIDENCE_THRESHOLD:
        return QueryPlan(
            intent=plan.intent,
            confidence=plan.confidence,
            mode=QueryMode.HYBRID,
            reason=f"{plan.reason}; confidence below {_CONFIDENCE_THRESHOLD}",
        )
    return plan


class QueryPlanner:
    """Intent-aware query router used by the CLI and gateway."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self._agent = QueryAgent(self.settings)
        self.last_plan: QueryPlan | None = None

    async def ask(
        self,
        query: str,
        pool: MCPPool,
        *,
        mode: QueryMode | str = QueryMode.AUTO,
        quality: bool = False,
    ) -> QueryResult:
        plan = plan_query(query, mode)
        self.last_plan = plan
        synthesis_model = (
            self.settings.model_deep_analysis
            if quality
            else self.settings.model_query_synthesis
        )
        return await self._agent.ask_routed(
            query,
            pool,
            mode=plan.mode.value,
            synthesis_model=synthesis_model,
        )
