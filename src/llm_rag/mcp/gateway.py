from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Request, Response
from fastapi.encoders import jsonable_encoder
from filelock import Timeout as FileLockTimeout
from pydantic import BaseModel, Field

from llm_rag.auth.cloudflare import require_cloudflare_access
from llm_rag.config import get_settings
from llm_rag.mcp.pool import MCPPool, SourceUnavailable
from llm_rag.query.planner import QueryPlanner


class QueryRequest(BaseModel):
    query: str = Field(min_length=1)
    mode: str = "auto"
    quality: bool = False


PoolFactory = Callable[[], Any]
PlannerFactory = Callable[[], QueryPlanner]


def _default_pool_factory() -> MCPPool:
    return MCPPool.from_yaml("config/mcp-sources.yaml", max_restarts=5)


def _default_planner_factory() -> QueryPlanner:
    return QueryPlanner(get_settings())


def _get_pool(request: Request) -> Any:
    pool: Any = request.app.state.pool
    return pool


def _get_planner(request: Request) -> QueryPlanner:
    planner: QueryPlanner = request.app.state.planner
    return planner


def _registered_sources(pool: Any) -> list[str]:
    return [cfg.name for cfg in pool.configs]


def _available_sources(pool: Any) -> list[str]:
    unavailable = set(pool.unavailable)
    return [name for name in _registered_sources(pool) if name not in unavailable]


def _source_registry(pool: Any) -> list[dict[str, Any]]:
    return [
        {
            "name": cfg.name,
            "capabilities": list(cfg.capabilities),
        }
        for cfg in pool.configs
    ]


def _serialize_tool_result(result: Any) -> Any:
    if hasattr(result, "model_dump"):
        return result.model_dump(mode="json")
    return jsonable_encoder(result)


def _query_citations(result: Any) -> list[dict[str, Any]]:
    citations = getattr(result.context_bundle, "citations", [])
    return [
        c.model_dump(mode="json") if hasattr(c, "model_dump") else jsonable_encoder(c)
        for c in citations
    ]


def _degraded_payload(source_name: str, fallback: Any = None) -> dict[str, Any]:
    return {
        "degraded": True,
        "missing_source": source_name,
        "result": fallback,
    }


def _cors_headers(origin: str, request_headers: str | None = None) -> dict[str, str]:
    headers = {
        "Access-Control-Allow-Origin": origin,
        "Access-Control-Allow-Credentials": "true",
        "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
        "Vary": "Origin",
    }
    if request_headers:
        headers["Access-Control-Allow-Headers"] = request_headers
    else:
        headers["Access-Control-Allow-Headers"] = (
            "Content-Type,Cf-Access-Jwt-Assertion,"
            "Cf-Access-Authenticated-User-Email,Cf-Access-Service-Token-Name"
        )
    return headers


def _origin_allowed(origin: str, configured_origins: list[str]) -> bool:
    return "*" in configured_origins or origin in configured_origins


def _install_cors_guard(app: FastAPI) -> None:
    @app.middleware("http")
    async def cors_guard(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        settings = get_settings()
        configured_origins = settings.gateway_cors_origins
        origin = request.headers.get("origin")
        request_method = request.headers.get("access-control-request-method")
        is_preflight = (
            request.method == "OPTIONS"
            and origin is not None
            and request_method is not None
        )

        if origin is not None and not _origin_allowed(origin, configured_origins):
            if is_preflight:
                return Response(status_code=403)
            response: Response = await call_next(request)
            return response

        if is_preflight:
            assert origin is not None
            return Response(
                status_code=200,
                headers=_cors_headers(
                    origin,
                    request.headers.get("access-control-request-headers"),
                ),
            )

        response = await call_next(request)
        if origin is not None:
            response.headers.update(_cors_headers(origin))
        return response


def create_app(
    pool_factory: PoolFactory = _default_pool_factory,
    planner_factory: PlannerFactory = _default_planner_factory,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        pool_context = pool_factory()
        async with pool_context as pool:
            app.state.pool = pool
            app.state.planner = planner_factory()
            yield

    app = FastAPI(
        title="Biblioteca MCP Gateway",
        version="0.1.0",
        dependencies=[Depends(require_cloudflare_access)],
        lifespan=lifespan,
    )
    _install_cors_guard(app)

    @app.get("/mcp/health")
    async def health(pool: Any = Depends(_get_pool)) -> dict[str, Any]:
        return {
            "sources": _registered_sources(pool),
            "unavailable": pool.unavailable,
        }

    @app.get("/mcp/sources")
    async def sources(pool: Any = Depends(_get_pool)) -> dict[str, Any]:
        return {"sources": _source_registry(pool)}

    async def _forward_tool(
        source_name: str,
        tool_name: str,
        params: dict[str, Any] | None,
        pool: Any,
    ) -> dict[str, Any]:
        try:
            result = await pool.get(source_name).call_tool(tool_name, params or {})
        except SourceUnavailable:
            return _degraded_payload(source_name)
        except FileLockTimeout as exc:
            raise HTTPException(status_code=503, detail="Wiki write lock timed out") from exc
        return {"result": _serialize_tool_result(result)}

    @app.post("/mcp/literature/{tool_name}")
    async def literature_tool(
        tool_name: str,
        params: dict[str, Any] | None = Body(default=None),
        pool: Any = Depends(_get_pool),
    ) -> dict[str, Any]:
        return await _forward_tool("literature", tool_name, params, pool)

    @app.post("/mcp/lab/{tool_name}")
    async def lab_tool(
        tool_name: str,
        params: dict[str, Any] | None = Body(default=None),
        pool: Any = Depends(_get_pool),
    ) -> dict[str, Any]:
        return await _forward_tool("lab", tool_name, params, pool)

    @app.post("/mcp/query")
    async def query(
        query_request: QueryRequest,
        pool: Any = Depends(_get_pool),
        planner: QueryPlanner = Depends(_get_planner),
    ) -> dict[str, Any]:
        try:
            result = await planner.ask(
                query_request.query,
                pool,
                mode=query_request.mode,
                quality=query_request.quality,
            )
        except SourceUnavailable as exc:
            missing_source = exc.args[0] if exc.args else "unknown"
            return _degraded_payload(str(missing_source), fallback={"answer": ""})
        except FileLockTimeout as exc:
            raise HTTPException(status_code=503, detail="Wiki write lock timed out") from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        plan = planner.last_plan
        return {
            "answer": result.answer,
            "intent": plan.intent.value if plan is not None else "other",
            "confidence": plan.confidence if plan is not None else 0.0,
            "route": plan.mode.value if plan is not None else query_request.mode,
            "citations": _query_citations(result),
            "sources_consulted": _available_sources(pool),
            "sources_unavailable": list(pool.unavailable),
        }

    return app


app = create_app()
