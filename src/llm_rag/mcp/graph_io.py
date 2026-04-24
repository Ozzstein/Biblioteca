from __future__ import annotations

from pathlib import Path
from typing import Any

import networkx as nx
from mcp.server.fastmcp import FastMCP

from llm_rag.config import get_settings

app = FastMCP("graph-io")


def _load_graph() -> nx.MultiDiGraph:
    settings = get_settings()
    snapshot = settings.graph_dir / "snapshots" / "latest.graphml"
    if not snapshot.exists():
        return nx.MultiDiGraph()
    return nx.read_graphml(str(snapshot), force_multigraph=True)


def _save_graph(g: nx.MultiDiGraph) -> None:
    settings = get_settings()
    snapshot = settings.graph_dir / "snapshots" / "latest.graphml"
    snapshot.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(g, str(snapshot))


@app.tool()
async def get_entity(entity_id: str) -> dict[str, Any] | None:
    """Return node attributes for entity_id, or None if not in the graph."""
    g = _load_graph()
    if not g.has_node(entity_id):
        return None
    attrs: dict[str, Any] = dict(g.nodes[entity_id])
    attrs["entity_id"] = entity_id
    return attrs


@app.tool()
async def list_entities(entity_type: str = "") -> list[dict[str, Any]]:
    """Return all entities, optionally filtered by entity_type string."""
    g = _load_graph()
    result = []
    for node_id, attrs in g.nodes(data=True):
        if entity_type and attrs.get("entity_type") != entity_type:
            continue
        entry: dict[str, Any] = dict(attrs)
        entry["entity_id"] = node_id
        result.append(entry)
    return result


def _run_merge(path: Path) -> None:
    """Load an ExtractionResult JSON from path and merge into the live graph.

    Entity IDs and relation endpoints are resolved through the alias map in
    ``entity-normalization.yaml`` so that aliases collapse to canonical nodes
    and relations always reference canonical IDs.
    """
    from llm_rag.graph.normalization import (
        canonicalize_relation_endpoints,
        load_normalization_map,
        normalize_entity_id,
    )
    from llm_rag.graph.store import GraphStore
    from llm_rag.schemas.entities import ExtractionResult

    settings = get_settings()
    snapshot = settings.graph_dir / "snapshots" / "latest.graphml"
    norm_path = settings.config_dir / "entity-normalization.yaml"
    alias_map = load_normalization_map(norm_path)

    result = ExtractionResult.model_validate_json(path.read_text())
    store = GraphStore(snapshot)
    store.load()

    # Track which canonical IDs we've already added to avoid duplicate nodes
    seen_ids: set[str] = set()
    for entity in result.entities:
        canonical_id = normalize_entity_id(entity.entity_id, alias_map)
        if canonical_id in seen_ids:
            continue
        seen_ids.add(canonical_id)
        entity.entity_id = canonical_id
        store.add_entity(entity)

    for relation in result.relations:
        canon_src, canon_tgt = canonicalize_relation_endpoints(
            relation.source_entity_id,
            relation.target_entity_id,
            alias_map,
        )
        relation.source_entity_id = canon_src
        relation.target_entity_id = canon_tgt
        store.add_relation(relation)

    store.save()


@app.tool()
async def merge_extraction(export_path: str) -> None:
    """Load an ExtractionResult JSON from graph/exports/ and merge into the live graph."""
    settings = get_settings()
    exports_dir = settings.graph_dir / "exports"
    resolved = (exports_dir / Path(export_path).name).resolve()
    if not str(resolved).startswith(str(exports_dir.resolve())):
        raise ValueError(f"export_path escapes exports directory: {export_path}")
    _run_merge(resolved)


@app.tool()
async def merge_by_doc_id(doc_id: str) -> None:
    """Merge the normalized extraction result for doc_id into the knowledge graph."""
    settings = get_settings()
    safe_id = doc_id.replace("/", "-")
    path = settings.graph_dir / "exports" / f"{safe_id}.json"
    if not path.exists():
        return
    _run_merge(path)


@app.tool()
async def materialize_from_claims(claims_json: str) -> int:
    """Build (or rebuild) the graph as a projection from a ClaimCollection JSON.

    Returns the number of nodes in the materialized graph.  The previous
    snapshot is replaced entirely — the graph is always derivable from the
    input claims.
    """
    from llm_rag.graph.materializer import GraphMaterializer
    from llm_rag.graph.normalization import load_normalization_map
    from llm_rag.knowledge.models import ClaimCollection

    settings = get_settings()
    norm_path = settings.config_dir / "entity-normalization.yaml"
    alias_map = load_normalization_map(norm_path) if norm_path.exists() else {}

    collection = ClaimCollection.model_validate_json(claims_json)
    materializer = GraphMaterializer(alias_map=alias_map)
    g = materializer.build_graph_from_collection(collection)
    _save_graph(g)
    return g.number_of_nodes()


@app.tool()
async def get_neighbors(entity_id: str, depth: int = 1) -> list[str]:
    """Return entity IDs reachable from entity_id within depth hops (out-edges only)."""
    g = _load_graph()
    if not g.has_node(entity_id):
        return []
    if depth <= 1:
        return list(g.neighbors(entity_id))
    visited: set[str] = {entity_id}
    frontier: set[str] = set(g.neighbors(entity_id))
    visited.update(frontier)
    for _ in range(depth - 1):
        next_frontier: set[str] = set()
        for node in frontier:
            for nbr in g.neighbors(node):
                if nbr not in visited:
                    visited.add(nbr)
                    next_frontier.add(nbr)
        frontier = next_frontier
    visited.discard(entity_id)
    return list(visited)


@app.tool()
async def get_canonical(alias: str) -> str | None:
    """Look up alias in entity-normalization.yaml. Returns canonical entity_id or None."""
    from llm_rag.graph.normalization import resolve_alias

    settings = get_settings()
    norm_path = settings.config_dir / "entity-normalization.yaml"
    return resolve_alias(alias, norm_path)


def main() -> None:
    app.run()
