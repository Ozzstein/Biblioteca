# Battery Research OS — Plan 2: Ingest Pipeline

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the five pipeline agents (IngestionAgent → ExtractionAgent → NormalizationAgent → WikiCompilerAgent → GraphCuratorAgent), manifest management, wiki reader/writer, graph store, and a pipeline runner that sequences all five agents with manifest-gated incremental reprocessing.

**Architecture:** Plain Python pipeline (no LangGraph). Each agent is a class with a `run()` method. Claude-calling agents (Extraction, Normalization, WikiCompiler) accept an `anthropic.Anthropic` client as a constructor parameter for testability — unit tests use `unittest.mock.MagicMock`. The pipeline is driven by `DocumentManifest.stages_completed` — each stage runs only when its `ProcessingStage` is absent from the manifest.

**Tech Stack:** Python 3.11+, anthropic SDK, chromadb, networkx, pydantic v2, pyyaml, python-frontmatter, pandas (CSV), pdfplumber (PDF), pytest, unittest.mock

**Prerequisite:** Plan 1 is complete — all schemas, utils, config, templates, and sample data exist.

**This is Plan 2 of 6:**
- Plan 3: Research Agent (ResearchAgent coordinator + SourceSubagents)
- Plan 4: Supervisor + Runtime (SupervisorAgent LangGraph, file watcher, APScheduler)
- Plan 5: Query Layer (QueryPlannerAgent, retrieval, AnswerAgent)
- Plan 6: CLI Integration (Typer CLI, end-to-end wiring)

**Spec:** `docs/superpowers/specs/2026-04-18-battery-research-os-design.md`

---

## File Map

```
src/llm_rag/pipeline/manifest.py          ← manifest CRUD (load/save/create/update/needs_processing)
src/llm_rag/pipeline/ingestion.py         ← IngestionAgent (parse + chunk + embed)
src/llm_rag/pipeline/extraction.py        ← ExtractionAgent (Claude Haiku, batch 5 chunks/call)
src/llm_rag/pipeline/normalization.py     ← NormalizationAgent (rule-based + Claude fallback)
src/llm_rag/pipeline/wiki_compiler.py     ← WikiCompilerAgent (Claude Sonnet, section-tagged merge)
src/llm_rag/pipeline/graph_curator.py     ← GraphCuratorAgent (pure Python, NetworkX merge)
src/llm_rag/pipeline/runner.py            ← PipelineRunner (manifest-gated orchestration)

src/llm_rag/wiki/reader.py                ← parse_page(path) → WikiPage (regex section extraction)
src/llm_rag/wiki/writer.py                ← update_auto_sections(), create_page()

src/llm_rag/graph/store.py                ← GraphStore (NetworkX MultiDiGraph, GraphML I/O)
src/llm_rag/graph/builder.py              ← merge_extraction_result(result, store)

agents/prompts/extraction.md              ← editable extraction prompt template
agents/prompts/normalization.md           ← editable normalization prompt template
agents/prompts/wiki_compiler.md           ← editable wiki compiler prompt template

tests/pipeline/__init__.py
tests/pipeline/test_manifest.py           ← 8 tests
tests/pipeline/test_ingestion.py          ← 4 tests (mocked chromadb)
tests/pipeline/test_extraction.py         ← 6 tests (mocked anthropic)
tests/pipeline/test_normalization.py      ← 4 tests
tests/pipeline/test_wiki_compiler.py      ← 5 tests (mocked anthropic)
tests/pipeline/test_graph_curator.py      ← 4 tests
tests/pipeline/test_runner.py             ← 4 tests (all agents mocked)
tests/wiki/__init__.py
tests/wiki/test_reader.py                 ← 5 tests
tests/wiki/test_writer.py                 ← 4 tests
tests/graph/__init__.py
tests/graph/test_store.py                 ← 6 tests
tests/test_pipeline_integration.py        ← 2 tests (end-to-end, mocked Claude)
```

---

## Task 1: Manifest Management

**Files:**
- Create: `src/llm_rag/pipeline/manifest.py`
- Create: `tests/pipeline/__init__.py`
- Create: `tests/pipeline/test_manifest.py`

- [ ] **Step 1: Create test directory**

```bash
mkdir -p tests/pipeline tests/wiki tests/graph
touch tests/pipeline/__init__.py tests/wiki/__init__.py tests/graph/__init__.py
```

- [ ] **Step 2: Write the failing tests**

```python
# tests/pipeline/test_manifest.py
from __future__ import annotations

from pathlib import Path

import pytest

from llm_rag.pipeline.manifest import (
    create_manifest,
    load_manifest,
    manifest_path,
    needs_processing,
    save_manifest,
    update_stage,
)
from llm_rag.schemas.provenance import ProcessingStage


def test_manifest_path_is_sibling(tmp_path: Path) -> None:
    source = tmp_path / "papers" / "doc.md"
    assert manifest_path(source) == source.parent / "doc.manifest.json"


def test_load_manifest_missing_returns_none(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    assert load_manifest(source) is None


def test_create_save_load_roundtrip(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("hello battery")
    m = create_manifest(source, doc_id="papers/doc", doc_type="paper", source_connector="manual")
    save_manifest(m)
    loaded = load_manifest(source)
    assert loaded is not None
    assert loaded.doc_id == "papers/doc"
    assert loaded.content_hash.startswith("sha256:")
    assert loaded.stages_completed == []


def test_update_stage_adds_stage(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    m2 = update_stage(m, ProcessingStage.INGESTED)
    assert ProcessingStage.INGESTED in m2.stages_completed
    assert ProcessingStage.INGESTED not in m.stages_completed  # original unchanged


def test_update_stage_is_idempotent(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    m2 = update_stage(update_stage(m, ProcessingStage.INGESTED), ProcessingStage.INGESTED)
    assert m2.stages_completed.count(ProcessingStage.INGESTED) == 1


def test_needs_processing_no_manifest(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    assert needs_processing(source, ProcessingStage.INGESTED) is True


def test_needs_processing_stage_complete(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("content")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    save_manifest(update_stage(m, ProcessingStage.INGESTED))
    assert needs_processing(source, ProcessingStage.INGESTED) is False


def test_needs_processing_hash_changed(tmp_path: Path) -> None:
    source = tmp_path / "doc.md"
    source.write_text("original")
    m = create_manifest(source, doc_id="x", doc_type="paper", source_connector="manual")
    save_manifest(update_stage(m, ProcessingStage.INGESTED))
    source.write_text("changed content")
    assert needs_processing(source, ProcessingStage.INGESTED) is True
```

- [ ] **Step 3: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_manifest.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.manifest'`

- [ ] **Step 4: Implement manifest management**

```python
# src/llm_rag/pipeline/manifest.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage
from llm_rag.utils.hashing import content_hash


def manifest_path(source_path: Path) -> Path:
    return source_path.parent / f"{source_path.stem}.manifest.json"


def load_manifest(source_path: Path) -> DocumentManifest | None:
    mp = manifest_path(source_path)
    if not mp.exists():
        return None
    return DocumentManifest.model_validate_json(mp.read_text())


def save_manifest(manifest: DocumentManifest) -> None:
    mp = manifest_path(Path(manifest.source_path))
    mp.write_text(manifest.model_dump_json(indent=2))


def create_manifest(
    source_path: Path,
    doc_id: str,
    doc_type: str,
    source_connector: str,
) -> DocumentManifest:
    now = datetime.now(timezone.utc)
    return DocumentManifest(
        doc_id=doc_id,
        source_path=str(source_path),
        content_hash=content_hash(source_path),
        doc_type=doc_type,
        source_connector=source_connector,
        fetched_at=now,
        last_processed=now,
    )


def update_stage(manifest: DocumentManifest, stage: ProcessingStage) -> DocumentManifest:
    if stage in manifest.stages_completed:
        return manifest
    return manifest.model_copy(update={
        "stages_completed": [*manifest.stages_completed, stage],
        "last_processed": datetime.now(timezone.utc),
    })


def needs_processing(source_path: Path, stage: ProcessingStage) -> bool:
    manifest = load_manifest(source_path)
    if manifest is None:
        return True
    if manifest.content_hash != content_hash(source_path):
        return True
    return stage not in manifest.stages_completed
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_manifest.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/llm_rag/pipeline/manifest.py tests/pipeline/__init__.py tests/wiki/__init__.py tests/graph/__init__.py tests/pipeline/test_manifest.py
git commit -m "feat: add manifest management (load/save/create/update_stage/needs_processing)"
```

---

## Task 2: Wiki Reader

**Files:**
- Create: `src/llm_rag/wiki/reader.py`
- Create: `tests/wiki/test_reader.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/wiki/test_reader.py
from __future__ import annotations

from pathlib import Path

import pytest

from llm_rag.wiki.reader import parse_page


def make_wiki_page(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "lfp.md"
    p.write_text(content)
    return p


def test_parse_page_extracts_auto_section(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

# LFP

<!-- auto-start: evidence -->
| Source | Claim |
|--------|-------|
| doc.md | LFP 170 mAh/g |
<!-- auto-end: evidence -->
""")
    page = parse_page(p)
    assert "evidence" in page.sections
    assert page.sections["evidence"].managed_by == "auto"
    assert "LFP 170" in page.sections["evidence"].content


def test_parse_page_extracts_human_section(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

<!-- human-start: summary -->
LFP is a stable cathode.
<!-- human-end: summary -->
""")
    page = parse_page(p)
    assert "summary" in page.sections
    assert page.sections["summary"].managed_by == "human"
    assert "stable cathode" in page.sections["summary"].content


def test_parse_page_reads_frontmatter(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---
""")
    page = parse_page(p)
    assert page.entity_id == "material:lfp"
    assert page.canonical_name == "LFP"
    assert page.page_type == "material"


def test_parse_page_empty_sections(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

<!-- auto-start: evidence -->
<!-- auto-end: evidence -->
""")
    page = parse_page(p)
    assert "evidence" in page.sections
    assert page.sections["evidence"].content == ""


def test_parse_page_mixed_sections(tmp_path: Path) -> None:
    p = make_wiki_page(tmp_path, """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

<!-- auto-start: evidence -->
row1
<!-- auto-end: evidence -->

<!-- human-start: open-questions -->
What about rate capability?
<!-- human-end: open-questions -->
""")
    page = parse_page(p)
    assert len(page.sections) == 2
    assert page.sections["evidence"].managed_by == "auto"
    assert page.sections["open-questions"].managed_by == "human"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/wiki/test_reader.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.wiki.reader'`

- [ ] **Step 3: Implement wiki reader**

```python
# src/llm_rag/wiki/reader.py
from __future__ import annotations

import re
from pathlib import Path

import frontmatter

from llm_rag.schemas.wiki import WikiPage, WikiSection

_AUTO_RE = re.compile(
    r"<!-- auto-start: (\S+) -->(.*?)<!-- auto-end: \1 -->",
    re.DOTALL,
)
_HUMAN_RE = re.compile(
    r"<!-- human-start: (\S+) -->(.*?)<!-- human-end: \1 -->",
    re.DOTALL,
)


def parse_page(path: Path) -> WikiPage:
    post = frontmatter.load(str(path))
    meta = post.metadata
    body = post.content
    sections: dict[str, WikiSection] = {}

    for match in _AUTO_RE.finditer(body):
        name, raw = match.group(1), match.group(2).strip()
        sections[name] = WikiSection(name=name, managed_by="auto", content=raw)

    for match in _HUMAN_RE.finditer(body):
        name, raw = match.group(1), match.group(2).strip()
        sections[name] = WikiSection(name=name, managed_by="human", content=raw)

    return WikiPage(
        page_type=str(meta.get("entity_type", "unknown")),
        entity_id=str(meta.get("entity_id", "")),
        canonical_name=str(meta.get("canonical_name", path.stem)),
        path=str(path),
        sections=sections,
    )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/wiki/test_reader.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/wiki/reader.py tests/wiki/test_reader.py
git commit -m "feat: add wiki reader (parse_page with auto/human section extraction)"
```

---

## Task 3: Wiki Writer

**Files:**
- Create: `src/llm_rag/wiki/writer.py`
- Create: `tests/wiki/test_writer.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/wiki/test_writer.py
from __future__ import annotations

from pathlib import Path

import pytest

from llm_rag.wiki.writer import create_page, update_auto_sections


_TEMPLATE = """\
---
entity_type: material
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
---

# {{ canonical_name }}

<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

<!-- human-start: summary -->
original human content
<!-- human-end: summary -->
"""


def test_update_auto_section_replaces_content(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text(_TEMPLATE)
    update_auto_sections(p, {"evidence": "| Source | Claim |\n|---|---|\n| doc | LFP |"})
    result = p.read_text()
    assert "| Source | Claim |" in result
    assert "<!-- auto-start: evidence -->" in result
    assert "<!-- auto-end: evidence -->" in result


def test_update_auto_section_preserves_human_section(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text(_TEMPLATE)
    update_auto_sections(p, {"evidence": "new content"})
    result = p.read_text()
    assert "original human content" in result


def test_update_auto_section_empty_content(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text(_TEMPLATE)
    update_auto_sections(p, {"evidence": ""})
    result = p.read_text()
    # Tags still present, content between them is empty
    assert "<!-- auto-start: evidence -->" in result
    assert "<!-- auto-end: evidence -->" in result


def test_create_page_renders_template(tmp_path: Path) -> None:
    p = tmp_path / "wiki" / "materials" / "lfp.md"
    create_page(p, _TEMPLATE, {"entity_id": "material:lfp", "canonical_name": "LFP"})
    assert p.exists()
    content = p.read_text()
    assert 'entity_id: "material:lfp"' in content
    assert "# LFP" in content


def test_create_page_skips_existing(tmp_path: Path) -> None:
    p = tmp_path / "lfp.md"
    p.write_text("existing content")
    create_page(p, _TEMPLATE, {"entity_id": "x", "canonical_name": "X"})
    assert p.read_text() == "existing content"
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/wiki/test_writer.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.wiki.writer'`

- [ ] **Step 3: Implement wiki writer**

```python
# src/llm_rag/wiki/writer.py
from __future__ import annotations

import re
from pathlib import Path


def update_auto_sections(path: Path, sections: dict[str, str]) -> None:
    """Replace content inside auto-fenced sections. Human sections are untouched."""
    content = path.read_text()
    for name, new_content in sections.items():
        stripped = new_content.strip()
        body = f"\n{stripped}\n" if stripped else "\n"
        content = re.sub(
            rf"(<!-- auto-start: {re.escape(name)} -->).*?(<!-- auto-end: {re.escape(name)} -->)",
            rf"\g<1>{body}\g<2>",
            content,
            flags=re.DOTALL,
        )
    path.write_text(content)


def create_page(path: Path, template: str, substitutions: dict[str, str]) -> None:
    """Render template with substitutions and write to path. No-op if path exists."""
    if path.exists():
        return
    content = template
    for key, value in substitutions.items():
        content = content.replace(f"{{{{ {key} }}}}", value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/wiki/test_writer.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Run all tests so far**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASSED (schemas + hashing + chunking + config + manifest + wiki reader + wiki writer).

- [ ] **Step 6: Commit**

```bash
git add src/llm_rag/wiki/writer.py tests/wiki/test_writer.py
git commit -m "feat: add wiki writer (update_auto_sections, create_page)"
```

---

## Task 4: Graph Store + Builder

**Files:**
- Create: `src/llm_rag/graph/store.py`
- Create: `src/llm_rag/graph/builder.py`
- Create: `tests/graph/test_store.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/graph/test_store.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from llm_rag.graph.builder import merge_extraction_result
from llm_rag.graph.store import GraphStore
from llm_rag.schemas.entities import (
    Entity,
    EntityType,
    ExtractionResult,
    Material,
    Relation,
    RelationType,
)


@pytest.fixture
def store(tmp_path: Path) -> GraphStore:
    return GraphStore(snapshot_path=tmp_path / "graph.graphml")


def _make_material(entity_id: str, name: str) -> Material:
    return Material(entity_id=entity_id, canonical_name=name)


def _make_relation(rid: str, src: str, tgt: str, rtype: RelationType) -> Relation:
    return Relation(
        relation_id=rid,
        relation_type=rtype,
        source_entity_id=src,
        target_entity_id=tgt,
    )


def test_add_entity(store: GraphStore) -> None:
    store.add_entity(_make_material("material:lfp", "LFP"))
    assert store.has_node("material:lfp")
    assert store.node_count() == 1


def test_add_relation(store: GraphStore) -> None:
    store.add_entity(_make_material("material:lfp", "LFP"))
    store.add_entity(Entity(entity_id="mechanism:sei", entity_type=EntityType.FAILURE_MECHANISM, canonical_name="SEI Growth"))
    store.add_relation(_make_relation("r1", "material:lfp", "mechanism:sei", RelationType.CAUSES))
    assert store.edge_count() == 1


def test_save_and_load_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "snap.graphml"
    s = GraphStore(snapshot_path=path)
    s.add_entity(_make_material("material:lfp", "LFP"))
    s.save()

    s2 = GraphStore(snapshot_path=path)
    s2.load()
    assert s2.has_node("material:lfp")
    assert s2.node_count() == 1


def test_neighbors(store: GraphStore) -> None:
    store.add_entity(_make_material("material:lfp", "LFP"))
    store.add_entity(_make_material("material:nmc", "NMC"))
    store.add_relation(_make_relation("r1", "material:lfp", "material:nmc", RelationType.ASSOCIATED_WITH))
    assert "material:nmc" in store.neighbors("material:lfp")


def test_merge_extraction_result(store: GraphStore) -> None:
    result = ExtractionResult(
        doc_id="papers/test",
        entities=[_make_material("material:lfp", "LFP")],
        relations=[],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )
    merge_extraction_result(result, store)
    assert store.has_node("material:lfp")


def test_merge_multiple_results_accumulates(store: GraphStore) -> None:
    r1 = ExtractionResult(
        doc_id="doc1",
        entities=[_make_material("material:lfp", "LFP")],
        relations=[],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )
    r2 = ExtractionResult(
        doc_id="doc2",
        entities=[_make_material("material:nmc", "NMC")],
        relations=[],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )
    merge_extraction_result(r1, store)
    merge_extraction_result(r2, store)
    assert store.node_count() == 2
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/graph/test_store.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.graph.store'`

- [ ] **Step 3: Implement graph store**

```python
# src/llm_rag/graph/store.py
from __future__ import annotations

from pathlib import Path

import networkx as nx

from llm_rag.schemas.entities import Entity, Relation


class GraphStore:
    def __init__(self, snapshot_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self._g: nx.MultiDiGraph = nx.MultiDiGraph()

    def load(self) -> None:
        if self.snapshot_path.exists():
            self._g = nx.read_graphml(str(self.snapshot_path))

    def save(self) -> None:
        self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        nx.write_graphml(self._g, str(self.snapshot_path))

    def add_entity(self, entity: Entity) -> None:
        self._g.add_node(
            entity.entity_id,
            entity_type=entity.entity_type.value,
            canonical_name=entity.canonical_name,
        )

    def add_relation(self, relation: Relation) -> None:
        self._g.add_edge(
            relation.source_entity_id,
            relation.target_entity_id,
            key=relation.relation_id,
            relation_type=relation.relation_type.value,
            weight=str(relation.weight),
        )

    def has_node(self, entity_id: str) -> bool:
        return self._g.has_node(entity_id)

    def node_count(self) -> int:
        return self._g.number_of_nodes()

    def edge_count(self) -> int:
        return self._g.number_of_edges()

    def neighbors(self, entity_id: str) -> list[str]:
        return list(self._g.neighbors(entity_id))
```

- [ ] **Step 4: Implement graph builder**

```python
# src/llm_rag/graph/builder.py
from __future__ import annotations

from llm_rag.graph.store import GraphStore
from llm_rag.schemas.entities import ExtractionResult


def merge_extraction_result(result: ExtractionResult, store: GraphStore) -> None:
    """Add all entities and relations from an ExtractionResult into the store."""
    for entity in result.entities:
        store.add_entity(entity)
    for relation in result.relations:
        store.add_relation(relation)
```

- [ ] **Step 5: Run tests — verify they pass**

```bash
uv run pytest tests/graph/test_store.py -v
```

Expected: 6 tests PASSED.

- [ ] **Step 6: Commit**

```bash
git add src/llm_rag/graph/store.py src/llm_rag/graph/builder.py tests/graph/test_store.py
git commit -m "feat: add GraphStore (NetworkX MultiDiGraph, GraphML I/O) and merge_extraction_result"
```

---

## Task 5: Prompt Templates

**Files:**
- Create: `agents/prompts/extraction.md`
- Create: `agents/prompts/normalization.md`
- Create: `agents/prompts/wiki_compiler.md`

No tests — these are editable text files loaded by agents at runtime.

- [ ] **Step 1: Create agents/prompts/extraction.md**

```markdown
You are an expert in battery electrochemistry and materials science.

Extract all entities and relations from the text below. Return ONLY a JSON object — no explanation, no markdown fences.

Format:
{
  "entities": [
    {
      "entity_id": "material:lfp",
      "entity_type": "Material",
      "canonical_name": "LFP",
      "aliases": ["LiFePO4", "lithium iron phosphate"],
      "properties": {}
    }
  ],
  "relations": [
    {
      "relation_id": "rel-001",
      "relation_type": "USES_MATERIAL",
      "source_entity_id": "experiment:001",
      "target_entity_id": "material:lfp"
    }
  ]
}

Entity types (use exactly): Document, Project, Material, Process, Component, Formulation, Cell, TestCondition, Metric, Property, FailureMechanism, Dataset, Experiment, Claim

Relation types (use exactly): MENTIONS, USES_MATERIAL, USES_PROCESS, PRODUCES_PROPERTY, MEASURED_BY, TESTED_UNDER, AFFECTS, ASSOCIATED_WITH, CAUSES, MITIGATES, CONTRADICTS, SUPPORTED_BY, DERIVED_FROM, PART_OF, SIMULATED_BY

Rules:
- entity_id: lowercase, type-prefix:slug — "material:lfp", "process:calcination", "mechanism:sei-growth"
- Only extract entities explicitly present in the text
- Only extract relations between entities you extracted in this call
- For Claim entities, prefer concise canonical_name like "LFP 170 mAh/g claim"

Text:
{{TEXT}}
```

- [ ] **Step 2: Create agents/prompts/normalization.md**

```markdown
You are a battery materials expert. A rule-based normalizer could not resolve the entity below to a canonical name.

Given the entity details, suggest the canonical name and entity_id from battery literature.
If no standard canonical form exists, return the original values unchanged.

Return ONLY a JSON object:
{
  "entity_id": "material:lfp",
  "canonical_name": "LFP"
}

Entity to normalize:
{{ENTITY_JSON}}
```

- [ ] **Step 3: Create agents/prompts/wiki_compiler.md**

```markdown
You are updating a battery research wiki page. Given the extraction result below, generate updated content for the auto-managed sections.

Return ONLY a JSON object mapping section names to markdown content strings.
Use only section names that appear in the page template as auto sections.
Common auto sections: evidence, linked-entities, properties, causes, effects, mitigations, key-claims, supporting-evidence, contradicting-evidence, materials-used, test-conditions, key-metrics, last-updated

Evidence section format (use markdown table):
| Source | Claim | Confidence | Extracted |
|--------|-------|-----------|-----------|
| doc.md §3.2 | LFP shows 170 mAh/g | 0.92 | 2026-04-18 |

Linked entities format (use markdown list):
- [LFP](../../materials/lfp.md) — Material
- [SEI Growth](../../mechanisms/sei-growth.md) — FailureMechanism

For last-updated, use ISO date string.

Extraction Result:
{{EXTRACTION_RESULT}}

Entity type for this page: {{ENTITY_TYPE}}
Entity canonical name: {{CANONICAL_NAME}}
```

- [ ] **Step 4: Commit**

```bash
git add agents/prompts/extraction.md agents/prompts/normalization.md agents/prompts/wiki_compiler.md
git commit -m "feat: add Claude prompt templates for extraction, normalization, wiki compiler"
```

---

## Task 6: IngestionAgent

**Files:**
- Create: `src/llm_rag/pipeline/ingestion.py`
- Create: `tests/pipeline/test_ingestion.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_ingestion.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_rag.pipeline.ingestion import IngestionAgent
from llm_rag.pipeline.manifest import create_manifest, load_manifest
from llm_rag.schemas.provenance import ProcessingStage


@pytest.fixture
def mock_collection() -> MagicMock:
    return MagicMock()


@pytest.fixture
def sample_doc(tmp_path: Path) -> Path:
    doc = tmp_path / "papers" / "test.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("# LFP Study\n\nLFP is a cathode material with 170 mAh/g capacity.")
    return doc


def test_ingestion_creates_jsonl(tmp_path: Path, sample_doc: Path, mock_collection: MagicMock) -> None:
    chunks_dir = tmp_path / "chunks"
    manifest = create_manifest(sample_doc, doc_id="papers/test", doc_type="paper", source_connector="manual")

    agent = IngestionAgent(chunks_dir=chunks_dir, metadata_dir=tmp_path / "meta", collection=mock_collection)
    result = agent.run(manifest)

    jsonl = chunks_dir / "papers-test.jsonl"
    assert jsonl.exists()
    lines = jsonl.read_text().strip().splitlines()
    assert len(lines) >= 1
    chunk_data = json.loads(lines[0])
    assert chunk_data["doc_id"] == "papers/test"
    assert ProcessingStage.INGESTED in result.stages_completed


def test_ingestion_calls_chroma_add(tmp_path: Path, sample_doc: Path, mock_collection: MagicMock) -> None:
    manifest = create_manifest(sample_doc, doc_id="papers/test", doc_type="paper", source_connector="manual")
    agent = IngestionAgent(chunks_dir=tmp_path / "chunks", metadata_dir=tmp_path / "meta", collection=mock_collection)
    agent.run(manifest)
    mock_collection.add.assert_called_once()


def test_ingestion_empty_file_skips_chroma(tmp_path: Path, mock_collection: MagicMock) -> None:
    doc = tmp_path / "empty.md"
    doc.write_text("")
    manifest = create_manifest(doc, doc_id="empty/doc", doc_type="paper", source_connector="manual")
    agent = IngestionAgent(chunks_dir=tmp_path / "chunks", metadata_dir=tmp_path / "meta", collection=mock_collection)
    agent.run(manifest)
    mock_collection.add.assert_not_called()


def test_ingestion_saves_manifest(tmp_path: Path, sample_doc: Path, mock_collection: MagicMock) -> None:
    manifest = create_manifest(sample_doc, doc_id="papers/test", doc_type="paper", source_connector="manual")
    agent = IngestionAgent(chunks_dir=tmp_path / "chunks", metadata_dir=tmp_path / "meta", collection=mock_collection)
    agent.run(manifest)
    loaded = load_manifest(sample_doc)
    assert loaded is not None
    assert ProcessingStage.INGESTED in loaded.stages_completed
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_ingestion.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.ingestion'`

- [ ] **Step 3: Implement IngestionAgent**

```python
# src/llm_rag/pipeline/ingestion.py
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import chromadb

from llm_rag.pipeline.manifest import save_manifest, update_stage
from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage
from llm_rag.utils.chunking import Chunk, chunk_text
from llm_rag.utils.pdf import extract_pages


class IngestionAgent:
    def __init__(
        self,
        chunks_dir: Path,
        metadata_dir: Path,
        collection: chromadb.Collection,
        chunk_size: int = 512,
        chunk_overlap: int = 64,
    ) -> None:
        self.chunks_dir = chunks_dir
        self.metadata_dir = metadata_dir
        self.collection = collection
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def run(self, manifest: DocumentManifest) -> DocumentManifest:
        source_path = Path(manifest.source_path)
        text = self._extract_text(source_path)
        chunks = chunk_text(
            text,
            doc_id=manifest.doc_id,
            chunk_size=self.chunk_size,
            overlap=self.chunk_overlap,
        )
        self._save_chunks(manifest.doc_id, chunks)
        self._embed_chunks(manifest.doc_id, chunks)
        manifest = update_stage(manifest, ProcessingStage.INGESTED)
        save_manifest(manifest)
        return manifest

    def _extract_text(self, path: Path) -> str:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            pages = extract_pages(path)
            return "\n\n".join(p.text for p in pages)
        if suffix in {".md", ".txt", ".rst"}:
            return path.read_text()
        if suffix == ".csv":
            import pandas as pd  # lazy import
            return pd.read_csv(path).to_string()
        return path.read_text()

    def _save_chunks(self, doc_id: str, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self.chunks_dir.mkdir(parents=True, exist_ok=True)
        safe_id = doc_id.replace("/", "-")
        jsonl_path = self.chunks_dir / f"{safe_id}.jsonl"
        with jsonl_path.open("w") as f:
            for chunk in chunks:
                f.write(json.dumps(asdict(chunk)) + "\n")

    def _embed_chunks(self, doc_id: str, chunks: list[Chunk]) -> None:
        if not chunks:
            return
        self.collection.add(
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
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_ingestion.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/pipeline/ingestion.py tests/pipeline/test_ingestion.py
git commit -m "feat: add IngestionAgent (parse + chunk + embed with mocked Chroma)"
```

---

## Task 7: ExtractionAgent

**Files:**
- Create: `src/llm_rag/pipeline/extraction.py`
- Create: `tests/pipeline/test_extraction.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_extraction.py
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_rag.pipeline.extraction import ExtractionAgent
from llm_rag.pipeline.manifest import create_manifest, load_manifest
from llm_rag.schemas.provenance import ProcessingStage
from llm_rag.utils.chunking import Chunk


def _mock_client(response_json: dict) -> MagicMock:
    client = MagicMock()
    msg = MagicMock()
    msg.content = [MagicMock(text=json.dumps(response_json))]
    client.messages.create.return_value = msg
    return client


def _chunks(texts: list[str], doc_id: str = "papers/test") -> list[Chunk]:
    return [
        Chunk(doc_id=doc_id, chunk_index=i, text=t, section=None, page=None, token_count=len(t) // 4)
        for i, t in enumerate(texts)
    ]


def _doc(tmp_path: Path) -> tuple[Path, object]:
    doc = tmp_path / "papers" / "test.md"
    doc.parent.mkdir(parents=True)
    doc.write_text("LFP is a cathode material.")
    manifest = create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")
    return doc, manifest


def test_extraction_returns_entities(tmp_path: Path) -> None:
    client = _mock_client({
        "entities": [{"entity_id": "material:lfp", "entity_type": "Material", "canonical_name": "LFP", "aliases": [], "properties": {}}],
        "relations": [],
    })
    doc, manifest = _doc(tmp_path)
    agent = ExtractionAgent(client=client)
    result = agent.run(manifest, _chunks(["LFP is a cathode material."]))
    assert len(result.entities) == 1
    assert result.entities[0].canonical_name == "LFP"


def test_extraction_returns_relations(tmp_path: Path) -> None:
    client = _mock_client({
        "entities": [
            {"entity_id": "material:lfp", "entity_type": "Material", "canonical_name": "LFP", "aliases": [], "properties": {}},
            {"entity_id": "mechanism:sei", "entity_type": "FailureMechanism", "canonical_name": "SEI Growth", "aliases": [], "properties": {}},
        ],
        "relations": [{"relation_id": "r1", "relation_type": "CAUSES", "source_entity_id": "material:lfp", "target_entity_id": "mechanism:sei"}],
    })
    doc, manifest = _doc(tmp_path)
    result = ExtractionAgent(client=client).run(manifest, _chunks(["LFP causes SEI."]))
    assert len(result.relations) == 1
    assert result.relations[0].relation_type.value == "CAUSES"


def test_extraction_handles_malformed_json(tmp_path: Path) -> None:
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text="not valid json at all")]
    doc, manifest = _doc(tmp_path)
    result = ExtractionAgent(client=client).run(manifest, _chunks(["some text"]))
    assert result.entities == []
    assert result.relations == []


def test_extraction_batches_at_five_chunks(tmp_path: Path) -> None:
    client = _mock_client({"entities": [], "relations": []})
    doc, manifest = _doc(tmp_path)
    ExtractionAgent(client=client).run(manifest, _chunks([f"chunk {i}" for i in range(6)]))
    assert client.messages.create.call_count == 2


def test_extraction_saves_export(tmp_path: Path) -> None:
    client = _mock_client({"entities": [], "relations": []})
    doc, manifest = _doc(tmp_path)
    exports_dir = tmp_path / "exports"
    ExtractionAgent(client=client, exports_dir=exports_dir).run(manifest, _chunks(["text"]))
    assert (exports_dir / "papers-test.json").exists()


def test_extraction_updates_manifest(tmp_path: Path) -> None:
    client = _mock_client({"entities": [], "relations": []})
    doc, manifest = _doc(tmp_path)
    ExtractionAgent(client=client).run(manifest, _chunks(["text"]))
    loaded = load_manifest(doc)
    assert loaded is not None
    assert ProcessingStage.EXTRACTED in loaded.stages_completed
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_extraction.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.extraction'`

- [ ] **Step 3: Implement ExtractionAgent**

```python
# src/llm_rag/pipeline/extraction.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import anthropic

from llm_rag.pipeline.manifest import save_manifest, update_stage
from llm_rag.schemas.entities import Entity, EntityType, ExtractionResult, Relation, RelationType
from llm_rag.schemas.provenance import (
    DocumentManifest,
    ExtractionMethod,
    ProcessingStage,
    ProvenanceRecord,
)
from llm_rag.utils.chunking import Chunk

_BATCH_SIZE = 5

_DEFAULT_PROMPT = """You are an expert in battery electrochemistry and materials science.

Extract all entities and relations from the text below. Return ONLY a JSON object — no explanation, no markdown fences.

Format:
{
  "entities": [
    {
      "entity_id": "material:lfp",
      "entity_type": "Material",
      "canonical_name": "LFP",
      "aliases": ["LiFePO4"],
      "properties": {}
    }
  ],
  "relations": [
    {
      "relation_id": "rel-001",
      "relation_type": "USES_MATERIAL",
      "source_entity_id": "experiment:001",
      "target_entity_id": "material:lfp"
    }
  ]
}

Entity types: Document, Project, Material, Process, Component, Formulation, Cell, TestCondition, Metric, Property, FailureMechanism, Dataset, Experiment, Claim
Relation types: MENTIONS, USES_MATERIAL, USES_PROCESS, PRODUCES_PROPERTY, MEASURED_BY, TESTED_UNDER, AFFECTS, ASSOCIATED_WITH, CAUSES, MITIGATES, CONTRADICTS, SUPPORTED_BY, DERIVED_FROM, PART_OF, SIMULATED_BY

Rules:
- entity_id: lowercase type-prefix:slug — "material:lfp", "mechanism:sei-growth"
- Only extract entities and relations explicitly present in the text

Text:
{{TEXT}}"""


class ExtractionAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str = "claude-haiku-4-5-20251001",
        exports_dir: Path | None = None,
        prompt_template: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.exports_dir = exports_dir
        self.prompt_template = prompt_template or _DEFAULT_PROMPT

    def run(self, manifest: DocumentManifest, chunks: list[Chunk]) -> ExtractionResult:
        all_entities: list[Entity] = []
        all_relations: list[Relation] = []

        for i in range(0, len(chunks), _BATCH_SIZE):
            batch = chunks[i : i + _BATCH_SIZE]
            entities, relations = self._extract_batch(manifest, batch)
            all_entities.extend(entities)
            all_relations.extend(relations)

        result = ExtractionResult(
            doc_id=manifest.doc_id,
            entities=all_entities,
            relations=all_relations,
            chunks_processed=len(chunks),
            extraction_model=self.model,
            extracted_at=datetime.now(timezone.utc),
        )

        if self.exports_dir is not None:
            self._save_export(result)

        manifest = update_stage(manifest, ProcessingStage.EXTRACTED)
        save_manifest(manifest)
        return result

    def _extract_batch(
        self, manifest: DocumentManifest, chunks: list[Chunk]
    ) -> tuple[list[Entity], list[Relation]]:
        combined = "\n\n---\n\n".join(c.text for c in chunks)
        prompt = self.prompt_template.replace("{{TEXT}}", combined)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if "```" in raw:
                raw = raw[: raw.rfind("```")]

        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return [], []

        prov = ProvenanceRecord(
            source_doc_id=manifest.doc_id,
            source_path=manifest.source_path,
            timestamp=datetime.now(timezone.utc),
            confidence=0.8,
            extraction_method=ExtractionMethod.CLAUDE_HAIKU,
            extractor_model=self.model,
        )
        entities = [self._parse_entity(e, prov) for e in data.get("entities", [])]
        relations = [self._parse_relation(r, prov) for r in data.get("relations", [])]
        return [e for e in entities if e is not None], [r for r in relations if r is not None]

    def _parse_entity(self, data: dict, prov: ProvenanceRecord) -> Entity | None:
        try:
            return Entity(
                entity_id=data["entity_id"],
                entity_type=EntityType(data["entity_type"]),
                canonical_name=data["canonical_name"],
                aliases=data.get("aliases", []),
                provenance=[prov],
                properties=data.get("properties", {}),
            )
        except (KeyError, ValueError):
            return None

    def _parse_relation(self, data: dict, prov: ProvenanceRecord) -> Relation | None:
        try:
            return Relation(
                relation_id=data["relation_id"],
                relation_type=RelationType(data["relation_type"]),
                source_entity_id=data["source_entity_id"],
                target_entity_id=data["target_entity_id"],
                provenance=[prov],
            )
        except (KeyError, ValueError):
            return None

    def _save_export(self, result: ExtractionResult) -> None:
        assert self.exports_dir is not None
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        safe_id = result.doc_id.replace("/", "-")
        (self.exports_dir / f"{safe_id}.json").write_text(result.model_dump_json(indent=2))
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_extraction.py -v
```

Expected: 6 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/pipeline/extraction.py tests/pipeline/test_extraction.py
git commit -m "feat: add ExtractionAgent (Claude Haiku, batched extraction, JSON parsing, mocked tests)"
```

---

## Task 8: NormalizationAgent

**Files:**
- Create: `src/llm_rag/pipeline/normalization.py`
- Create: `tests/pipeline/test_normalization.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_normalization.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

from llm_rag.pipeline.manifest import create_manifest, load_manifest
from llm_rag.pipeline.normalization import NormalizationAgent
from llm_rag.schemas.entities import Entity, EntityType, ExtractionResult
from llm_rag.schemas.provenance import ProcessingStage


@pytest.fixture
def rules_file(tmp_path: Path) -> Path:
    rules = {
        "materials": {
            "LFP": {
                "entity_id": "material:lfp",
                "aliases": ["LiFePO4", "lithium iron phosphate"],
            }
        }
    }
    p = tmp_path / "entity-normalization.yaml"
    p.write_text(yaml.dump(rules))
    return p


def _result(entities: list[Entity]) -> ExtractionResult:
    return ExtractionResult(
        doc_id="papers/test",
        entities=entities,
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )


def _entity(entity_id: str, canonical_name: str, aliases: list[str] | None = None) -> Entity:
    return Entity(
        entity_id=entity_id,
        entity_type=EntityType.MATERIAL,
        canonical_name=canonical_name,
        aliases=aliases or [],
    )


def _manifest(tmp_path: Path) -> object:
    doc = tmp_path / "doc.md"
    doc.write_text("content")
    return create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")


def test_normalization_resolves_by_canonical_name(tmp_path: Path, rules_file: Path) -> None:
    entity = _entity("material:raw", "LiFePO4")
    result = NormalizationAgent(rules_path=rules_file).run(_result([entity]), _manifest(tmp_path))
    assert result.entities[0].entity_id == "material:lfp"
    assert result.entities[0].canonical_name == "LFP"


def test_normalization_resolves_by_alias(tmp_path: Path, rules_file: Path) -> None:
    entity = _entity("material:raw", "Some Material", aliases=["LiFePO4"])
    result = NormalizationAgent(rules_path=rules_file).run(_result([entity]), _manifest(tmp_path))
    assert result.entities[0].entity_id == "material:lfp"


def test_normalization_leaves_unknown_unchanged(tmp_path: Path, rules_file: Path) -> None:
    entity = _entity("material:unknown", "SomeFutureMaterial")
    result = NormalizationAgent(rules_path=rules_file).run(_result([entity]), _manifest(tmp_path))
    assert result.entities[0].entity_id == "material:unknown"


def test_normalization_updates_manifest(tmp_path: Path, rules_file: Path) -> None:
    manifest = _manifest(tmp_path)
    NormalizationAgent(rules_path=rules_file).run(_result([]), manifest)
    doc = tmp_path / "doc.md"
    loaded = load_manifest(doc)
    assert loaded is not None
    assert ProcessingStage.NORMALIZED in loaded.stages_completed
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_normalization.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.normalization'`

- [ ] **Step 3: Implement NormalizationAgent**

```python
# src/llm_rag/pipeline/normalization.py
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from llm_rag.pipeline.manifest import save_manifest, update_stage
from llm_rag.schemas.entities import Entity, ExtractionResult
from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage


class NormalizationAgent:
    def __init__(
        self,
        rules_path: Path,
        client: Any | None = None,
        model: str = "claude-haiku-4-5-20251001",
    ) -> None:
        self.client = client
        self.model = model
        self._alias_map: dict[str, tuple[str, str]] = {}
        self._load_rules(rules_path)

    def _load_rules(self, path: Path) -> None:
        with open(path) as f:
            rules: dict[str, Any] = yaml.safe_load(f) or {}
        for section in rules.values():
            if not isinstance(section, dict):
                continue
            for canonical, data in section.items():
                if not isinstance(data, dict):
                    continue
                entity_id: str = data.get("entity_id", "")
                self._alias_map[canonical.lower()] = (entity_id, canonical)
                for alias in data.get("aliases", []):
                    self._alias_map[str(alias).lower()] = (entity_id, canonical)

    def run(self, result: ExtractionResult, manifest: DocumentManifest) -> ExtractionResult:
        normalized = [self._normalize(e) for e in result.entities]
        manifest = update_stage(manifest, ProcessingStage.NORMALIZED)
        save_manifest(manifest)
        return result.model_copy(update={"entities": normalized})

    def _normalize(self, entity: Entity) -> Entity:
        key = entity.canonical_name.lower()
        if key in self._alias_map:
            eid, cname = self._alias_map[key]
            return entity.model_copy(update={"entity_id": eid, "canonical_name": cname})
        for alias in entity.aliases:
            key = alias.lower()
            if key in self._alias_map:
                eid, cname = self._alias_map[key]
                return entity.model_copy(update={"entity_id": eid, "canonical_name": cname})
        return entity
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_normalization.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/pipeline/normalization.py tests/pipeline/test_normalization.py
git commit -m "feat: add NormalizationAgent (rule-based alias resolution from entity-normalization.yaml)"
```

---

## Task 9: WikiCompilerAgent

**Files:**
- Create: `src/llm_rag/pipeline/wiki_compiler.py`
- Create: `tests/pipeline/test_wiki_compiler.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_wiki_compiler.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_rag.pipeline.manifest import create_manifest, load_manifest
from llm_rag.pipeline.wiki_compiler import WikiCompilerAgent
from llm_rag.schemas.entities import ExtractionResult, Material
from llm_rag.schemas.provenance import ProcessingStage


_PAGE_CONTENT = """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---

# LFP

<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

<!-- human-start: summary -->
LFP is stable.
<!-- human-end: summary -->

<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
"""


def _mock_client(sections: dict) -> MagicMock:
    client = MagicMock()
    client.messages.create.return_value.content = [MagicMock(text=json.dumps(sections))]
    return client


def _result() -> ExtractionResult:
    return ExtractionResult(
        doc_id="papers/test",
        entities=[Material(entity_id="material:lfp", canonical_name="LFP", formula="LiFePO4")],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )


def _manifest(tmp_path: Path) -> object:
    doc = tmp_path / "doc.md"
    doc.write_text("LFP content")
    return create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")


def test_wiki_compiler_updates_auto_section(tmp_path: Path) -> None:
    page = tmp_path / "lfp.md"
    page.write_text(_PAGE_CONTENT)
    client = _mock_client({"evidence": "| doc | LFP 170 mAh/g | 0.9 |"})
    agent = WikiCompilerAgent(client=client)
    agent.run(_result(), _manifest(tmp_path), page_path=page)
    assert "LFP 170 mAh/g" in page.read_text()


def test_wiki_compiler_preserves_human_section(tmp_path: Path) -> None:
    page = tmp_path / "lfp.md"
    page.write_text(_PAGE_CONTENT)
    client = _mock_client({"evidence": "new evidence"})
    agent = WikiCompilerAgent(client=client)
    agent.run(_result(), _manifest(tmp_path), page_path=page)
    assert "LFP is stable." in page.read_text()


def test_wiki_compiler_calls_claude(tmp_path: Path) -> None:
    page = tmp_path / "lfp.md"
    page.write_text(_PAGE_CONTENT)
    client = _mock_client({"evidence": "row"})
    agent = WikiCompilerAgent(client=client)
    agent.run(_result(), _manifest(tmp_path), page_path=page)
    client.messages.create.assert_called_once()


def test_wiki_compiler_no_entities_skips_claude(tmp_path: Path) -> None:
    client = _mock_client({})
    agent = WikiCompilerAgent(client=client)
    empty_result = ExtractionResult(
        doc_id="papers/test",
        entities=[],
        chunks_processed=0,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )
    agent.run(empty_result, _manifest(tmp_path), page_path=None)
    client.messages.create.assert_not_called()


def test_wiki_compiler_updates_manifest(tmp_path: Path) -> None:
    page = tmp_path / "lfp.md"
    page.write_text(_PAGE_CONTENT)
    agent = WikiCompilerAgent(client=_mock_client({"evidence": "row"}))
    doc = tmp_path / "doc.md"
    doc.write_text("content")
    manifest = create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")
    agent.run(_result(), manifest, page_path=page)
    loaded = load_manifest(doc)
    assert loaded is not None
    assert ProcessingStage.WIKI_COMPILED in loaded.stages_completed
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_wiki_compiler.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.wiki_compiler'`

- [ ] **Step 3: Implement WikiCompilerAgent**

```python
# src/llm_rag/pipeline/wiki_compiler.py
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import anthropic

from llm_rag.pipeline.manifest import save_manifest, update_stage
from llm_rag.schemas.entities import ExtractionResult
from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage
from llm_rag.wiki.writer import update_auto_sections

_DEFAULT_PROMPT = """You are updating a battery research wiki page.
Given the extraction result below, generate updated content for the auto-managed sections.

Return ONLY a JSON object mapping section names to markdown content strings.
For evidence, use a markdown table. For linked-entities, use a markdown list.
For last-updated, use an ISO date string.

Extraction Result:
{{EXTRACTION_RESULT}}

Entity type: {{ENTITY_TYPE}}
Entity canonical name: {{CANONICAL_NAME}}"""


class WikiCompilerAgent:
    def __init__(
        self,
        client: anthropic.Anthropic,
        model: str = "claude-sonnet-4-6",
        wiki_dir: Path | None = None,
        templates_dir: Path | None = None,
        prompt_template: str | None = None,
    ) -> None:
        self.client = client
        self.model = model
        self.wiki_dir = wiki_dir
        self.templates_dir = templates_dir
        self.prompt_template = prompt_template or _DEFAULT_PROMPT

    def run(
        self,
        result: ExtractionResult,
        manifest: DocumentManifest,
        page_path: Path | None = None,
    ) -> None:
        if not result.entities or page_path is None:
            manifest = update_stage(manifest, ProcessingStage.WIKI_COMPILED)
            save_manifest(manifest)
            return

        primary = result.entities[0]
        sections = self._compile_sections(result, primary.entity_type.value, primary.canonical_name)
        update_auto_sections(page_path, sections)

        manifest = update_stage(manifest, ProcessingStage.WIKI_COMPILED)
        save_manifest(manifest)

    def _compile_sections(
        self, result: ExtractionResult, entity_type: str, canonical_name: str
    ) -> dict[str, str]:
        prompt = (
            self.prompt_template
            .replace("{{EXTRACTION_RESULT}}", result.model_dump_json(indent=2))
            .replace("{{ENTITY_TYPE}}", entity_type)
            .replace("{{CANONICAL_NAME}}", canonical_name)
        )
        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text.strip()
        if raw.startswith("```"):
            raw = "\n".join(raw.split("\n")[1:])
            if "```" in raw:
                raw = raw[: raw.rfind("```")]
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {k: str(v) for k, v in data.items()}
        except (json.JSONDecodeError, ValueError):
            pass
        return {"evidence": raw}
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_wiki_compiler.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/pipeline/wiki_compiler.py tests/pipeline/test_wiki_compiler.py
git commit -m "feat: add WikiCompilerAgent (Claude Sonnet, section-tagged merge, mocked tests)"
```

---

## Task 10: GraphCuratorAgent

**Files:**
- Create: `src/llm_rag/pipeline/graph_curator.py`
- Create: `tests/pipeline/test_graph_curator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_graph_curator.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from llm_rag.graph.store import GraphStore
from llm_rag.pipeline.graph_curator import GraphCuratorAgent
from llm_rag.pipeline.manifest import create_manifest, load_manifest
from llm_rag.schemas.entities import ExtractionResult, Material
from llm_rag.schemas.provenance import ProcessingStage


def _result(doc_id: str = "papers/test") -> ExtractionResult:
    return ExtractionResult(
        doc_id=doc_id,
        entities=[Material(entity_id="material:lfp", canonical_name="LFP", formula="LiFePO4")],
        chunks_processed=1,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )


def _manifest(tmp_path: Path) -> object:
    doc = tmp_path / "doc.md"
    doc.write_text("content")
    return create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")


def test_graph_curator_adds_entities(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "graph.graphml")
    agent = GraphCuratorAgent(store=store, exports_dir=tmp_path / "exports")
    agent.run(_result(), _manifest(tmp_path))
    assert store.has_node("material:lfp")


def test_graph_curator_saves_graph(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "graph.graphml")
    agent = GraphCuratorAgent(store=store, exports_dir=tmp_path / "exports")
    agent.run(_result(), _manifest(tmp_path))
    assert (tmp_path / "graph.graphml").exists()


def test_graph_curator_saves_normalized_export(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "graph.graphml")
    exports_dir = tmp_path / "exports"
    agent = GraphCuratorAgent(store=store, exports_dir=exports_dir)
    agent.run(_result(), _manifest(tmp_path))
    assert (exports_dir / "papers-test.normalized.json").exists()


def test_graph_curator_updates_manifest(tmp_path: Path) -> None:
    store = GraphStore(tmp_path / "graph.graphml")
    agent = GraphCuratorAgent(store=store, exports_dir=tmp_path / "exports")
    agent.run(_result(), _manifest(tmp_path))
    doc = tmp_path / "doc.md"
    loaded = load_manifest(doc)
    assert loaded is not None
    assert ProcessingStage.GRAPH_UPDATED in loaded.stages_completed
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_graph_curator.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.graph_curator'`

- [ ] **Step 3: Implement GraphCuratorAgent**

```python
# src/llm_rag/pipeline/graph_curator.py
from __future__ import annotations

from pathlib import Path

from llm_rag.graph.builder import merge_extraction_result
from llm_rag.graph.store import GraphStore
from llm_rag.pipeline.manifest import save_manifest, update_stage
from llm_rag.schemas.entities import ExtractionResult
from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage


class GraphCuratorAgent:
    def __init__(self, store: GraphStore, exports_dir: Path) -> None:
        self.store = store
        self.exports_dir = exports_dir

    def run(self, result: ExtractionResult, manifest: DocumentManifest) -> DocumentManifest:
        merge_extraction_result(result, self.store)
        self.store.save()
        self._save_normalized_export(result)
        manifest = update_stage(manifest, ProcessingStage.GRAPH_UPDATED)
        save_manifest(manifest)
        return manifest

    def _save_normalized_export(self, result: ExtractionResult) -> None:
        self.exports_dir.mkdir(parents=True, exist_ok=True)
        safe_id = result.doc_id.replace("/", "-")
        (self.exports_dir / f"{safe_id}.normalized.json").write_text(
            result.model_dump_json(indent=2)
        )
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_graph_curator.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/pipeline/graph_curator.py tests/pipeline/test_graph_curator.py
git commit -m "feat: add GraphCuratorAgent (pure Python, NetworkX merge, normalized export)"
```

---

## Task 11: Pipeline Runner

**Files:**
- Create: `src/llm_rag/pipeline/runner.py`
- Create: `tests/pipeline/test_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/pipeline/test_runner.py
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_rag.pipeline.manifest import create_manifest, save_manifest, update_stage
from llm_rag.pipeline.runner import PipelineRunner
from llm_rag.schemas.entities import ExtractionResult
from llm_rag.schemas.provenance import ProcessingStage


def _make_runner(
    ingestion: MagicMock,
    extraction: MagicMock,
    normalization: MagicMock,
    wiki_compiler: MagicMock,
    graph_curator: MagicMock,
    tmp_path: Path,
) -> PipelineRunner:
    from llm_rag.config import Settings
    settings = Settings(root_dir=tmp_path)
    return PipelineRunner(
        ingestion=ingestion,
        extraction=extraction,
        normalization=normalization,
        wiki_compiler=wiki_compiler,
        graph_curator=graph_curator,
        settings=settings,
    )


def _empty_result(doc_id: str = "papers/test") -> ExtractionResult:
    return ExtractionResult(
        doc_id=doc_id,
        entities=[],
        chunks_processed=0,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )


def _sample_doc(tmp_path: Path) -> Path:
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    doc = raw_dir / "test.md"
    doc.write_text("LFP content")
    return doc


def test_runner_calls_all_stages(tmp_path: Path) -> None:
    doc = _sample_doc(tmp_path)

    def ingestion_run(manifest):
        return update_stage(manifest, ProcessingStage.INGESTED)

    def extraction_run(manifest, chunks):
        r = _empty_result()
        m = update_stage(manifest, ProcessingStage.EXTRACTED)
        save_manifest(m)
        return r

    def normalization_run(result, manifest):
        m = update_stage(manifest, ProcessingStage.NORMALIZED)
        save_manifest(m)
        return result

    def wiki_run(result, manifest, page_path=None):
        m = update_stage(manifest, ProcessingStage.WIKI_COMPILED)
        save_manifest(m)

    def graph_run(result, manifest):
        m = update_stage(manifest, ProcessingStage.GRAPH_UPDATED)
        save_manifest(m)
        return m

    ingestion = MagicMock(side_effect=ingestion_run)
    extraction = MagicMock(side_effect=extraction_run)
    normalization = MagicMock(side_effect=normalization_run)
    wiki_compiler = MagicMock(side_effect=wiki_run)
    graph_curator = MagicMock(side_effect=graph_run)

    runner = _make_runner(ingestion, extraction, normalization, wiki_compiler, graph_curator, tmp_path)
    result = runner.run(doc)

    ingestion.run.assert_called_once()
    extraction.run.assert_called_once()
    normalization.run.assert_called_once()
    wiki_compiler.run.assert_called_once()
    graph_curator.run.assert_called_once()


def test_runner_skips_completed_ingestion(tmp_path: Path) -> None:
    doc = _sample_doc(tmp_path)
    manifest = create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    save_manifest(manifest)

    ingestion = MagicMock()
    extraction = MagicMock(return_value=_empty_result())
    normalization = MagicMock(return_value=_empty_result())
    wiki_compiler = MagicMock()
    graph_curator = MagicMock(return_value=manifest)

    runner = _make_runner(ingestion, extraction, normalization, wiki_compiler, graph_curator, tmp_path)
    runner.run(doc)
    ingestion.run.assert_not_called()


def test_runner_force_reruns_all(tmp_path: Path) -> None:
    doc = _sample_doc(tmp_path)
    manifest = create_manifest(doc, doc_id="papers/test", doc_type="paper", source_connector="manual")
    for stage in ProcessingStage:
        manifest = update_stage(manifest, stage)
    save_manifest(manifest)

    def ingestion_run(m):
        return update_stage(m, ProcessingStage.INGESTED)

    def extraction_run(m, chunks):
        r = _empty_result()
        upd = update_stage(m, ProcessingStage.EXTRACTED)
        save_manifest(upd)
        return r

    def normalization_run(result, m):
        upd = update_stage(m, ProcessingStage.NORMALIZED)
        save_manifest(upd)
        return result

    def wiki_run(result, m, page_path=None):
        upd = update_stage(m, ProcessingStage.WIKI_COMPILED)
        save_manifest(upd)

    def graph_run(result, m):
        upd = update_stage(m, ProcessingStage.GRAPH_UPDATED)
        save_manifest(upd)
        return upd

    ingestion = MagicMock(side_effect=ingestion_run)
    extraction = MagicMock(side_effect=extraction_run)
    normalization = MagicMock(side_effect=normalization_run)
    wiki_compiler = MagicMock(side_effect=wiki_run)
    graph_curator = MagicMock(side_effect=graph_run)

    runner = _make_runner(ingestion, extraction, normalization, wiki_compiler, graph_curator, tmp_path)
    runner.run(doc, force=True)

    ingestion.run.assert_called_once()
    extraction.run.assert_called_once()


def test_runner_derives_doc_id_from_raw_dir(tmp_path: Path) -> None:
    doc = _sample_doc(tmp_path)

    def ingestion_run(m):
        assert m.doc_id == "papers/test"
        return update_stage(m, ProcessingStage.INGESTED)

    def extraction_run(m, chunks):
        r = _empty_result(m.doc_id)
        upd = update_stage(m, ProcessingStage.EXTRACTED)
        save_manifest(upd)
        return r

    def normalization_run(result, m):
        upd = update_stage(m, ProcessingStage.NORMALIZED)
        save_manifest(upd)
        return result

    def wiki_run(result, m, page_path=None):
        upd = update_stage(m, ProcessingStage.WIKI_COMPILED)
        save_manifest(upd)

    def graph_run(result, m):
        upd = update_stage(m, ProcessingStage.GRAPH_UPDATED)
        save_manifest(upd)
        return upd

    runner = _make_runner(
        MagicMock(side_effect=ingestion_run),
        MagicMock(side_effect=extraction_run),
        MagicMock(side_effect=normalization_run),
        MagicMock(side_effect=wiki_run),
        MagicMock(side_effect=graph_run),
        tmp_path,
    )
    runner.run(doc)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/pipeline/test_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.pipeline.runner'`

- [ ] **Step 3: Implement PipelineRunner**

```python
# src/llm_rag/pipeline/runner.py
from __future__ import annotations

import json
from pathlib import Path

from llm_rag.config import Settings, get_settings
from llm_rag.pipeline.graph_curator import GraphCuratorAgent
from llm_rag.pipeline.ingestion import IngestionAgent
from llm_rag.pipeline.extraction import ExtractionAgent
from llm_rag.pipeline.normalization import NormalizationAgent
from llm_rag.pipeline.wiki_compiler import WikiCompilerAgent
from llm_rag.pipeline.manifest import (
    create_manifest,
    load_manifest,
    needs_processing,
)
from llm_rag.schemas.entities import ExtractionResult
from llm_rag.schemas.provenance import DocumentManifest, ProcessingStage
from llm_rag.utils.chunking import Chunk

_KNOWN_DOC_TYPES = {"papers", "reports", "datasets", "simulations", "meetings", "sop"}


class PipelineRunner:
    def __init__(
        self,
        ingestion: IngestionAgent,
        extraction: ExtractionAgent,
        normalization: NormalizationAgent,
        wiki_compiler: WikiCompilerAgent,
        graph_curator: GraphCuratorAgent,
        settings: Settings | None = None,
    ) -> None:
        self.ingestion = ingestion
        self.extraction = extraction
        self.normalization = normalization
        self.wiki_compiler = wiki_compiler
        self.graph_curator = graph_curator
        self.settings = settings or get_settings()

    def run(self, source_path: Path, force: bool = False) -> DocumentManifest:
        manifest = load_manifest(source_path) or create_manifest(
            source_path,
            doc_id=self._derive_doc_id(source_path),
            doc_type=self._infer_doc_type(source_path),
            source_connector="manual",
        )

        if force or needs_processing(source_path, ProcessingStage.INGESTED):
            manifest = self.ingestion.run(manifest)
            manifest = load_manifest(source_path) or manifest

        chunks = self._load_chunks(manifest.doc_id)

        if force or needs_processing(source_path, ProcessingStage.EXTRACTED):
            extraction_result = self.extraction.run(manifest, chunks)
            manifest = load_manifest(source_path) or manifest
        else:
            extraction_result = self._load_extraction_result(manifest.doc_id)

        if extraction_result is None:
            return manifest

        if force or needs_processing(source_path, ProcessingStage.NORMALIZED):
            extraction_result = self.normalization.run(extraction_result, manifest)
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.WIKI_COMPILED):
            self.wiki_compiler.run(extraction_result, manifest)
            manifest = load_manifest(source_path) or manifest

        if force or needs_processing(source_path, ProcessingStage.GRAPH_UPDATED):
            manifest = self.graph_curator.run(extraction_result, manifest)
            manifest = load_manifest(source_path) or manifest

        return manifest

    def _derive_doc_id(self, source_path: Path) -> str:
        try:
            rel = source_path.relative_to(self.settings.raw_dir)
            return str(rel.with_suffix(""))
        except ValueError:
            return source_path.stem

    def _infer_doc_type(self, source_path: Path) -> str:
        parent = source_path.parent.name
        return parent if parent in _KNOWN_DOC_TYPES else "unknown"

    def _load_chunks(self, doc_id: str) -> list[Chunk]:
        safe_id = doc_id.replace("/", "-")
        jsonl_path = self.settings.retrieval_dir / "chunks" / f"{safe_id}.jsonl"
        if not jsonl_path.exists():
            return []
        chunks = []
        for line in jsonl_path.read_text().splitlines():
            if line.strip():
                data = json.loads(line)
                chunks.append(Chunk(**data))
        return chunks

    def _load_extraction_result(self, doc_id: str) -> ExtractionResult | None:
        safe_id = doc_id.replace("/", "-")
        path = self.settings.graph_dir / "exports" / f"{safe_id}.json"
        if not path.exists():
            return None
        return ExtractionResult.model_validate_json(path.read_text())
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/pipeline/test_runner.py -v
```

Expected: 4 tests PASSED.

- [ ] **Step 5: Run all pipeline tests**

```bash
uv run pytest tests/pipeline/ -v
```

Expected: all tests PASSED (manifest + ingestion + extraction + normalization + wiki_compiler + graph_curator + runner).

- [ ] **Step 6: Commit**

```bash
git add src/llm_rag/pipeline/runner.py tests/pipeline/test_runner.py
git commit -m "feat: add PipelineRunner (manifest-gated, sequences all 5 pipeline agents)"
```

---

## Task 12: Integration Test

**Files:**
- Create: `tests/test_pipeline_integration.py`

The integration test runs the full pipeline end-to-end on a copy of `raw/papers/sample-lfp-degradation.md` using mocked Claude clients. All five stages run and all five `ProcessingStage` values appear in the final manifest.

- [ ] **Step 1: Write the integration test**

```python
# tests/test_pipeline_integration.py
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from llm_rag.graph.store import GraphStore
from llm_rag.pipeline.extraction import ExtractionAgent
from llm_rag.pipeline.graph_curator import GraphCuratorAgent
from llm_rag.pipeline.ingestion import IngestionAgent
from llm_rag.pipeline.manifest import load_manifest
from llm_rag.pipeline.normalization import NormalizationAgent
from llm_rag.pipeline.runner import PipelineRunner
from llm_rag.pipeline.wiki_compiler import WikiCompilerAgent
from llm_rag.schemas.provenance import ProcessingStage

_SAMPLE_DOC = Path("raw/papers/sample-lfp-degradation.md")
_NORM_RULES = Path("config/entity-normalization.yaml")

_PAGE_TEMPLATE = """\
---
entity_type: material
entity_id: "material:lfp"
canonical_name: "LFP"
---
# LFP
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->
<!-- human-start: summary -->
LFP is stable.
<!-- human-end: summary -->
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
"""

_EXTRACTION_RESPONSE = {
    "entities": [
        {
            "entity_id": "material:lfp",
            "entity_type": "Material",
            "canonical_name": "LFP",
            "aliases": ["LiFePO4"],
            "properties": {},
        },
        {
            "entity_id": "mechanism:sei",
            "entity_type": "FailureMechanism",
            "canonical_name": "SEI Growth",
            "aliases": [],
            "properties": {},
        },
    ],
    "relations": [
        {
            "relation_id": "rel-001",
            "relation_type": "CAUSES",
            "source_entity_id": "material:lfp",
            "target_entity_id": "mechanism:sei",
        }
    ],
}


@pytest.fixture
def pipeline(tmp_path: Path) -> tuple[PipelineRunner, Path]:
    # Copy sample doc into tmp_path raw/ tree
    raw_dir = tmp_path / "raw" / "papers"
    raw_dir.mkdir(parents=True)
    doc = raw_dir / "sample-lfp-degradation.md"
    shutil.copy(_SAMPLE_DOC, doc)

    # Create a wiki page for the integration test
    wiki_dir = tmp_path / "wiki" / "materials"
    wiki_dir.mkdir(parents=True)
    wiki_page = wiki_dir / "lfp.md"
    wiki_page.write_text(_PAGE_TEMPLATE)

    # Mock clients
    extraction_client = MagicMock()
    extraction_client.messages.create.return_value.content = [
        MagicMock(text=json.dumps(_EXTRACTION_RESPONSE))
    ]

    wiki_client = MagicMock()
    wiki_client.messages.create.return_value.content = [
        MagicMock(
            text=json.dumps(
                {
                    "evidence": "| sample-lfp-degradation.md | LFP 82% retention | 0.85 |",
                    "last-updated": "2026-04-19",
                }
            )
        )
    ]

    mock_collection = MagicMock()
    graph_store = GraphStore(snapshot_path=tmp_path / "graph" / "latest.graphml")

    from llm_rag.config import Settings
    settings = Settings(root_dir=tmp_path)

    runner = PipelineRunner(
        ingestion=IngestionAgent(
            chunks_dir=tmp_path / "retrieval" / "chunks",
            metadata_dir=tmp_path / "retrieval" / "metadata",
            collection=mock_collection,
        ),
        extraction=ExtractionAgent(
            client=extraction_client,
            exports_dir=tmp_path / "graph" / "exports",
        ),
        normalization=NormalizationAgent(rules_path=_NORM_RULES),
        wiki_compiler=WikiCompilerAgent(
            client=wiki_client,
        ),
        graph_curator=GraphCuratorAgent(
            store=graph_store,
            exports_dir=tmp_path / "graph" / "exports",
        ),
        settings=settings,
    )
    return runner, doc


@pytest.mark.skipif(not _SAMPLE_DOC.exists(), reason="sample doc not found — run from project root")
def test_pipeline_all_stages_complete(pipeline: tuple[PipelineRunner, Path]) -> None:
    runner, doc = pipeline
    final_manifest = runner.run(doc)
    for stage in ProcessingStage:
        assert stage in final_manifest.stages_completed, f"Stage {stage} not completed"


@pytest.mark.skipif(not _SAMPLE_DOC.exists(), reason="sample doc not found — run from project root")
def test_pipeline_idempotent_on_second_run(pipeline: tuple[PipelineRunner, Path]) -> None:
    runner, doc = pipeline
    runner.run(doc)
    # Second run — nothing should reprocess (same hash, all stages complete)
    result = runner.run(doc)
    # All stages should still be complete
    for stage in ProcessingStage:
        assert stage in result.stages_completed
```

- [ ] **Step 2: Run integration tests**

```bash
uv run pytest tests/test_pipeline_integration.py -v
```

Expected: 2 tests PASSED.

- [ ] **Step 3: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASSED. Count should be:
- test_schemas.py: ~19 tests
- test_hashing.py: 5 tests
- test_chunking.py: 8 tests
- test_config.py: 7 tests
- test_manifest.py: 8 tests
- test_ingestion.py: 4 tests
- test_extraction.py: 6 tests
- test_normalization.py: 4 tests
- test_wiki_compiler.py: 5 tests
- test_graph_curator.py: 4 tests
- test_runner.py: 4 tests
- test_reader.py: 5 tests
- test_writer.py: 5 tests
- test_store.py: 6 tests
- test_pipeline_integration.py: 2 tests

Total: ~97 tests.

- [ ] **Step 4: Run linting and type checking**

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: no errors. If mypy reports issues with `Any` types in `NormalizationAgent`, confirm `from typing import Any` is imported.

- [ ] **Step 5: Commit**

```bash
git add tests/test_pipeline_integration.py
git commit -m "test: add end-to-end pipeline integration test (all 5 stages, mocked Claude)"
```

---

## Self-Review Checklist (do not skip)

After all tasks are implemented, verify:

- [ ] `uv run pytest tests/ -v` — all tests pass
- [ ] `uv run ruff check src/ tests/` — clean
- [ ] `uv run mypy src/` — no errors
- [ ] `uv run python -c "from llm_rag.pipeline.runner import PipelineRunner; print('ok')"` — imports cleanly
- [ ] `uv run python -c "from llm_rag.wiki.reader import parse_page; print('ok')"` — imports cleanly
- [ ] `uv run python -c "from llm_rag.graph.store import GraphStore; print('ok')"` — imports cleanly
- [ ] All 5 pipeline agents have a `run()` method
- [ ] Claude-calling agents (ExtractionAgent, NormalizationAgent, WikiCompilerAgent) accept `client` as first constructor parameter
- [ ] `agents/prompts/extraction.md`, `agents/prompts/normalization.md`, `agents/prompts/wiki_compiler.md` all exist
- [ ] `graph/builder.py` exports `merge_extraction_result(result, store)`
- [ ] `pipeline/manifest.py` exports: `manifest_path`, `load_manifest`, `save_manifest`, `create_manifest`, `update_stage`, `needs_processing`
