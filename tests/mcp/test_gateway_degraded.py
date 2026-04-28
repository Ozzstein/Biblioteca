from __future__ import annotations

from fastapi.testclient import TestClient

from llm_rag.mcp.gateway import create_app
from tests.mcp.gateway_helpers import FakePool, allow_auth


def test_unavailable_source_returns_degraded_payload() -> None:
    pool = FakePool(unavailable={"lab": "crashed"})
    app = create_app(pool_factory=lambda: pool)
    allow_auth(app)

    with TestClient(app) as client:
        response = client.post("/mcp/lab/read_page", json={"relative_path": "sop/index.md"})

    assert response.status_code == 200
    assert response.json() == {
        "degraded": True,
        "missing_source": "lab",
        "result": None,
    }
