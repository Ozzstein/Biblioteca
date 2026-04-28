from __future__ import annotations

from fastapi.testclient import TestClient

from llm_rag.mcp.gateway import create_app
from llm_rag.query.agent import Citation, CitationType, QueryContextBundle, QueryResult
from llm_rag.query.planner import QueryIntent, QueryMode, QueryPlan
from tests.mcp.gateway_helpers import FakePool, allow_auth


class FakePlanner:
    def __init__(self) -> None:
        self.last_plan = QueryPlan(
            intent=QueryIntent.REPORTING,
            confidence=0.92,
            mode=QueryMode.HYBRID,
            reason="test",
        )

    async def ask(
        self,
        query: str,
        pool: FakePool,
        *,
        mode: str,
        quality: bool,
    ) -> QueryResult:
        assert query == "write an LFP report"
        assert mode == "auto"
        assert quality is False
        assert pool.configs
        return QueryResult(
            answer="LFP answer",
            context_bundle=QueryContextBundle(
                citations=[
                    Citation(
                        source_doc_id="papers/lfp-001",
                        chunk_id="0",
                        quote="LFP quote",
                        confidence=1.0,
                        citation_type=CitationType.EVIDENCE,
                    )
                ]
            ),
        )


def test_query_returns_provenance_and_sources() -> None:
    planner = FakePlanner()
    app = create_app(pool_factory=FakePool, planner_factory=lambda: planner)  # type: ignore[arg-type]
    allow_auth(app)

    with TestClient(app) as client:
        response = client.post("/mcp/query", json={"query": "write an LFP report"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["answer"] == "LFP answer"
    assert payload["intent"] == "reporting"
    assert payload["confidence"] == 0.92
    assert payload["route"] == "hybrid"
    assert payload["sources_consulted"] == ["literature", "lab"]
    assert payload["sources_unavailable"] == []
    assert payload["citations"][0]["source"] == "literature"
    assert payload["citations"][0]["doc_id"] == "papers/lfp-001"
    assert payload["citations"][0]["chunk_index"] == 0
    assert payload["citations"][0]["verify_against_source"] is True
