"""
Biblioteca Web API — FastAPI backend for the Battery Research OS dashboard.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from llm_rag.auth.cloudflare import require_cloudflare_access
from llm_rag.config import PROJECT_ROOT, get_settings
from llm_rag.mcp.pool import MCPPool
from llm_rag.query.planner import QueryPlanner

# ============================================================================
# Configuration
# ============================================================================

# Get Biblioteca home (default: ~/.biblioteca or ~/Biblioteca)
BIBLIOTECA_HOME = Path(os.environ.get("BIBLIOTECA_HOME", Path.home() / "Biblioteca"))

# ============================================================================
# FastAPI App
# ============================================================================

app = FastAPI(
    title="Biblioteca API",
    description="Battery Research OS Dashboard API",
    version="0.1.0",
    dependencies=[Depends(require_cloudflare_access)],
)

def _dashboard_cors_origins() -> list[str]:
    return get_settings().gateway_cors_origins or [
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
    ]


# CORS for dev server and Cloudflare-hosted dashboard origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_dashboard_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# Models
# ============================================================================

class SystemStatus(BaseModel):
    status: str
    supervisor_running: bool
    supervisor_pid: int | None = None
    health: str = "healthy"
    last_heartbeat: str | None = None
    files_processed: int = 0
    error_rate: float = 0.0
    pending_files: int = 0

class CorpusStats(BaseModel):
    total_documents: int
    total_chunks: int
    total_tokens: int
    pending_files: int
    recent_documents: list[dict]

class WikiStats(BaseModel):
    total_pages: int
    pages_by_category: dict[str, int]
    recent_pages: list[dict]

class GraphStats(BaseModel):
    total_nodes: int
    total_edges: int
    nodes_by_type: dict[str, int]
    edges_by_type: dict[str, int]

class QueryRequest(BaseModel):
    query: str
    mode: str = "hybrid"
    quality: bool = False
    verbose: bool = False

class QueryResponse(BaseModel):
    answer: str
    citations: list[dict] = []
    context: dict = {}
    latency_ms: float = 0.0

# ============================================================================
# Health & Status
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/api/status", response_model=SystemStatus)
async def get_status():
    """Get system status including supervisor health."""
    state_file = BIBLIOTECA_HOME / ".supervisor" / "state.json"
    pid_file = BIBLIOTECA_HOME / ".supervisor" / "supervisor.pid"
    
    supervisor_running = False
    supervisor_pid = None
    last_heartbeat = None
    files_processed = 0
    error_rate = 0.0
    
    # Check if supervisor is running
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            os.kill(pid, 0)
            supervisor_running = True
            supervisor_pid = pid
        except (OSError, ValueError):
            pass
    
    # Read state file
    if state_file.exists():
        try:
            state = json.loads(state_file.read_text())
            last_heartbeat = state.get("last_heartbeat")
            files_processed = state.get("files_processed", 0)
            error_rate = state.get("error_rate", 0.0)
        except (json.JSONDecodeError, OSError):
            pass
    
    # Count pending files
    inbox_dir = BIBLIOTECA_HOME / "raw" / "inbox"
    pending_files = 0
    if inbox_dir.exists():
        pending_files = len(list(inbox_dir.glob("*")))
    
    health = "healthy" if supervisor_running or pending_files == 0 else "degraded"
    
    return SystemStatus(
        status="running" if supervisor_running else "stopped",
        supervisor_running=supervisor_running,
        supervisor_pid=supervisor_pid,
        health=health,
        last_heartbeat=last_heartbeat,
        files_processed=files_processed,
        error_rate=error_rate,
        pending_files=pending_files,
    )

# ============================================================================
# Corpus Endpoints
# ============================================================================

@app.get("/api/corpus/stats", response_model=CorpusStats)
async def get_corpus_stats():
    """Get corpus statistics."""
    manifests_dir = BIBLIOTECA_HOME / "retrieval" / "manifests"
    
    total_documents = 0
    total_chunks = 0
    total_tokens = 0
    recent_docs = []
    
    if manifests_dir.exists():
        for manifest_file in manifests_dir.glob("*.json"):
            total_documents += 1
            try:
                manifest = json.loads(manifest_file.read_text())
                chunks = manifest.get("chunks", 0)
                total_chunks += chunks
                total_tokens += manifest.get("total_tokens", 0)
                
                recent_docs.append({
                    "doc_id": manifest_file.stem,
                    "path": manifest.get("path", ""),
                    "status": manifest.get("status", "unknown"),
                    "chunks": chunks,
                    "processed_at": manifest.get("processed_at"),
                })
            except (json.JSONDecodeError, OSError):
                pass
    
    recent_docs.sort(key=lambda x: x.get("processed_at") or "", reverse=True)
    recent_docs = recent_docs[:10]
    
    inbox_dir = BIBLIOTECA_HOME / "raw" / "inbox"
    pending_files = len(list(inbox_dir.glob("*"))) if inbox_dir.exists() else 0
    
    return CorpusStats(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_tokens=total_tokens,
        pending_files=pending_files,
        recent_documents=recent_docs,
    )

@app.get("/api/corpus/documents")
async def list_documents(
    limit: int = Query(50, ge=1, le=200),
    status: str | None = None,
):
    """List all documents in the corpus."""
    manifests_dir = BIBLIOTECA_HOME / "retrieval" / "manifests"
    documents = []
    
    if manifests_dir.exists():
        for manifest_file in manifests_dir.glob("*.json"):
            try:
                manifest = json.loads(manifest_file.read_text())
                if status and manifest.get("status") != status:
                    continue
                    
                documents.append({
                    "doc_id": manifest_file.stem,
                    "path": manifest.get("path", ""),
                    "status": manifest.get("status", "unknown"),
                    "stages_completed": manifest.get("stages_completed", []),
                    "num_chunks": manifest.get("chunks", 0),
                    "processed_at": manifest.get("processed_at"),
                })
            except (json.JSONDecodeError, OSError):
                pass
    
    documents.sort(key=lambda x: x.get("processed_at") or "", reverse=True)
    return documents[:limit]

@app.get("/api/corpus/documents/{doc_id}")
async def get_document(doc_id: str):
    """Get details for a specific document."""
    manifest_file = BIBLIOTECA_HOME / "retrieval" / "manifests" / f"{doc_id}.json"
    
    if not manifest_file.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    try:
        manifest = json.loads(manifest_file.read_text())
        return manifest
    except (json.JSONDecodeError, OSError) as e:
        raise HTTPException(status_code=500, detail=f"Error reading manifest: {e}")

# ============================================================================
# Wiki Endpoints
# ============================================================================

@app.get("/api/wiki/stats", response_model=WikiStats)
async def get_wiki_stats():
    """Get wiki statistics."""
    wiki_dir = BIBLIOTECA_HOME / "wiki"
    
    pages_by_category = {}
    total_pages = 0
    recent_pages = []
    
    if wiki_dir.exists():
        for category_dir in wiki_dir.iterdir():
            if category_dir.is_dir() and not category_dir.name.startswith("."):
                count = len(list(category_dir.glob("*.md")))
                if count > 0:
                    pages_by_category[category_dir.name] = count
                    total_pages += count
                    
                    for page_file in sorted(category_dir.glob("*.md"), reverse=True)[:3]:
                        recent_pages.append({
                            "title": page_file.stem,
                            "category": category_dir.name,
                            "path": f"{category_dir.name}/{page_file.stem}",
                        })
    
    root_pages = len([f for f in wiki_dir.glob("*.md") if f.is_file()])
    if root_pages > 0:
        pages_by_category["root"] = root_pages
        total_pages += root_pages
    
    return WikiStats(
        total_pages=total_pages,
        pages_by_category=pages_by_category,
        recent_pages=recent_pages[:10],
    )

@app.get("/api/wiki/pages")
async def list_wiki_pages(
    category: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """List wiki pages, optionally filtered by category."""
    wiki_dir = BIBLIOTECA_HOME / "wiki"
    pages = []
    
    if category:
        category_dir = wiki_dir / category
        if category_dir.exists():
            for page_file in category_dir.glob("*.md"):
                pages.append({
                    "title": page_file.stem,
                    "category": category,
                    "path": f"{category}/{page_file.stem}",
                })
    else:
        for item in wiki_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                for page_file in item.glob("*.md"):
                    pages.append({
                        "title": page_file.stem,
                        "category": item.name,
                        "path": f"{item.name}/{page_file.stem}",
                    })
            elif item.is_file() and item.suffix == ".md":
                pages.append({
                    "title": item.stem,
                    "category": "root",
                    "path": item.name,
                })
    
    return pages[:limit]

@app.get("/api/wiki/pages/{path:path}")
async def get_wiki_page(path: str):
    """Get a specific wiki page content."""
    wiki_dir = BIBLIOTECA_HOME / "wiki"
    page_file = wiki_dir / f"{path}.md"
    
    if not page_file.exists():
        raise HTTPException(status_code=404, detail="Page not found")
    
    content = page_file.read_text()
    
    import re
    frontmatter = {}
    body = content
    
    if content.startswith("---"):
        match = re.search(r"^---\n(.*?)\n---\n", content, re.DOTALL)
        if match:
            try:
                import yaml
                frontmatter = yaml.safe_load(match.group(1)) or {}
                body = content[match.end():]
            except Exception:
                pass
    
    return {
        "path": path,
        "title": frontmatter.get("title", path.split("/")[-1]),
        "content": body,
        "frontmatter": frontmatter,
    }

# ============================================================================
# Graph Endpoints
# ============================================================================

@app.get("/api/graph/stats", response_model=GraphStats)
async def get_graph_stats():
    """Get knowledge graph statistics."""
    graph_file = BIBLIOTECA_HOME / "graph" / "exports" / "latest.graphml"
    
    if not graph_file.exists():
        return GraphStats(
            total_nodes=0,
            total_edges=0,
            nodes_by_type={},
            edges_by_type={},
        )
    
    try:
        import networkx as nx
        G = nx.read_graphml(graph_file)
        
        nodes_by_type = {}
        for node, data in G.nodes(data=True):
            node_type = data.get("type", "unknown")
            nodes_by_type[node_type] = nodes_by_type.get(node_type, 0) + 1
        
        edges_by_type = {}
        for u, v, data in G.edges(data=True):
            edge_type = data.get("type", "unknown")
            edges_by_type[edge_type] = edges_by_type.get(edge_type, 0) + 1
        
        return GraphStats(
            total_nodes=len(G.nodes()),
            total_edges=len(G.edges()),
            nodes_by_type=nodes_by_type,
            edges_by_type=edges_by_type,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading graph: {e}")

@app.get("/api/graph/entities")
async def list_entities(
    entity_type: str | None = None,
    limit: int = Query(100, ge=1, le=500),
):
    """List entities in the graph."""
    graph_file = BIBLIOTECA_HOME / "graph" / "exports" / "latest.graphml"
    
    if not graph_file.exists():
        return []
    
    try:
        import networkx as nx
        G = nx.read_graphml(graph_file)
        entities = []
        
        for node, data in G.nodes(data=True):
            if entity_type and data.get("type") != entity_type:
                continue
            
            entities.append({
                "id": node,
                "type": data.get("type", "unknown"),
                "name": data.get("name", node),
                "description": data.get("description"),
            })
        
        return entities[:limit]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading graph: {e}")

@app.get("/api/graph/full")
async def get_full_graph():
    """Get full graph data for D3.js visualization."""
    graph_file = BIBLIOTECA_HOME / "graph" / "exports" / "latest.graphml"
    
    if not graph_file.exists():
        return {"nodes": [], "links": []}
    
    try:
        import networkx as nx
        G = nx.read_graphml(graph_file)
        
        nodes = []
        type_to_group = {}
        group_idx = 0
        
        for node, data in G.nodes(data=True):
            node_type = data.get("type", "unknown")
            if node_type not in type_to_group:
                type_to_group[node_type] = group_idx
                group_idx += 1
            
            nodes.append({
                "id": node,
                "type": node_type,
                "name": data.get("name", node),
                "group": type_to_group[node_type],
            })
        
        links = []
        for u, v, data in G.edges(data=True):
            links.append({
                "source": u,
                "target": v,
                "type": data.get("type", "related"),
            })
        
        return {"nodes": nodes, "links": links}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading graph: {e}")

@app.get("/api/graph/entities/{entity_id}")
async def get_entity(entity_id: str):
    """Get entity details with neighbors."""
    graph_file = BIBLIOTECA_HOME / "graph" / "exports" / "latest.graphml"
    
    if not graph_file.exists():
        raise HTTPException(status_code=404, detail="Graph not found")
    
    try:
        import networkx as nx
        G = nx.read_graphml(graph_file)
        
        if entity_id not in G:
            raise HTTPException(status_code=404, detail="Entity not found")
        
        node_data = G.nodes[entity_id]
        
        neighbors = []
        for neighbor in G.neighbors(entity_id):
            edge_data = G.edges[entity_id, neighbor]
            neighbors.append({
                "id": neighbor,
                "type": G.nodes[neighbor].get("type", "unknown"),
                "name": G.nodes[neighbor].get("name", neighbor),
                "relation": edge_data.get("type", "related"),
            })
        
        return {
            "id": entity_id,
            "type": node_data.get("type", "unknown"),
            "name": node_data.get("name", entity_id),
            "description": node_data.get("description"),
            "relations": neighbors[:50],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading graph: {e}")

# ============================================================================
# Query Endpoint
# ============================================================================

@app.post("/api/query", response_model=QueryResponse)
async def query_knowledge(request: QueryRequest):
    """Query the knowledge base."""
    import time
    
    start_time = time.time()
    
    try:
        planner = QueryPlanner(get_settings())
        registry_path = PROJECT_ROOT / "config" / "mcp-sources.yaml"
        async with MCPPool.from_yaml(registry_path) as pool:
            result = await planner.ask(
                request.query,
                pool,
                mode=request.mode,
                quality=request.quality,
            )
        
        latency_ms = (time.time() - start_time) * 1000
        plan = planner.last_plan
        
        return QueryResponse(
            answer=result.answer,
            citations=[
                citation.model_dump(mode="json")
                for citation in result.context_bundle.citations
            ],
            context={
                "intent": plan.intent.value if plan is not None else "other",
                "confidence": plan.confidence if plan is not None else 0.0,
                "route": plan.mode.value if plan is not None else request.mode,
                "sources": result.sources,
                "verbose": request.verbose,
            },
            latency_ms=latency_ms,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query failed: {e}")

# ============================================================================
# Static Files (for production)
# ============================================================================

static_dir = Path(__file__).parent.parent / "dist"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

@app.get("/{full_path:path}")
async def serve_spa(full_path: str):
    """Serve the React SPA for all non-API routes."""
    index_file = static_dir / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    raise HTTPException(status_code=404, detail="Not found")
