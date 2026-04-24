# Battery Research OS — Plan 1: Foundation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the repository, implement all Pydantic schemas, utility functions, config module, wiki page templates, sample data, and project documentation — giving every subsequent plan a complete typed foundation to build on.

**Architecture:** `src/llm_rag` Python package with typed schemas flowing through the entire system. No agents or LLM calls in this plan — pure data models, utilities, and configuration. All subsequent plans import from this foundation.

**Tech Stack:** Python 3.11+, uv, pydantic 2.x, pydantic-settings, pyyaml, pytest, ruff, mypy

**This is Plan 1 of 6:**
- Plan 2: Ingest Pipeline (IngestionAgent, ExtractionAgent, NormalizationAgent, WikiCompilerAgent, GraphCuratorAgent)
- Plan 3: Research Agent (ResearchAgent coordinator + SourceSubagents)
- Plan 4: Supervisor + Runtime (SupervisorAgent LangGraph, file watcher, APScheduler)
- Plan 5: Query Layer (QueryPlannerAgent, retrieval, AnswerAgent)
- Plan 6: CLI Integration (Typer CLI, end-to-end wiring)

**Spec:** `docs/superpowers/specs/2026-04-18-battery-research-os-design.md`

---

## File Map

```
pyproject.toml
.env.example
CLAUDE.md
README.md

src/llm_rag/__init__.py
src/llm_rag/config.py
src/llm_rag/schemas/__init__.py
src/llm_rag/schemas/provenance.py          ← ProvenanceRecord, DocumentManifest
src/llm_rag/schemas/entities.py            ← Entity, Material, Cell, Claim, Relation, ExtractionResult
src/llm_rag/schemas/wiki.py                ← WikiSection, WikiPage
src/llm_rag/utils/__init__.py
src/llm_rag/utils/hashing.py               ← content_hash(path) → str
src/llm_rag/utils/chunking.py              ← chunk_text(...) → list[Chunk]
src/llm_rag/utils/pdf.py                   ← pdfplumber wrapper (stub, used by Plan 2)
src/llm_rag/pipeline/__init__.py           (empty — Plan 2)
src/llm_rag/research/__init__.py           (empty — Plan 3)
src/llm_rag/supervisor/__init__.py         (empty — Plan 4)
src/llm_rag/query/__init__.py              (empty — Plan 5)
src/llm_rag/wiki/__init__.py               (empty — Plan 2)
src/llm_rag/graph/__init__.py              (empty — Plan 2)

tests/__init__.py
tests/test_schemas.py
tests/test_hashing.py
tests/test_chunking.py
tests/test_config.py

config/settings.yaml
config/sources.yaml
config/taxonomy.yaml
config/entity-normalization.yaml
config/page-templates/material.md
config/page-templates/process.md
config/page-templates/test.md
config/page-templates/mechanism.md
config/page-templates/dataset.md
config/page-templates/project.md
config/page-templates/synthesis.md

raw/inbox/.gitkeep
raw/papers/sample-lfp-degradation.md
raw/meetings/sample-meeting-notes.md
raw/sop/sample-coin-cell-assembly.md

wiki/index.md
wiki/log.md
graph/schema/schema.json
graph/exports/.gitkeep
graph/snapshots/.gitkeep
retrieval/chunks/.gitkeep
retrieval/embeddings/.gitkeep
retrieval/metadata/.gitkeep
agents/prompts/.gitkeep
agents/tools/.gitkeep
scripts/.gitkeep
```

---

## Task 1: Repository Scaffold + pyproject.toml

**Files:**
- Create: `pyproject.toml`
- Create: all directory `.gitkeep` files and empty `__init__.py` files
- Create: `.env.example`

- [ ] **Step 1: Initialize git and create directory structure**

```bash
cd /Users/ozzstein/Documents/Code/llm_rag
git init
mkdir -p src/llm_rag/{schemas,utils,pipeline,research,supervisor,query,wiki,graph}
mkdir -p tests
mkdir -p config/page-templates
mkdir -p raw/{inbox,papers,reports,datasets,simulations,meetings,sop}
mkdir -p wiki/{projects,concepts,materials,processes,tests,mechanisms,datasets,reports,synthesis,heuristics}
mkdir -p graph/{schema,exports,snapshots}
mkdir -p retrieval/{chunks,embeddings,metadata}
mkdir -p agents/{prompts,tools}
mkdir -p scripts
mkdir -p docs/superpowers/{specs,plans}
touch raw/inbox/.gitkeep raw/papers/.gitkeep raw/reports/.gitkeep
touch raw/datasets/.gitkeep raw/simulations/.gitkeep raw/meetings/.gitkeep raw/sop/.gitkeep
touch graph/exports/.gitkeep graph/snapshots/.gitkeep
touch retrieval/chunks/.gitkeep retrieval/embeddings/.gitkeep retrieval/metadata/.gitkeep
touch agents/prompts/.gitkeep agents/tools/.gitkeep scripts/.gitkeep
touch src/llm_rag/__init__.py
touch src/llm_rag/schemas/__init__.py
touch src/llm_rag/utils/__init__.py
touch src/llm_rag/pipeline/__init__.py
touch src/llm_rag/research/__init__.py
touch src/llm_rag/supervisor/__init__.py
touch src/llm_rag/query/__init__.py
touch src/llm_rag/wiki/__init__.py
touch src/llm_rag/graph/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Create pyproject.toml**

```toml
# pyproject.toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "llm-rag"
version = "0.1.0"
description = "Battery Research OS — autonomous research assistant for battery R&D"
requires-python = ">=3.11"
dependencies = [
    "anthropic>=0.40.0",
    "langgraph>=0.2.0",
    "typer[all]>=0.12.0",
    "chromadb>=0.5.0",
    "sentence-transformers>=3.0.0",
    "networkx[default]>=3.3",
    "lxml>=5.0.0",
    "pdfplumber>=0.11.0",
    "python-frontmatter>=1.1.0",
    "watchdog>=4.0.0",
    "apscheduler>=3.10.0",
    "httpx>=0.27.0",
    "arxiv>=2.1.0",
    "firecrawl-py>=1.0.0",
    "pandas>=2.2.0",
    "pydantic>=2.8.0",
    "pydantic-settings>=2.4.0",
    "pyyaml>=6.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.23.0",
    "ruff>=0.6.0",
    "mypy>=1.11.0",
]
scholar = [
    "google-search-results>=2.4.2",
]

[project.scripts]
llm-rag = "llm_rag.cli:app"

[tool.hatch.build.targets.wheel]
packages = ["src/llm_rag"]

[tool.ruff]
src = ["src"]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP"]

[tool.mypy]
python_version = "3.11"
strict = true
ignore_missing_imports = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

- [ ] **Step 3: Create .env.example**

```bash
# .env.example
ANTHROPIC_API_KEY=sk-ant-...
FIRECRAWL_API_KEY=fc-...
SERPAPI_KEY=        # optional — enables GoogleScholarSubagent
```

- [ ] **Step 4: Install dependencies**

```bash
uv sync --extra dev
```

Expected: uv resolves and installs all packages. No errors. Takes 1–3 minutes on first run (downloads sentence-transformers model index).

- [ ] **Step 5: Verify package is importable**

```bash
uv run python -c "import llm_rag; print('ok')"
```

Expected output: `ok`

- [ ] **Step 6: Commit**

```bash
git add .
git commit -m "chore: scaffold repository structure and pyproject.toml"
```

---

## Task 2: Provenance Schemas

**Files:**
- Create: `src/llm_rag/schemas/provenance.py`
- Create: `tests/test_schemas.py` (partial — provenance section)

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_schemas.py
from datetime import datetime, timezone
import pytest
from llm_rag.schemas.provenance import (
    ExtractionMethod,
    ProvenanceRecord,
    ProcessingStage,
    DocumentManifest,
)


def make_provenance() -> ProvenanceRecord:
    return ProvenanceRecord(
        source_doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        section="§3.2",
        timestamp=datetime(2026, 4, 18, tzinfo=timezone.utc),
        confidence=0.92,
        extraction_method=ExtractionMethod.CLAUDE_HAIKU,
        extractor_model="claude-haiku-4-5-20251001",
    )


def test_provenance_record_valid():
    p = make_provenance()
    assert p.confidence == 0.92
    assert p.extraction_method == ExtractionMethod.CLAUDE_HAIKU
    assert p.section == "§3.2"


def test_provenance_confidence_too_high():
    with pytest.raises(Exception):
        ProvenanceRecord(
            source_doc_id="x",
            source_path="x",
            timestamp=datetime.now(timezone.utc),
            confidence=1.5,
            extraction_method=ExtractionMethod.MANUAL,
        )


def test_provenance_confidence_negative():
    with pytest.raises(Exception):
        ProvenanceRecord(
            source_doc_id="x",
            source_path="x",
            timestamp=datetime.now(timezone.utc),
            confidence=-0.1,
            extraction_method=ExtractionMethod.MANUAL,
        )


def test_provenance_optional_fields_default_none():
    p = ProvenanceRecord(
        source_doc_id="papers/x",
        source_path="raw/x",
        timestamp=datetime.now(timezone.utc),
        confidence=0.8,
        extraction_method=ExtractionMethod.RULE_BASED,
    )
    assert p.section is None
    assert p.extractor_model is None


def test_document_manifest_defaults():
    m = DocumentManifest(
        doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        content_hash="sha256:abc123",
        doc_type="paper",
        source_connector="arxiv",
        fetched_at=datetime.now(timezone.utc),
        last_processed=datetime.now(timezone.utc),
    )
    assert m.stages_completed == []
    assert m.authors == []
    assert m.doi is None
    assert m.error is None


def test_document_manifest_with_stages():
    m = DocumentManifest(
        doc_id="papers/test-001",
        source_path="raw/papers/test-001.md",
        content_hash="sha256:abc123",
        doc_type="paper",
        source_connector="manual",
        fetched_at=datetime.now(timezone.utc),
        last_processed=datetime.now(timezone.utc),
        stages_completed=[ProcessingStage.INGESTED, ProcessingStage.EXTRACTED],
    )
    assert ProcessingStage.INGESTED in m.stages_completed
    assert ProcessingStage.WIKI_COMPILED not in m.stages_completed
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_schemas.py -v
```

Expected: `ModuleNotFoundError: No module named 'llm_rag.schemas.provenance'`

- [ ] **Step 3: Implement provenance schemas**

```python
# src/llm_rag/schemas/provenance.py
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ExtractionMethod(str, Enum):
    CLAUDE_HAIKU = "claude-haiku"
    CLAUDE_SONNET = "claude-sonnet"
    CLAUDE_OPUS = "claude-opus"
    RULE_BASED = "rule-based"
    MANUAL = "manual"


class ProvenanceRecord(BaseModel):
    source_doc_id: str
    source_path: str
    section: str | None = None
    timestamp: datetime
    confidence: float = Field(ge=0.0, le=1.0)
    extraction_method: ExtractionMethod
    extractor_model: str | None = None


class ProcessingStage(str, Enum):
    INGESTED = "ingested"
    EXTRACTED = "extracted"
    NORMALIZED = "normalized"
    WIKI_COMPILED = "wiki_compiled"
    GRAPH_UPDATED = "graph_updated"


class DocumentManifest(BaseModel):
    doc_id: str
    source_path: str
    content_hash: str
    doc_type: str
    title: str | None = None
    authors: list[str] = Field(default_factory=list)
    doi: str | None = None
    arxiv_id: str | None = None
    source_connector: str
    fetched_at: datetime
    stages_completed: list[ProcessingStage] = Field(default_factory=list)
    last_processed: datetime
    error: str | None = None
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_schemas.py -v
```

Expected: 6 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/schemas/provenance.py tests/test_schemas.py
git commit -m "feat: add provenance schemas (ProvenanceRecord, DocumentManifest)"
```

---

## Task 3: Entity + Relation Schemas

**Files:**
- Create: `src/llm_rag/schemas/entities.py`
- Modify: `tests/test_schemas.py` (append entity tests)

- [ ] **Step 1: Append entity tests to tests/test_schemas.py**

```python
# Append to tests/test_schemas.py (after existing imports, add these imports)
from llm_rag.schemas.entities import (
    EntityType,
    RelationType,
    Entity,
    Material,
    Cell,
    Claim,
    Relation,
    ExtractionResult,
)


# Append these test functions to tests/test_schemas.py


def test_entity_base():
    e = Entity(
        entity_id="material:lfp",
        entity_type=EntityType.MATERIAL,
        canonical_name="LFP",
    )
    assert e.aliases == []
    assert e.provenance == []
    assert e.wiki_page is None


def test_material_entity_type():
    m = Material(
        entity_id="material:lfp",
        canonical_name="LFP",
        aliases=["LiFePO4", "lithium iron phosphate"],
        formula="LiFePO4",
        material_class="cathode",
    )
    assert m.entity_type == EntityType.MATERIAL
    assert m.formula == "LiFePO4"
    assert m.crystal_structure is None


def test_cell_entity():
    c = Cell(
        entity_id="cell:pouch-lfp-001",
        canonical_name="LFP Pouch Cell 2Ah",
        chemistry="LFP/graphite",
        form_factor="pouch",
        capacity_mah=2000.0,
    )
    assert c.entity_type == EntityType.CELL
    assert c.capacity_mah == 2000.0


def test_claim_entity():
    c = Claim(
        entity_id="claim:lfp-capacity-001",
        canonical_name="LFP theoretical capacity",
        statement="LFP has a theoretical specific capacity of 170 mAh/g",
        supported_by=["papers/sample-001"],
        contradicted_by=[],
    )
    assert c.entity_type == EntityType.CLAIM
    assert "papers/sample-001" in c.supported_by


def test_relation():
    r = Relation(
        relation_id="rel-001",
        relation_type=RelationType.USES_MATERIAL,
        source_entity_id="experiment:001",
        target_entity_id="material:lfp",
    )
    assert r.weight == 1.0
    assert r.provenance == []


def test_extraction_result_empty():
    result = ExtractionResult(
        doc_id="papers/test-001",
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )
    assert result.entities == []
    assert result.relations == []
    assert result.chunks_processed == 0


def test_extraction_result_with_entities():
    m = Material(
        entity_id="material:lfp",
        canonical_name="LFP",
        formula="LiFePO4",
    )
    result = ExtractionResult(
        doc_id="papers/test-001",
        entities=[m],
        chunks_processed=5,
        extraction_model="claude-haiku-4-5-20251001",
        extracted_at=datetime.now(timezone.utc),
    )
    assert len(result.entities) == 1
    assert result.chunks_processed == 5
```

- [ ] **Step 2: Run tests — verify new tests fail**

```bash
uv run pytest tests/test_schemas.py -v
```

Expected: `ImportError` on `from llm_rag.schemas.entities import ...`

- [ ] **Step 3: Implement entity + relation schemas**

```python
# src/llm_rag/schemas/entities.py
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field

from llm_rag.schemas.provenance import ProvenanceRecord


class EntityType(str, Enum):
    DOCUMENT = "Document"
    PROJECT = "Project"
    MATERIAL = "Material"
    PROCESS = "Process"
    COMPONENT = "Component"
    FORMULATION = "Formulation"
    CELL = "Cell"
    TEST_CONDITION = "TestCondition"
    METRIC = "Metric"
    PROPERTY = "Property"
    FAILURE_MECHANISM = "FailureMechanism"
    DATASET = "Dataset"
    EXPERIMENT = "Experiment"
    CLAIM = "Claim"


class RelationType(str, Enum):
    MENTIONS = "MENTIONS"
    USES_MATERIAL = "USES_MATERIAL"
    USES_PROCESS = "USES_PROCESS"
    PRODUCES_PROPERTY = "PRODUCES_PROPERTY"
    MEASURED_BY = "MEASURED_BY"
    TESTED_UNDER = "TESTED_UNDER"
    AFFECTS = "AFFECTS"
    ASSOCIATED_WITH = "ASSOCIATED_WITH"
    CAUSES = "CAUSES"
    MITIGATES = "MITIGATES"
    CONTRADICTS = "CONTRADICTS"
    SUPPORTED_BY = "SUPPORTED_BY"
    DERIVED_FROM = "DERIVED_FROM"
    PART_OF = "PART_OF"
    SIMULATED_BY = "SIMULATED_BY"


class Entity(BaseModel):
    entity_id: str
    entity_type: EntityType
    canonical_name: str
    aliases: list[str] = Field(default_factory=list)
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    properties: dict[str, Any] = Field(default_factory=dict)
    wiki_page: str | None = None


class Material(Entity):
    entity_type: Literal[EntityType.MATERIAL] = EntityType.MATERIAL
    formula: str | None = None
    material_class: str | None = None
    crystal_structure: str | None = None


class Cell(Entity):
    entity_type: Literal[EntityType.CELL] = EntityType.CELL
    chemistry: str | None = None
    form_factor: str | None = None
    capacity_mah: float | None = None


class Claim(Entity):
    entity_type: Literal[EntityType.CLAIM] = EntityType.CLAIM
    statement: str
    supported_by: list[str] = Field(default_factory=list)
    contradicted_by: list[str] = Field(default_factory=list)


class Relation(BaseModel):
    relation_id: str
    relation_type: RelationType
    source_entity_id: str
    target_entity_id: str
    provenance: list[ProvenanceRecord] = Field(default_factory=list)
    weight: float = 1.0


class ExtractionResult(BaseModel):
    doc_id: str
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    chunks_processed: int = 0
    extraction_model: str
    extracted_at: datetime
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
uv run pytest tests/test_schemas.py -v
```

Expected: all tests PASSED (6 provenance + 7 entity = 13 total).

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/schemas/entities.py tests/test_schemas.py
git commit -m "feat: add entity and relation schemas (14 entity types, 15 relation types)"
```

---

## Task 4: Wiki Schemas

**Files:**
- Create: `src/llm_rag/schemas/wiki.py`
- Modify: `tests/test_schemas.py` (append wiki tests)

- [ ] **Step 1: Append wiki tests to tests/test_schemas.py**

```python
# Append to tests/test_schemas.py
from llm_rag.schemas.wiki import WikiSection, WikiPage


def test_wiki_section_auto():
    s = WikiSection(name="evidence", managed_by="auto", content="| Source | Claim |")
    assert s.managed_by == "auto"
    assert "Source" in s.content


def test_wiki_section_human():
    s = WikiSection(name="summary", managed_by="human", content="LFP is stable.")
    assert s.managed_by == "human"


def test_wiki_section_defaults_empty_content():
    s = WikiSection(name="contradictions", managed_by="auto")
    assert s.content == ""


def test_wiki_page_defaults():
    page = WikiPage(
        page_type="material",
        entity_id="material:lfp",
        canonical_name="LFP",
        path="wiki/materials/lfp.md",
    )
    assert page.sections == {}
    assert page.last_auto_updated is None
    assert page.last_human_edited is None


def test_wiki_page_with_sections():
    page = WikiPage(
        page_type="material",
        entity_id="material:lfp",
        canonical_name="LFP",
        path="wiki/materials/lfp.md",
        sections={
            "evidence": WikiSection(name="evidence", managed_by="auto", content="..."),
            "summary": WikiSection(name="summary", managed_by="human", content="..."),
        },
    )
    assert "evidence" in page.sections
    assert page.sections["evidence"].managed_by == "auto"
    assert page.sections["summary"].managed_by == "human"
```

- [ ] **Step 2: Run tests — verify new tests fail**

```bash
uv run pytest tests/test_schemas.py -v
```

Expected: `ImportError` on `from llm_rag.schemas.wiki import ...`

- [ ] **Step 3: Implement wiki schemas**

```python
# src/llm_rag/schemas/wiki.py
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class WikiSection(BaseModel):
    name: str
    managed_by: Literal["auto", "human"]
    content: str = ""


class WikiPage(BaseModel):
    page_type: str
    entity_id: str
    canonical_name: str
    path: str
    sections: dict[str, WikiSection] = Field(default_factory=dict)
    last_auto_updated: datetime | None = None
    last_human_edited: datetime | None = None
```

- [ ] **Step 4: Run tests — verify all pass**

```bash
uv run pytest tests/test_schemas.py -v
```

Expected: 19 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/schemas/wiki.py tests/test_schemas.py
git commit -m "feat: add wiki schemas (WikiSection, WikiPage)"
```

---

## Task 5: Hashing Utility

**Files:**
- Create: `src/llm_rag/utils/hashing.py`
- Create: `tests/test_hashing.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_hashing.py
from pathlib import Path
from llm_rag.utils.hashing import content_hash


def test_hash_is_deterministic(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("hello battery research")
    assert content_hash(f) == content_hash(f)


def test_hash_changes_with_content(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    h1 = content_hash(f)
    f.write_text("goodbye")
    h2 = content_hash(f)
    assert h1 != h2


def test_hash_format(tmp_path: Path):
    f = tmp_path / "test.txt"
    f.write_text("test")
    h = content_hash(f)
    assert h.startswith("sha256:")
    assert len(h) == 7 + 64  # "sha256:" prefix + 64 hex chars


def test_hash_works_on_binary(tmp_path: Path):
    f = tmp_path / "test.bin"
    f.write_bytes(b"\x00\x01\x02\xff")
    h = content_hash(f)
    assert h.startswith("sha256:")


def test_different_files_different_hashes(tmp_path: Path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_text("content A")
    f2.write_text("content B")
    assert content_hash(f1) != content_hash(f2)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_hashing.py -v
```

Expected: `ImportError: cannot import name 'content_hash'`

- [ ] **Step 3: Implement hashing utility**

```python
# src/llm_rag/utils/hashing.py
from __future__ import annotations

import hashlib
from pathlib import Path


def content_hash(path: Path) -> str:
    """SHA-256 hash of file contents, prefixed with 'sha256:'."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return f"sha256:{h.hexdigest()}"
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_hashing.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add src/llm_rag/utils/hashing.py tests/test_hashing.py
git commit -m "feat: add content_hash utility (SHA-256 with sha256: prefix)"
```

---

## Task 6: Chunking Utility

**Files:**
- Create: `src/llm_rag/utils/chunking.py`
- Create: `tests/test_chunking.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_chunking.py
from llm_rag.utils.chunking import Chunk, chunk_text


def test_short_text_is_single_chunk():
    chunks = chunk_text("hello world", doc_id="test-001")
    assert len(chunks) == 1
    assert chunks[0].text == "hello world"
    assert chunks[0].chunk_index == 0
    assert chunks[0].doc_id == "test-001"


def test_empty_text_returns_no_chunks():
    chunks = chunk_text("", doc_id="test-001")
    assert chunks == []


def test_long_text_produces_multiple_chunks():
    # 512 tokens * 4 chars/token = 2048 chars per chunk
    # 3 * 2048 = 6144 chars → at least 2 chunks
    text = "word " * 1500  # ~7500 chars
    chunks = chunk_text(text, doc_id="test", chunk_size=512, overlap=64)
    assert len(chunks) >= 2


def test_chunks_are_indexed_sequentially():
    text = "A" * 5000
    chunks = chunk_text(text, doc_id="test", chunk_size=512, overlap=64)
    for i, chunk in enumerate(chunks):
        assert chunk.chunk_index == i


def test_chunks_overlap():
    text = "A" * 6000
    chunks = chunk_text(text, doc_id="test", chunk_size=512, overlap=64)
    char_size = 512 * 4  # 2048
    char_overlap = 64 * 4  # 256
    # tail of chunk 0 == head of chunk 1
    assert chunks[0].text[-char_overlap:] == chunks[1].text[:char_overlap]


def test_chunk_carries_section_and_page():
    chunks = chunk_text("some text", doc_id="x", section="§3.2", page=5)
    assert chunks[0].section == "§3.2"
    assert chunks[0].page == 5


def test_chunk_section_defaults_none():
    chunks = chunk_text("some text", doc_id="x")
    assert chunks[0].section is None
    assert chunks[0].page is None


def test_token_count_is_approximate():
    text = "A" * 400  # 400 chars ≈ 100 tokens
    chunks = chunk_text(text, doc_id="x")
    assert chunks[0].token_count == 100
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_chunking.py -v
```

Expected: `ImportError: cannot import name 'Chunk'`

- [ ] **Step 3: Implement chunking utility**

```python
# src/llm_rag/utils/chunking.py
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    text: str
    section: str | None
    page: int | None
    token_count: int


def chunk_text(
    text: str,
    doc_id: str,
    chunk_size: int = 512,
    overlap: int = 64,
    section: str | None = None,
    page: int | None = None,
) -> list[Chunk]:
    """Split text into overlapping chunks. Token count approximated as len(text) // 4."""
    if not text:
        return []

    char_size = chunk_size * 4
    char_overlap = overlap * 4
    chunks: list[Chunk] = []
    start = 0
    idx = 0

    while start < len(text):
        end = min(start + char_size, len(text))
        content = text[start:end]
        chunks.append(
            Chunk(
                doc_id=doc_id,
                chunk_index=idx,
                text=content,
                section=section,
                page=page,
                token_count=len(content) // 4,
            )
        )
        if end == len(text):
            break
        start += char_size - char_overlap
        idx += 1

    return chunks
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
uv run pytest tests/test_chunking.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 5: Create pdfplumber wrapper stub**

```python
# src/llm_rag/utils/pdf.py
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class PdfPage:
    page_number: int
    text: str
    tables: list[list[list[str | None]]]


def extract_pages(path: Path) -> list[PdfPage]:
    """Extract text and tables from a PDF using pdfplumber. Implemented in Plan 2."""
    import pdfplumber  # imported lazily — pdfplumber is heavy

    pages: list[PdfPage] = []
    with pdfplumber.open(path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            tables = page.extract_tables() or []
            pages.append(PdfPage(page_number=i + 1, text=text, tables=tables))
    return pages
```

- [ ] **Step 6: Run tests — verify still passing**

```bash
uv run pytest tests/test_chunking.py -v
```

Expected: 8 tests PASSED.

- [ ] **Step 7: Commit**

```bash
git add src/llm_rag/utils/chunking.py src/llm_rag/utils/pdf.py tests/test_chunking.py
git commit -m "feat: add chunk_text utility and pdf.py wrapper stub"
```

---

## Task 7: Config Module

**Files:**
- Create: `src/llm_rag/config.py`
- Create: `config/settings.yaml`
- Create: `config/sources.yaml`
- Create: `config/taxonomy.yaml`
- Create: `config/entity-normalization.yaml`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
from pathlib import Path
from llm_rag.config import get_settings, Settings


def test_settings_returns_settings_instance():
    s = get_settings()
    assert isinstance(s, Settings)


def test_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2


def test_default_model_assignments():
    s = get_settings()
    assert s.model_bulk_extraction == "claude-haiku-4-5-20251001"
    assert s.model_wiki_compilation == "claude-sonnet-4-6"
    assert s.model_deep_analysis == "claude-opus-4-7"


def test_default_pipeline_settings():
    s = get_settings()
    assert s.chunk_size == 512
    assert s.chunk_overlap == 64
    assert s.relevance_threshold == 0.6


def test_paths_are_path_objects():
    s = get_settings()
    assert isinstance(s.raw_dir, Path)
    assert isinstance(s.wiki_dir, Path)
    assert isinstance(s.graph_dir, Path)


def test_raw_dir_ends_with_raw():
    s = get_settings()
    assert s.raw_dir.name == "raw"


def test_missing_api_key_defaults_to_empty_string():
    s = get_settings()
    # In test environment, keys may not be set — should default to "" not raise
    assert isinstance(s.anthropic_api_key, str)
```

- [ ] **Step 2: Run tests — verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ImportError: cannot import name 'get_settings'`

- [ ] **Step 3: Implement config module**

```python
# src/llm_rag/config.py
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).parent.parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # API keys — loaded from environment or .env
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    firecrawl_api_key: str = Field(default="", alias="FIRECRAWL_API_KEY")
    serpapi_key: str = Field(default="", alias="SERPAPI_KEY")

    # Paths
    root_dir: Path = PROJECT_ROOT

    @property
    def raw_dir(self) -> Path:
        return self.root_dir / "raw"

    @property
    def wiki_dir(self) -> Path:
        return self.root_dir / "wiki"

    @property
    def graph_dir(self) -> Path:
        return self.root_dir / "graph"

    @property
    def retrieval_dir(self) -> Path:
        return self.root_dir / "retrieval"

    @property
    def config_dir(self) -> Path:
        return self.root_dir / "config"

    @property
    def agents_dir(self) -> Path:
        return self.root_dir / "agents"

    # Model assignments
    model_bulk_extraction: str = "claude-haiku-4-5-20251001"
    model_wiki_compilation: str = "claude-sonnet-4-6"
    model_contradiction: str = "claude-opus-4-7"
    model_query_synthesis: str = "claude-sonnet-4-6"
    model_deep_analysis: str = "claude-opus-4-7"
    model_relevance_scoring: str = "claude-haiku-4-5-20251001"
    model_supervisor: str = "claude-sonnet-4-6"

    # Pipeline
    chunk_size: int = 512
    chunk_overlap: int = 64
    relevance_threshold: float = 0.6
    supervisor_interval_seconds: int = 60


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 4: Create config/settings.yaml**

```yaml
# config/settings.yaml
# Operational settings. API keys belong in .env, not here.

pipeline:
  chunk_size: 512
  chunk_overlap: 64
  relevance_threshold: 0.6

supervisor:
  interval_seconds: 60

models:
  bulk_extraction: claude-haiku-4-5-20251001
  wiki_compilation: claude-sonnet-4-6
  contradiction_detection: claude-opus-4-7
  query_synthesis: claude-sonnet-4-6
  deep_analysis: claude-opus-4-7
  relevance_scoring: claude-haiku-4-5-20251001
  supervisor: claude-sonnet-4-6
```

- [ ] **Step 5: Create config/sources.yaml**

```yaml
# config/sources.yaml
# Research topics and source subagent schedules.

research_topics:
  - "LFP cycle life degradation"
  - "solid electrolyte interphase formation"
  - "silicon anode volume expansion"
  - "lithium plating mechanisms"
  - "NMC cathode structural stability"
  - "battery thermal runaway prevention"
  - "solid state electrolyte ionic conductivity"

subagents:
  arxiv:
    enabled: true
    schedule: "interval:hours=12"
    max_results_per_query: 20
    categories:
      - "cond-mat.mtrl-sci"
      - "physics.chem-ph"

  semantic_scholar:
    enabled: true
    schedule: "interval:hours=24"
    max_results_per_query: 15
    monitor_citations_of: []  # add DOIs of key papers to track citations

  openalex:
    enabled: true
    schedule: "interval:hours=24"
    max_results_per_query: 20

  pubmed:
    enabled: true
    schedule: "interval:hours=48"
    max_results_per_query: 10

  unpaywall:
    enabled: true
    schedule: "on-demand"

  firecrawl:
    enabled: true
    schedule: "on-demand"

  google_scholar:
    enabled: false  # set to true and provide SERPAPI_KEY to enable
    schedule: "interval:hours=24"
    max_results_per_query: 10
    backend: serpapi

  elsevier:
    enabled: false  # v2 — requires ELSEVIER_API_KEY
    schedule: "interval:hours=48"
```

- [ ] **Step 6: Create config/taxonomy.yaml**

```yaml
# config/taxonomy.yaml
# Battery domain taxonomy used for entity classification and search.

material_classes:
  cathode:
    - LFP
    - NMC811
    - NMC622
    - NMC532
    - NCA
    - LCO
    - LNMO
    - LMO
    - LFMP
  anode:
    - graphite
    - natural graphite
    - artificial graphite
    - silicon
    - silicon-graphite composite
    - lithium metal
    - hard carbon
    - LTO
  electrolyte:
    - LP30
    - LP57
    - LiPF6 in EC/DMC
    - solid electrolyte
    - polymer electrolyte
    - LLZO
    - LGPS
  separator:
    - polyethylene
    - polypropylene
    - Celgard 2325
    - ceramic coated

failure_mechanisms:
  - capacity fade
  - lithium plating
  - electrolyte decomposition
  - SEI growth
  - cathode dissolution
  - mechanical degradation
  - particle cracking
  - thermal runaway
  - current collector corrosion
  - lithium dendrite formation

test_types:
  - galvanostatic cycling
  - cyclic voltammetry (CV)
  - electrochemical impedance spectroscopy (EIS)
  - GITT
  - rate capability test
  - calendar aging
  - thermal characterization
  - accelerating rate calorimetry (ARC)
  - post-mortem analysis
  - SEM
  - TEM
  - XRD
  - XPS

key_metrics:
  - specific capacity (mAh/g)
  - volumetric energy density (Wh/L)
  - gravimetric energy density (Wh/kg)
  - coulombic efficiency (%)
  - capacity retention (%)
  - DC internal resistance (mΩ)
  - charge transfer resistance (Ω)
  - cycle life (cycles)
  - calendar life (years)
  - C-rate capability
```

- [ ] **Step 7: Create config/entity-normalization.yaml**

```yaml
# config/entity-normalization.yaml
# Canonical entity names and their known aliases.
# Used by NormalizationAgent for rule-based entity resolution.
# Add new entries as you encounter inconsistent naming in your corpus.

materials:
  LFP:
    entity_id: "material:lfp"
    aliases:
      - LiFePO4
      - lithium iron phosphate
      - lithium ferrophosphate
      - Li iron phosphate
      - iron phosphate cathode

  NMC811:
    entity_id: "material:nmc811"
    aliases:
      - NMC 811
      - NCM811
      - Li[Ni0.8Mn0.1Co0.1]O2
      - LiNi0.8Mn0.1Co0.1O2
      - high-nickel NMC

  NMC622:
    entity_id: "material:nmc622"
    aliases:
      - NMC 622
      - NCM622
      - LiNi0.6Mn0.2Co0.2O2

  graphite:
    entity_id: "material:graphite"
    aliases:
      - natural graphite
      - artificial graphite
      - synthetic graphite
      - MCMB
      - mesocarbon microbeads

  SEI:
    entity_id: "mechanism:sei"
    aliases:
      - solid electrolyte interphase
      - solid electrolyte interface
      - SEI layer
      - SEI film
      - passivation layer

processes:
  calcination:
    entity_id: "process:calcination"
    aliases:
      - sintering
      - high-temperature treatment
      - heat treatment
      - annealing
      - solid-state synthesis

  electrochemical_cycling:
    entity_id: "process:ec-cycling"
    aliases:
      - galvanostatic cycling
      - charge-discharge cycling
      - battery cycling
      - cycle testing

  coin_cell_assembly:
    entity_id: "process:coin-cell-assembly"
    aliases:
      - CR2032 assembly
      - half-cell assembly
      - coin cell fabrication
```

- [ ] **Step 8: Run config tests — verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 9: Commit**

```bash
git add src/llm_rag/config.py config/ tests/test_config.py
git commit -m "feat: add config module and YAML config files (settings, sources, taxonomy, normalization)"
```

---

## Task 8: Wiki Page Templates

**Files:**
- Create: `config/page-templates/material.md`
- Create: `config/page-templates/process.md`
- Create: `config/page-templates/test.md`
- Create: `config/page-templates/mechanism.md`
- Create: `config/page-templates/dataset.md`
- Create: `config/page-templates/project.md`
- Create: `config/page-templates/synthesis.md`

No tests — these are static template files parsed by WikiCompilerAgent in Plan 2.

- [ ] **Step 1: Create config/page-templates/material.md**

```markdown
---
entity_type: material
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Properties
<!-- auto-start: properties -->
<!-- auto-end: properties -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Contradictions
<!-- auto-start: contradictions -->
<!-- auto-end: contradictions -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 2: Create config/page-templates/process.md**

```markdown
---
entity_type: process
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Steps / Protocol
<!-- human-start: protocol -->

<!-- human-end: protocol -->

## Materials Used
<!-- auto-start: materials-used -->
<!-- auto-end: materials-used -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Contradictions
<!-- auto-start: contradictions -->
<!-- auto-end: contradictions -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 3: Create config/page-templates/test.md**

```markdown
---
entity_type: test
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Test Conditions
<!-- auto-start: test-conditions -->
<!-- auto-end: test-conditions -->

## Key Metrics
<!-- auto-start: key-metrics -->
<!-- auto-end: key-metrics -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Contradictions
<!-- auto-start: contradictions -->
<!-- auto-end: contradictions -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 4: Create config/page-templates/mechanism.md**

```markdown
---
entity_type: mechanism
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Causes
<!-- auto-start: causes -->
<!-- auto-end: causes -->

## Effects
<!-- auto-start: effects -->
<!-- auto-end: effects -->

## Mitigation Strategies
<!-- auto-start: mitigations -->
<!-- auto-end: mitigations -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Contradictions
<!-- auto-start: contradictions -->
<!-- auto-end: contradictions -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 5: Create config/page-templates/dataset.md**

```markdown
---
entity_type: dataset
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Schema / Columns
<!-- human-start: schema -->

<!-- human-end: schema -->

## Provenance
<!-- auto-start: provenance -->
<!-- auto-end: provenance -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 6: Create config/page-templates/project.md**

```markdown
---
entity_type: project
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Goals
<!-- human-start: goals -->

<!-- human-end: goals -->

## Key Materials & Processes
<!-- auto-start: key-entities -->
<!-- auto-end: key-entities -->

## Documents
<!-- auto-start: documents -->
<!-- auto-end: documents -->

## Evidence
<!-- auto-start: evidence -->
<!-- auto-end: evidence -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 7: Create config/page-templates/synthesis.md**

```markdown
---
entity_type: synthesis
entity_id: "{{ entity_id }}"
canonical_name: "{{ canonical_name }}"
created: "{{ created }}"
---

# {{ canonical_name }}

## Summary
<!-- human-start: summary -->

<!-- human-end: summary -->

## Key Claims
<!-- auto-start: key-claims -->
<!-- auto-end: key-claims -->

## Supporting Evidence
<!-- auto-start: supporting-evidence -->
<!-- auto-end: supporting-evidence -->

## Contradicting Evidence
<!-- auto-start: contradicting-evidence -->
<!-- auto-end: contradicting-evidence -->

## Linked Entities
<!-- auto-start: linked-entities -->
<!-- auto-end: linked-entities -->

## Open Questions
<!-- human-start: open-questions -->

<!-- human-end: open-questions -->

## Last Updated
<!-- auto-start: last-updated -->
<!-- auto-end: last-updated -->
```

- [ ] **Step 8: Commit**

```bash
git add config/page-templates/
git commit -m "feat: add wiki page templates (7 types with auto/human section fencing)"
```

---

## Task 9: Sample Data

**Files:**
- Create: `raw/papers/sample-lfp-degradation.md`
- Create: `raw/meetings/sample-meeting-notes.md`
- Create: `raw/sop/sample-coin-cell-assembly.md`
- Create: `wiki/index.md`
- Create: `wiki/log.md`
- Create: `graph/schema/schema.json`

- [ ] **Step 1: Create raw/papers/sample-lfp-degradation.md**

```markdown
---
title: "Capacity Fade Mechanisms in LFP/Graphite Cells: A Comparative Study"
authors: ["A. Researcher", "B. Scientist"]
doi: "10.xxxx/sample.2026.001"
year: 2026
source: manual
keywords: ["LFP", "capacity fade", "SEI", "cycle life", "graphite"]
---

# Capacity Fade Mechanisms in LFP/Graphite Cells

## Abstract

Lithium iron phosphate (LFP) cells demonstrate excellent cycle life compared to NMC-based
systems, primarily due to the stable olivine structure of LiFePO4. In this study, we investigate
the dominant capacity fade mechanisms in LFP/graphite pouch cells cycled at 25°C and 45°C under
C/3 charge/discharge conditions. SEI growth on the graphite anode is the primary contributor to
capacity loss at room temperature, accounting for approximately 65% of total capacity fade over
1000 cycles. At elevated temperature, electrolyte decomposition accelerates SEI growth and
contributes an additional 15% capacity loss.

## 1. Introduction

LFP remains a leading cathode material for applications requiring long cycle life and thermal
stability. Its theoretical specific capacity of 170 mAh/g and flat discharge plateau at 3.4 V
vs. Li/Li+ make it attractive for stationary storage and electric vehicles.

## 2. Experimental

### 2.1 Cell Preparation

Pouch cells (2 Ah nominal capacity) were assembled using LFP cathode (90 wt% active material,
5 wt% carbon black, 5 wt% PVDF binder) and natural graphite anode. Electrolyte: 1 M LiPF6 in
EC/DMC (1:1 v/v) with 2 wt% VC additive.

### 2.2 Testing Protocol

Cells were cycled at C/3 between 2.5 V and 3.65 V at 25°C and 45°C. Capacity measurements
recorded every 10 cycles. EIS performed every 50 cycles at 50% SOC.

## 3. Results

### 3.1 Capacity Retention

- 25°C: 82% capacity retention after 1000 cycles.
- 45°C: 71% capacity retention after 1000 cycles.

### 3.2 SEI Analysis

Post-mortem analysis confirmed SEI layer thickening on graphite anode particles:
- Initial SEI thickness: ~5 nm
- After 1000 cycles at 25°C: ~18 nm
- After 1000 cycles at 45°C: ~27 nm

### 3.3 Impedance

Charge transfer resistance (Rct) increased by 35% at 25°C and 58% at 45°C after 1000 cycles.

## 4. Discussion

SEI growth is the dominant degradation mechanism in LFP/graphite systems. The olivine LFP
cathode shows negligible structural change, confirming its superior stability. Temperature
acceleration of SEI growth follows Arrhenius behavior with activation energy of 52 kJ/mol.

## 5. Conclusions

1. LFP/graphite cells retain >80% capacity over 1000 cycles at 25°C under C/3 cycling.
2. SEI growth on graphite is the primary capacity fade mechanism (65% of total fade at 25°C).
3. Elevated temperature (45°C) accelerates capacity fade by 1.5× vs. 25°C.
4. LFP cathode shows no measurable structural degradation after 1000 cycles.
```

- [ ] **Step 2: Create raw/meetings/sample-meeting-notes.md**

```markdown
---
title: "Battery Testing Review Q1 2026"
date: 2026-01-15
attendees: ["Dr. Smith", "J. Chen", "A. Kumar"]
project: "LFP Cycle Life Study"
source: manual
---

# Battery Testing Review — Q1 2026

## Action Items from Last Meeting

- [x] Complete EIS measurements on Batch A cells — done, results in /data/batch-a-eis/
- [ ] Investigate capacity jump at cycle 450 — assigned to J. Chen
- [ ] Order new separator material (Celgard 2325) — pending procurement

## Discussion

### LFP Cell Performance

Dr. Smith presented Q1 cycling results. Batch B cells showing 3% higher capacity fade than
expected. Hypothesis: inconsistent electrolyte fill volume (±5% variance) during assembly.

J. Chen noted that cells assembled on humid days (>40% RH) show systematically higher initial
resistance — possible moisture contamination. Recommended tightening environmental controls
to <30% RH during cell assembly.

### NMC Reference Cells

NMC622 reference cells at 200 cycles. Capacity retention 91% — within spec. Rate capability
test scheduled for next month.

## Open Questions

1. Is the capacity jump at cycle 450 related to SEI restructuring or electrode particle cracking?
2. Should GITT measurements be added to characterize diffusion coefficients as cells age?
3. What is the timeline for thermal runaway characterization of aged cells?

## Next Steps

- J. Chen: complete capacity jump investigation by end of January
- A. Kumar: run humidity sensitivity experiment (3 cells at 20% RH vs. 3 cells at 50% RH)
- Team: schedule post-mortem teardown for Batch A cells at end of Q1
```

- [ ] **Step 3: Create raw/sop/sample-coin-cell-assembly.md**

```markdown
---
title: "SOP-001: Coin Cell Assembly (CR2032)"
version: "2.1"
last_updated: 2025-11-01
author: "Lab Operations"
source: manual
doc_type: sop
---

# SOP-001: Coin Cell Assembly (CR2032)

## Purpose

Standard procedure for assembling CR2032 coin cells for electrochemical characterization.

## Safety

- All assembly steps performed in argon-filled glovebox (<0.1 ppm O2, <0.1 ppm H2O).
- Electrolyte skin contact: rinse with water for 15 minutes.
- LiPF6-based electrolytes release HF when exposed to moisture — dispose in dedicated HF waste.

## Materials

- CR2032 coin cell cases (positive and negative caps)
- Cathode electrode disc (15 mm diameter)
- Anode disc or lithium metal disc (15 mm diameter)
- Separator: Celgard 2325, 19 mm diameter
- Electrolyte: 1M LiPF6 in EC/DMC 1:1 v/v
- Manual coin cell crimper

## Procedure

### 1. Preparation (inside glovebox)

1.1 Dry all components at 80°C overnight in vacuum oven before glovebox transfer.
1.2 Transfer via antechamber — minimum two pump/purge cycles.

### 2. Assembly

2.1 Place positive cap (flat side up) in assembly stand.
2.2 Place cathode disc (coated side up) in cap.
2.3 Add 40 μL electrolyte to cathode disc using micropipette.
2.4 Place separator on wetted cathode.
2.5 Add 20 μL electrolyte to separator.
2.6 Place anode disc (shiny side down for Li metal) on separator.
2.7 Place spacer disc and spring on anode.
2.8 Close with negative cap.
2.9 Crimp at 1000 N using manual crimper.

### 3. Quality Check

Measure OCV immediately after crimping. Expected ranges:
- LFP/Li: 3.3–3.5 V
- NMC/Li: 3.6–4.0 V
- Graphite/Li: 1.5–3.0 V (SOC-dependent)

Quarantine cells outside expected OCV range.

### 4. Rest Protocol

Rest assembled cells at room temperature for minimum 4 hours before electrochemical testing
to allow complete electrolyte wetting.

## Troubleshooting

| Symptom | Likely Cause | Action |
|---|---|---|
| OCV below expected range | Poor contact or partial short | Check crimp quality, remeasure |
| OCV drops immediately after crimp | Internal short circuit | Discard cell |
| High initial impedance | Insufficient electrolyte | Cannot fix post-crimp; discard |
| Electrolyte visible outside cell | Overfill or failed crimp | Discard; adjust fill volume next batch |
```

- [ ] **Step 4: Create wiki/index.md**

```markdown
# Battery Research OS — Wiki Index

This wiki is the system of understanding for battery R&D knowledge.
It is maintained by a combination of automated extraction and human curation.

## Sections

- [Materials](materials/) — cathode, anode, electrolyte, separator materials
- [Processes](processes/) — synthesis, assembly, cycling protocols
- [Tests](tests/) — test types, conditions, and results
- [Mechanisms](mechanisms/) — degradation and failure mechanisms
- [Concepts](concepts/) — electrochemical concepts and theory
- [Projects](projects/) — active and completed research projects
- [Datasets](datasets/) — experimental and simulation datasets
- [Reports](reports/) — internal reports and analyses
- [Synthesis](synthesis/) — cross-paper synthesis and meta-analyses
- [Heuristics](heuristics/) — engineering rules of thumb and best practices

## How to Use

Human-editable sections are fenced with `<!-- human-start: ... -->` / `<!-- human-end: ... -->`.
Auto-managed sections (Evidence, Linked Entities, Last Updated) are fenced with
`<!-- auto-start: ... -->` / `<!-- auto-end: ... -->` and are updated by WikiCompilerAgent.

Never manually edit auto sections — your changes will be overwritten on next compilation.

## Change Log

See [log.md](log.md) for a record of all automated updates.
```

- [ ] **Step 5: Create wiki/log.md**

```markdown
# Wiki Change Log

Automated record of all WikiCompilerAgent updates.
Human edits are not recorded here — use git history for that.

---
```

- [ ] **Step 6: Create graph/schema/schema.json**

```json
{
  "version": "1.0",
  "entity_types": [
    "Document", "Project", "Material", "Process", "Component",
    "Formulation", "Cell", "TestCondition", "Metric", "Property",
    "FailureMechanism", "Dataset", "Experiment", "Claim"
  ],
  "relation_types": [
    "MENTIONS", "USES_MATERIAL", "USES_PROCESS", "PRODUCES_PROPERTY",
    "MEASURED_BY", "TESTED_UNDER", "AFFECTS", "ASSOCIATED_WITH",
    "CAUSES", "MITIGATES", "CONTRADICTS", "SUPPORTED_BY",
    "DERIVED_FROM", "PART_OF", "SIMULATED_BY"
  ],
  "node_required_fields": ["entity_id", "entity_type", "canonical_name"],
  "edge_required_fields": ["relation_id", "relation_type", "source_entity_id", "target_entity_id"],
  "neo4j_note": "This schema is designed to map directly to Neo4j node labels and relationship types. entity_id is the unique node key."
}
```

- [ ] **Step 7: Commit**

```bash
git add raw/ wiki/ graph/schema/ 
git commit -m "feat: add sample data (paper, meeting notes, SOP), wiki index, graph schema"
```

---

## Task 10: CLAUDE.md + README + .env

**Files:**
- Create: `CLAUDE.md`
- Create: `README.md`
- Create: `.gitignore`

- [ ] **Step 1: Create .gitignore**

```gitignore
# Python
__pycache__/
*.pyc
*.pyo
.venv/
.uv/
dist/
*.egg-info/
.mypy_cache/
.ruff_cache/

# Environment
.env

# Data (large files — track structure, not content)
retrieval/embeddings/
graph/snapshots/*.graphml

# OS
.DS_Store
```

- [ ] **Step 2: Create CLAUDE.md**

```markdown
# CLAUDE.md — Battery Research OS

Battery R&D knowledge management system. Autonomously monitors research sources, ingests
documents, extracts structured knowledge, maintains a markdown wiki, builds a knowledge graph,
and answers queries with full provenance.

## Quick Start

```bash
uv sync --extra dev          # install all dependencies
cp .env.example .env         # then fill in API keys
uv run pytest tests/ -v      # run tests
uv run llm-rag run           # start autonomous supervisor loop
uv run llm-rag ask "what causes LFP capacity fade?"
```

## Repository Layout

```
src/llm_rag/          ← Python package — all source code
  schemas/            ← Pydantic models (start here to understand data structures)
  config.py           ← Settings (pydantic-settings, env vars + .env)
  pipeline/           ← 5 pipeline agents: ingestion → graph curator
  research/           ← ResearchAgent coordinator + SourceSubagents
  supervisor/         ← SupervisorAgent LangGraph + file watcher
  query/              ← QueryPlannerAgent + AnswerAgent (LangGraph)
  wiki/               ← Wiki reader + section-tagged writer
  graph/              ← NetworkX graph store interface
  utils/              ← hashing, chunking

agents/prompts/       ← Claude prompt templates (markdown, edit to tune behavior)
config/               ← YAML config files (settings, sources, taxonomy, normalization)
config/page-templates/ ← Wiki page templates per entity type
raw/                  ← Source documents (evidence store)
raw/inbox/            ← Drop zone: PDF, .url, .doi files for auto-ingestion
wiki/                 ← Markdown knowledge base (understanding store)
graph/                ← NetworkX + JSON/GraphML knowledge graph (relations store)
retrieval/            ← Chroma vector store + chunks (recall store)
docs/                 ← Spec, plans, roadmap
```

## Three Data Stores

| Store | Role | Never modify |
|---|---|---|
| `raw/` + `retrieval/` | Evidence — source docs + vector index | raw files directly; use `ingest` |
| `wiki/` | Understanding — human + auto curated markdown | `auto` sections; use `compile-wiki` |
| `graph/` | Relations — NetworkX + JSON | exports directly; use `build-graph` |

## Wiki Section Fencing

Pages have two section types. WikiCompilerAgent **only** rewrites `auto` sections.

```markdown
## Evidence
<!-- auto-start: evidence -->
...overwritten on every compile-wiki run...
<!-- auto-end: evidence -->

## Summary
<!-- human-start: summary -->
...edit freely, never touched by agents...
<!-- human-end: summary -->
```

**Rule:** Never manually edit content between `auto-start` / `auto-end` tags.

## Environment Variables (.env)

```
ANTHROPIC_API_KEY=sk-ant-...      # required for all agents
FIRECRAWL_API_KEY=fc-...          # required for URL/web ingestion
SERPAPI_KEY=...                   # optional — enables GoogleScholarSubagent
```

## Config Files

| File | Purpose |
|---|---|
| `config/settings.yaml` | Model assignments, pipeline thresholds |
| `config/sources.yaml` | Research topics + subagent schedules |
| `config/taxonomy.yaml` | Battery domain taxonomy |
| `config/entity-normalization.yaml` | Canonical entity names + aliases |
| `config/page-templates/` | Wiki page templates per entity type |

## CLI Commands

```bash
# Autonomous
uv run llm-rag run                        # start supervisor loop
uv run llm-rag status                     # show queue and stats

# Manual ingest
uv run llm-rag ingest                     # process all changed files in raw/
uv run llm-rag ingest --force             # reprocess regardless of hash
uv run llm-rag fetch --topic "LFP fade"  # search and fetch papers

# Knowledge
uv run llm-rag compile-wiki               # update all stale wiki pages
uv run llm-rag build-graph                # rebuild NetworkX graph
uv run llm-rag export-graph --format graphml

# Query
uv run llm-rag ask "question"
uv run llm-rag ask "question" --mode hybrid
uv run llm-rag ask "question" --quality   # use Opus

# Maintenance
uv run llm-rag lint-wiki
uv run llm-rag lint-wiki --fix
```

## Testing

```bash
uv run pytest tests/ -v                  # all tests
uv run pytest tests/test_schemas.py -v   # schemas only
uv run pytest -k "extraction" -v         # filter by name
uv run ruff check src/ tests/            # lint
uv run mypy src/                         # type check
```

## Adding a New Pipeline Agent

1. Create `src/llm_rag/pipeline/<name>.py` with class `<Name>Agent`
2. Implement `async def run(self, input: InputType) -> OutputType`
3. Add prompt template to `agents/prompts/<name>.md`
4. Wire into `src/llm_rag/supervisor/loop.py`
5. Add tests in `tests/pipeline/test_<name>.py`

## Adding a New Source Subagent

1. Create `src/llm_rag/research/subagents/<source>.py`
2. Implement `class <Source>Subagent` with `async def search(self, topics: list[str]) -> list[CandidateDocument]`
3. Register in `src/llm_rag/research/coordinator.py`
4. Add schedule config in `config/sources.yaml`

## Document Manifests

Each raw document has a sidecar manifest at `raw/<subdir>/<doc-id>.manifest.json`.
The pipeline checks `content_hash` to decide whether reprocessing is needed.
Delete a manifest file to force reprocessing of that document.

## Design Spec + Roadmap

- Full design: `docs/superpowers/specs/2026-04-18-battery-research-os-design.md`
- Roadmap (v2, v3): `docs/roadmap.md`
- Implementation plans: `docs/superpowers/plans/`
```

- [ ] **Step 3: Create README.md**

```markdown
# Battery Research OS

Autonomous research assistant for battery R&D knowledge management. Continuously monitors
research sources, ingests documents, extracts structured knowledge, maintains a markdown wiki,
builds a knowledge graph, and answers queries — all with full provenance.

## What It Does

- **Monitors** arXiv, Semantic Scholar, OpenAlex, PubMed, and any URL for new battery research
- **Ingests** PDFs, markdown documents, CSVs, and meeting notes automatically
- **Extracts** entities, claims, and relations using Claude (battery-domain schema)
- **Maintains** a section-tagged markdown wiki (human edits preserved)
- **Builds** a NetworkX knowledge graph (Neo4j-ready export)
- **Answers** queries with provenance-cited responses via 4-mode query planner

## Quick Start

```bash
# 1. Install
uv sync

# 2. Configure
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY and FIRECRAWL_API_KEY

# 3. Drop a document
cp my_paper.pdf raw/inbox/

# 4. Process it
uv run llm-rag ingest

# 5. Ask a question
uv run llm-rag ask "what causes LFP capacity fade?"

# 6. Run autonomously
uv run llm-rag run
```

## Architecture

```
raw/          → source documents (evidence)
wiki/         → markdown knowledge base (understanding)
graph/        → knowledge graph (relations)
retrieval/    → Chroma vector store (recall)
```

Three runtime components run when `llm-rag run` is active:
1. **SupervisorAgent** — orchestrates all work (LangGraph loop)
2. **ResearchAgent** — searches and fetches papers from 6 source subagents
3. **File watcher** — detects new files dropped into `raw/inbox/`

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) package manager
- `ANTHROPIC_API_KEY` (Claude API)
- `FIRECRAWL_API_KEY` (web scraping)

## Documentation

- **Full design spec:** `docs/superpowers/specs/2026-04-18-battery-research-os-design.md`
- **Developer guide:** `CLAUDE.md`
- **Roadmap:** `docs/roadmap.md`
```

- [ ] **Step 4: Run the full test suite**

```bash
uv run pytest tests/ -v
```

Expected: all tests PASSED (schemas, hashing, chunking, config).

- [ ] **Step 5: Run linting and type checking**

```bash
uv run ruff check src/ tests/
uv run mypy src/
```

Expected: no errors. If mypy complains about missing stubs, add `ignore_missing_imports = true` to `[tool.mypy]` in pyproject.toml (already included).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md .gitignore
git commit -m "docs: add CLAUDE.md, README, and .gitignore"
```

- [ ] **Step 7: Verify final state**

```bash
uv run pytest tests/ -v
```

Expected output includes:
```
tests/test_config.py ......                        [100%]
tests/test_chunking.py ........                    [100%]
tests/test_hashing.py .....                        [100%]
tests/test_schemas.py ...................           [100%]
======================== X passed in Xs ========================
```

---

## Self-Review Checklist (do not skip)

After implementation, verify:

- [ ] `uv run python -c "from llm_rag.schemas.entities import Material; print(Material.__fields__)"` prints field names without error
- [ ] `uv run python -c "from llm_rag.config import get_settings; s = get_settings(); print(s.raw_dir)"` prints the raw/ path
- [ ] All 7 wiki page templates exist in `config/page-templates/`
- [ ] All 3 sample documents exist in `raw/`
- [ ] `graph/schema/schema.json` is valid JSON (`uv run python -c "import json; json.load(open('graph/schema/schema.json'))"`)
- [ ] `uv run ruff check src/ tests/` — clean
- [ ] `uv run mypy src/` — no errors
