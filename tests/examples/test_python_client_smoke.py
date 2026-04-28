from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


def _load_client_module() -> Any:
    path = Path("examples/writing-app/python/client.py")
    spec = importlib.util.spec_from_file_location("writing_app_client", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeTransport:
    async def __aenter__(self) -> tuple[str, str, object]:
        return ("read", "write", object())

    async def __aexit__(self, *_: object) -> None:
        return None


class FakeSession:
    calls: list[tuple[str, dict[str, str]]] = []

    def __init__(self, read_stream: str, write_stream: str) -> None:
        self.read_stream = read_stream
        self.write_stream = write_stream

    async def __aenter__(self) -> FakeSession:
        return self

    async def __aexit__(self, *_: object) -> None:
        return None

    async def initialize(self) -> None:
        assert self.read_stream == "read"
        assert self.write_stream == "write"

    async def call_tool(self, tool_name: str, params: dict[str, str]) -> dict[str, object]:
        self.calls.append((tool_name, params))
        return {"ok": True}


@pytest.mark.asyncio
async def test_python_client_constructs_url_headers_and_calls_query_tool() -> None:
    client = _load_client_module()
    transport_calls: list[tuple[str, dict[str, str]]] = []
    FakeSession.calls = []

    def fake_transport(url: str, headers: dict[str, str]) -> FakeTransport:
        transport_calls.append((url, headers))
        return FakeTransport()

    result = await client.query_gateway(
        "https://gateway.example.com/",
        "client-id",
        "client-secret",
        transport_factory=fake_transport,
        session_factory=FakeSession,
    )

    assert result == {"ok": True}
    assert transport_calls == [
        (
            "https://gateway.example.com/mcp",
            {
                "CF-Access-Client-Id": "client-id",
                "CF-Access-Client-Secret": "client-secret",
            },
        )
    ]
    assert FakeSession.calls == [
        (
            "query",
            {
                "query": (
                    "draft a summary of LFP cathode degradation including our internal "
                    "SOPs and reports"
                )
            },
        )
    ]
