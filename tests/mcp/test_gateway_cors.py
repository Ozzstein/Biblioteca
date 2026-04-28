from __future__ import annotations

from fastapi.testclient import TestClient

from llm_rag.config import get_settings
from llm_rag.mcp.gateway import create_app
from tests.mcp.gateway_helpers import FakePool, allow_auth


def test_allowlisted_origin_preflight(
    monkeypatch,
) -> None:
    monkeypatch.setenv("GATEWAY_CORS_ORIGINS", '["https://writer.example.com"]')
    get_settings.cache_clear()
    app = create_app(pool_factory=FakePool)
    allow_auth(app)

    with TestClient(app) as client:
        response = client.options(
            "/mcp/query",
            headers={
                "Origin": "https://writer.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://writer.example.com"
    assert response.headers["access-control-allow-credentials"] == "true"
    get_settings.cache_clear()


def test_disallowed_origin_preflight_returns_403(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_CORS_ORIGINS", '["https://writer.example.com"]')
    get_settings.cache_clear()
    app = create_app(pool_factory=FakePool)
    allow_auth(app)

    with TestClient(app) as client:
        response = client.options(
            "/mcp/query",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert response.status_code == 403
    get_settings.cache_clear()
