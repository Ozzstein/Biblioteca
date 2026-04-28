from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI

from llm_rag.auth.cloudflare import CloudflarePrincipal, require_cloudflare_access
from llm_rag.mcp.pool import SourceUnavailable


class FakeSession:
    def __init__(self, result: Any = None, exc: Exception | None = None) -> None:
        self.result = result if result is not None else {"ok": True}
        self.exc = exc
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call_tool(self, tool_name: str, params: dict[str, Any]) -> Any:
        self.calls.append((tool_name, params))
        if self.exc is not None:
            raise self.exc
        return self.result


class FakePool:
    def __init__(
        self,
        *,
        unavailable: dict[str, str] | None = None,
        sessions: dict[str, FakeSession] | None = None,
    ) -> None:
        self.configs = [
            SimpleNamespace(name="literature", capabilities=["tool:search_chunks"]),
            SimpleNamespace(name="lab", capabilities=["tool:read_page"]),
        ]
        self.unavailable = unavailable or {}
        self.sessions = sessions or {
            "literature": FakeSession(),
            "lab": FakeSession(),
        }

    async def __aenter__(self) -> FakePool:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    def get(self, name: str) -> FakeSession:
        if name in self.unavailable:
            raise SourceUnavailable(name)
        return self.sessions[name]


def allow_auth(app: FastAPI) -> None:
    app.dependency_overrides[require_cloudflare_access] = lambda: CloudflarePrincipal(
        name="test@example.com",
        claims={"sub": "test"},
    )
