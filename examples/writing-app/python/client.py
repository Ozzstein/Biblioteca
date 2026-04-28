from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Callable
from typing import Any

from dotenv import load_dotenv
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

DEMO_QUERY = (
    "draft a summary of LFP cathode degradation including our internal SOPs and reports"
)


def gateway_mcp_url(gateway_url: str) -> str:
    return gateway_url.rstrip("/") + "/mcp"


def cloudflare_headers(client_id: str, client_secret: str) -> dict[str, str]:
    return {
        "CF-Access-Client-Id": client_id,
        "CF-Access-Client-Secret": client_secret,
    }


def _required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


async def query_gateway(
    gateway_url: str,
    client_id: str,
    client_secret: str,
    query: str = DEMO_QUERY,
    *,
    transport_factory: Callable[..., Any] = streamablehttp_client,
    session_factory: Callable[..., Any] = ClientSession,
) -> Any:
    url = gateway_mcp_url(gateway_url)
    headers = cloudflare_headers(client_id, client_secret)
    async with transport_factory(url, headers=headers) as (read_stream, write_stream, _):
        async with session_factory(read_stream, write_stream) as session:
            await session.initialize()
            return await session.call_tool("query", {"query": query})


def _to_jsonable(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return result


async def _amain() -> int:
    load_dotenv()
    try:
        result = await query_gateway(
            _required_env("GATEWAY_URL"),
            _required_env("CF_ACCESS_CLIENT_ID"),
            _required_env("CF_ACCESS_CLIENT_SECRET"),
        )
    except Exception as exc:
        print(f"Gateway query failed: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(_to_jsonable(result), indent=2))
    return 0


def main() -> int:
    return asyncio.run(_amain())


if __name__ == "__main__":
    raise SystemExit(main())
