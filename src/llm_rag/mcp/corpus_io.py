from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

import chromadb
from mcp.server.fastmcp import FastMCP

from llm_rag.config import get_settings
from llm_rag.pipeline.manifest import (
    create_manifest,
    load_manifest,
    update_stage,
)
from llm_rag.pipeline.manifest import (
    save_manifest as _save_manifest_file,
)
from llm_rag.schemas.provenance import ProcessingStage
from llm_rag.utils.chunking import Chunk, chunk_text
from llm_rag.utils.hashing import content_hash

app = FastMCP("corpus-io")

_collection: chromadb.Collection | None = None


def _get_collection() -> chromadb.Collection:
    global _collection
    if _collection is None:
        settings = get_settings()
        client = chromadb.PersistentClient(path=str(settings.retrieval_dir / "embeddings"))
        _collection = client.get_or_create_collection("corpus")
    return _collection


def _extract_text(source_path: Path) -> str:
    suffix = source_path.suffix.lower()
    if suffix == ".pdf":
        from llm_rag.utils.pdf import extract_pages
        pages = extract_pages(source_path)
        return "\n\n".join(p.text for p in pages)
    if suffix in {".md", ".txt", ".rst"}:
        return source_path.read_text(encoding="utf-8")
    if suffix == ".csv":
        import pandas as pd
        return str(pd.read_csv(source_path).to_string())
    return source_path.read_text(encoding="utf-8")


def _save_chunks_jsonl(chunks_path: Path, chunks: list[Chunk]) -> None:
    lines = [json.dumps(asdict(chunk)) for chunk in chunks]
    chunks_path.write_text("\n".join(lines))


def _embed_chunks(collection: chromadb.Collection, doc_id: str, chunks: list[Chunk]) -> None:
    if not chunks:
        return
    existing = collection.get(where={"doc_id": {"$eq": doc_id}}, include=[])  # type: ignore[dict-item]
    if existing["ids"]:
        collection.delete(ids=existing["ids"])
    collection.add(
        ids=[f"{doc_id}::{chunk.chunk_index}" for chunk in chunks],
        documents=[chunk.text for chunk in chunks],
        metadatas=[
            {
                "doc_id": doc_id,
                "chunk_index": chunk.chunk_index,
                "section": chunk.section or "",
            }
            for chunk in chunks
        ],
    )


def _save_metadata_json(metadata_path: Path, doc_id: str, chunks: list[Chunk]) -> None:
    records = [
        {
            "doc_id": chunk.doc_id,
            "chunk_index": chunk.chunk_index,
            "token_count": chunk.token_count,
            "section": chunk.section,
            "page": chunk.page,
        }
        for chunk in chunks
    ]
    metadata_path.write_text(json.dumps(records, indent=2))


@app.tool()
async def get_chunks(doc_id: str) -> list[dict[str, Any]]:
    """Read chunks JSONL for a document. Returns [] if not found."""
    settings = get_settings()
    safe_id = doc_id.replace("/", "-")
    chunks_file = settings.retrieval_dir / "chunks" / f"{safe_id}.jsonl"
    if not chunks_file.exists():
        return []
    lines = chunks_file.read_text().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


@app.tool()
async def get_manifest(doc_id: str) -> dict[str, Any] | None:
    """Find and return a document manifest by doc_id. Returns None if not found."""
    settings = get_settings()
    for manifest_path in settings.raw_dir.rglob("*.manifest.json"):
        data: dict[str, Any] = json.loads(manifest_path.read_text())
        if data.get("doc_id") == doc_id:
            return data
    return None


@app.tool()
async def save_manifest(manifest: dict[str, Any]) -> None:
    """Write a manifest dict to its sidecar location next to the source file."""
    from llm_rag.pipeline.manifest import save_manifest as _save
    from llm_rag.schemas.provenance import DocumentManifest
    dm = DocumentManifest.model_validate(manifest)
    _save(dm)


@app.tool()
async def save_export(result: dict[str, Any]) -> None:
    """Write an ExtractionResult dict to graph/exports/<doc-id>.json."""
    from llm_rag.schemas.entities import ExtractionResult
    settings = get_settings()
    er = ExtractionResult.model_validate(result)
    exports_dir = settings.graph_dir / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_id = er.doc_id.replace("/", "-")
    (exports_dir / f"{safe_id}.json").write_text(er.model_dump_json(indent=2))


@app.tool()
async def list_pending_docs(missing_stage: str) -> list[str]:
    """Return doc_ids whose manifests do not include missing_stage in stages_completed."""
    settings = get_settings()
    pending: list[str] = []
    for manifest_path in settings.raw_dir.rglob("*.manifest.json"):
        data: dict[str, Any] = json.loads(manifest_path.read_text())
        stages: list[str] = data.get("stages_completed", [])
        if missing_stage not in stages:
            doc_id = data.get("doc_id", "")
            if doc_id:
                pending.append(doc_id)
    return pending


@app.tool()
async def get_export(doc_id: str) -> dict[str, Any] | None:
    """Read a saved ExtractionResult JSON from graph/exports/. Returns None if not found."""
    settings = get_settings()
    safe_id = doc_id.replace("/", "-")
    path = settings.graph_dir / "exports" / f"{safe_id}.json"
    if not path.exists():
        return None
    data: dict[str, Any] = json.loads(path.read_text())
    return data


@app.tool()
async def ingest_file(
    source_path: str,
    doc_id: str,
    doc_type: str,
    source_connector: str,
) -> dict[str, Any]:
    """Ingest a source file: extract text, chunk, embed, save JSONL/metadata, update manifest."""
    settings = get_settings()
    safe_id = doc_id.replace("/", "-")
    path = Path(source_path)

    # Extract text
    text = _extract_text(path)

    # Chunk
    chunks = chunk_text(
        text,
        doc_id=doc_id,
        chunk_size=settings.chunk_size,
        overlap=settings.chunk_overlap,
    )

    # Save chunks JSONL
    chunks_dir = settings.retrieval_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    chunks_path = chunks_dir / f"{safe_id}.jsonl"
    _save_chunks_jsonl(chunks_path, chunks)

    # Embed into Chroma
    collection = _get_collection()
    _embed_chunks(collection, doc_id, chunks)

    # Save metadata
    metadata_dir = settings.retrieval_dir / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    metadata_path = metadata_dir / f"{safe_id}.json"
    _save_metadata_json(metadata_path, doc_id, chunks)

    # Load or create manifest, refresh content_hash, update INGESTED stage
    manifest = load_manifest(path)
    if manifest is None:
        manifest = create_manifest(path, doc_id, doc_type, source_connector)
    else:
        # Always refresh the content_hash to match the current file.
        # Without this, needs_processing() would see a stale hash on every
        # subsequent call and trigger an infinite reingest loop.
        manifest = manifest.model_copy(update={"content_hash": content_hash(path)})
    manifest = update_stage(manifest, ProcessingStage.INGESTED)
    _save_manifest_file(manifest)

    return manifest.model_dump(mode="json")


@app.tool()
async def scan_pending_files() -> dict[str, list[str]]:
    """Scan raw_dir for files that need processing. Returns {"pending_paths": [...]}."""
    settings = get_settings()
    pending: list[str] = []
    for path in settings.raw_dir.rglob("*"):
        if path.is_file() and not path.name.endswith(".manifest.json"):
            manifest = load_manifest(path)
            if manifest is None or not all(
                stage in manifest.stages_completed for stage in ProcessingStage
            ):
                pending.append(str(path))
    return {"pending_paths": pending}


@app.tool()
async def search_chunks(query: str, n_results: int = 5) -> list[dict[str, Any]]:
    """Semantic similarity search over all ingested document chunks."""
    if n_results < 1:
        return []
    collection = _get_collection()
    results = collection.query(
        query_texts=[query],
        n_results=n_results,
        include=["documents", "metadatas"],
    )
    documents = results["documents"] or []
    metadatas = results["metadatas"] or []
    chunks = []
    for doc, meta in zip(documents[0] if documents else [], metadatas[0] if metadatas else []):
        chunks.append({
            "text": doc,
            "doc_id": meta.get("doc_id", ""),
            "chunk_index": meta.get("chunk_index", 0),
            "section": meta.get("section", ""),
        })
    return chunks


def main() -> None:
    app.run()
