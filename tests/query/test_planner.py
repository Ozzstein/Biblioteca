from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from llm_rag.config import Settings
from llm_rag.query.agent import QueryResult
from llm_rag.query.planner import (
    QueryIntent,
    QueryMode,
    QueryPlanner,
    classify_intent,
    plan_query,
)


def _make_settings(tmp_path: Path) -> Settings:
    return Settings(
        ANTHROPIC_API_KEY="test-key",
        root_dir=tmp_path,
        model_query_synthesis="claude-sonnet-4-6",
        model_deep_analysis="claude-opus-4-7",
        model_relevance_scoring="claude-haiku-4-5-20251001",
    )


_LABELED_QUERIES: list[tuple[str, QueryIntent]] = [
    ("Draft a weekly report on LFP degradation with citations", QueryIntent.REPORTING),
    ("Write a memo summarizing our cathode coating work", QueryIntent.REPORTING),
    ("Compose a literature review section on electrolyte additives", QueryIntent.REPORTING),
    ("Prepare slides for the quarterly battery materials update", QueryIntent.REPORTING),
    ("Summarize the meeting decisions for the anode project", QueryIntent.REPORTING),
    ("What is our SOP for coin cell assembly?", QueryIntent.KNOW_HOW),
    ("How do we assemble pouch cells in the dry room?", QueryIntent.KNOW_HOW),
    ("List the safety steps for electrolyte handling", QueryIntent.KNOW_HOW),
    ("Which equipment is required for cathode calendaring?", QueryIntent.KNOW_HOW),
    ("How to troubleshoot low first-cycle efficiency?", QueryIntent.KNOW_HOW),
    ("Which formulation has the best retention trend?", QueryIntent.INSIGHT),
    ("Compare LFP and NMC performance across batches", QueryIntent.INSIGHT),
    ("What metrics correlate with swelling?", QueryIntent.INSIGHT),
    ("Which process variables are connected to high impedance?", QueryIntent.INSIGHT),
    ("Rank the worst outliers in the cycling data", QueryIntent.INSIGHT),
    ("What papers support manganese dissolution as a cause?", QueryIntent.KNOW_HOW),
    ("Why does SEI growth cause capacity fade?", QueryIntent.KNOW_HOW),
    ("What evidence shows thermal storage accelerates degradation?", QueryIntent.KNOW_HOW),
    ("Who owns the Q2 cathode milestone?", QueryIntent.OTHER),
    ("When is the next internal review?", QueryIntent.OTHER),
]


def test_classifier_hits_labeled_benchmark_above_80_percent() -> None:
    correct = 0
    for query, expected in _LABELED_QUERIES:
        if classify_intent(query).intent == expected:
            correct += 1
    assert correct / len(_LABELED_QUERIES) >= 0.8


def test_auto_low_confidence_falls_back_to_hybrid() -> None:
    plan = plan_query("Who owns the Q2 cathode milestone?")
    assert plan.intent == QueryIntent.OTHER
    assert plan.mode == QueryMode.HYBRID
    assert plan.confidence < 0.7


def test_explicit_modes_bypass_classifier() -> None:
    plan = plan_query("Draft a report on LFP", QueryMode.WIKI)
    assert plan.mode == QueryMode.WIKI
    assert plan.confidence == 1.0
    assert plan.reason == "explicit mode"


async def test_planner_routes_auto_plan_to_query_agent(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    with patch(
        "llm_rag.query.planner.QueryAgent.ask_routed",
        new_callable=AsyncMock,
        return_value=QueryResult(answer="answer"),
    ) as mock_ask:
        planner = QueryPlanner(settings=settings)
        result = await planner.ask("What is our SOP for coin cell assembly?", MagicMock())

    assert result.answer == "answer"
    assert planner.last_plan is not None
    assert planner.last_plan.intent == QueryIntent.KNOW_HOW
    mock_ask.assert_awaited_once()
    assert mock_ask.call_args.kwargs["mode"] == "wiki"
    assert mock_ask.call_args.kwargs["synthesis_model"] == "claude-sonnet-4-6"


async def test_quality_uses_deep_analysis_model(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    with patch(
        "llm_rag.query.planner.QueryAgent.ask_routed",
        new_callable=AsyncMock,
        return_value=QueryResult(answer="answer"),
    ) as mock_ask:
        planner = QueryPlanner(settings=settings)
        await planner.ask("Draft a report on LFP", MagicMock(), quality=True)

    assert mock_ask.call_args.kwargs["mode"] == "hybrid"
    assert mock_ask.call_args.kwargs["synthesis_model"] == "claude-opus-4-7"
