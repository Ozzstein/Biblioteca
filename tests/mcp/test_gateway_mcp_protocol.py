from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from llm_rag.auth.cloudflare import clear_jwks_cache
from llm_rag.config import get_settings
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


def _jsonrpc(method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": params or {},
    }


def test_streamable_http_lists_query_tool() -> None:
    app = create_app(pool_factory=FakePool)
    allow_auth(app)

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=_jsonrpc("tools/list"),
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 200
    tools = response.json()["result"]["tools"]
    assert [tool["name"] for tool in tools] == ["query"]


def test_streamable_http_query_tool_returns_structured_content() -> None:
    planner = FakePlanner()
    app = create_app(pool_factory=FakePool, planner_factory=lambda: planner)  # type: ignore[arg-type]
    allow_auth(app)

    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=_jsonrpc(
                "tools/call",
                {"name": "query", "arguments": {"query": "write an LFP report"}},
            ),
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 200
    structured = response.json()["result"]["structuredContent"]
    assert structured["answer"] == "LFP answer"
    assert structured["intent"] == "reporting"
    assert structured["citations"][0]["doc_id"] == "papers/lfp-001"


def test_streamable_http_missing_auth_returns_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CF_ACCESS_TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.setenv("CF_ACCESS_AUD_TAG", "expected-aud")
    get_settings.cache_clear()
    clear_jwks_cache()

    app = create_app(pool_factory=FakePool)
    with TestClient(app) as client:
        response = client.post(
            "/mcp",
            json=_jsonrpc("tools/list"),
            headers={"Accept": "application/json, text/event-stream"},
        )

    assert response.status_code == 401
