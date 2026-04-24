# SP1: Agent SDK Tooling Foundation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver the MCP server layer, MCPPool lifecycle manager, and shared `run_agent()` runner that all future pipeline and research agents (SP2–SP6) depend on.

**Architecture:** Three domain-split FastMCP servers (`corpus-io`, `wiki-io`, `graph-io`) run as long-lived stdio subprocesses managed by `MCPPool`. A shared `run_agent()` function constructs a Claude Agent SDK `Agent` with the right model, system prompt, and MCP connections from the pool, then runs it and returns the text response. Existing pipeline agent classes are untouched (removed in SP2).

**Tech Stack:** Python 3.11+, `mcp` package (FastMCP), `claude-agent-sdk` (confirm exact PyPI name before starting — see spec), `networkx`, `pyyaml`, `pydantic`. All tests use direct function calls (no subprocess, no live API) except one smoke test gated on `ANTHROPIC_API_KEY`.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `src/llm_rag/mcp/__init__.py` | Create | Package init |
| `src/llm_rag/mcp/corpus_io.py` | Create | FastMCP app — chunk/manifest/export tools |
| `src/llm_rag/mcp/wiki_io.py` | Create | FastMCP app — wiki page read/write tools |
| `src/llm_rag/mcp/graph_io.py` | Create | FastMCP app — NetworkX entity/relation tools |
| `src/llm_rag/mcp/pool.py` | Create | MCPPool + MCPServerConfig |
| `src/llm_rag/agent_runner.py` | Create | AgentDefinition + run_agent() |
| `tests/mcp/__init__.py` | Create | Package init |
| `tests/mcp/test_corpus_io.py` | Create | corpus-io tool unit tests |
| `tests/mcp/test_wiki_io.py` | Create | wiki-io tool unit tests |
| `tests/mcp/test_graph_io.py` | Create | graph-io tool unit tests |
| `tests/test_agent_runner.py` | Create | AgentDefinition unit tests + smoke test |
| `pyproject.toml` | Modify | Add `mcp`, `claude-agent-sdk` deps + 3 script entrypoints |
| `agents/tools/` | Delete | Empty directory — removed |

---

## Task 1: Confirm SDK package and add dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Confirm the claude-agent-sdk PyPI package name**

  Run: `pip index versions claude-agent-sdk 2>/dev/null || pip index versions anthropic-agent-sdk 2>/dev/null || echo "check Anthropic docs"`

  If neither resolves, check https://docs.anthropic.com/en/agent-sdk for the exact package name and minimum version before continuing.

- [ ] **Step 2: Add dependencies and entrypoints to pyproject.toml**

  Add to `[project.dependencies]` (replace `PACKAGE_NAME` and `VERSION` with confirmed values):
  ```toml
  "mcp>=1.0.0",
  "PACKAGE_NAME>=VERSION",   # claude-agent-sdk or equivalent
  ```

  Add to `[project.scripts]`:
  ```toml
  llm-rag-corpus-io = "llm_rag.mcp.corpus_io:main"
  llm-rag-wiki-io = "llm_rag.mcp.wiki_io:main"
  llm-rag-graph-io = "llm_rag.mcp.graph_io:main"
  ```

- [ ] **Step 3: Install dependencies**

  Run: `uv sync --extra dev`
  Expected: resolves without error.

- [ ] **Step 4: Verify FastMCP imports**

  Run: `uv run python -c "from mcp.server.fastmcp import FastMCP; print('ok')"`
  Expected: `ok`

- [ ] **Step 5: Commit**

  ```bash
  git add pyproject.toml uv.lock
  git commit -m "build: add mcp and claude-agent-sdk dependencies + MCP entrypoints"
  ```

---

## Task 2: MCP package skeleton

**Files:**
- Create: `src/llm_rag/mcp/__init__.py`
- Create: `tests/mcp/__init__.py`

- [ ] **Step 1: Create package init files**

  `src/llm_rag/mcp/__init__.py` — empty file.

  `tests/mcp/__init__.py` — empty file.

- [ ] **Step 2: Verify package is importable**

  Run: `uv run python -c "import llm_rag.mcp; print('ok')"`
  Expected: `ok`

- [ ] **Step 3: Commit**

  ```bash
  git add src/llm_rag/mcp/__init__.py tests/mcp/__init__.py
  git commit -m "feat: add llm_rag.mcp package skeleton"
  ```

---

## Task 3: corpus-io MCP server

**Files:**
- Create: `src/llm_rag/mcp/corpus_io.py`
- Create: `tests/mcp/test_corpus_io.py`

- [ ] **Step 1: Write the failing tests**

  Create `tests/mcp/test_corpus_io.py`:

  ```python
  from __future__ import annotations

  import json
  from pathlib import Path

  import pytest

  from llm_rag.mcp.corpus_io import get_chunks, get_manifest, list_pending_docs, save_export, save_manifest


  @pytest.fixture()
  def raw_dir(tmp_path: Path) -> Path:
      d = tmp_path / "raw" / "papers"
      d.mkdir(parents=True)
      return tmp_path / "raw"


  @pytest.fixture()
  def chunks_dir(tmp_path: Path) -> Path:
      d = tmp_path / "retrieval" / "chunks"
      d.mkdir(parents=True)
      return d


  @pytest.fixture()
  def exports_dir(tmp_path: Path) -> Path:
      d = tmp_path / "graph" / "exports"
      d.mkdir(parents=True)
      return d


  async def test_get_chunks_returns_empty_for_missing_doc(chunks_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(chunks_dir.parent.parent))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_chunks("papers/no-such-doc")
      assert result == []
      get_settings.cache_clear()


  async def test_get_chunks_reads_jsonl(chunks_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      (chunks_dir / "papers-sample.jsonl").write_text(
          json.dumps({"text": "hello", "chunk_index": 0}) + "\n"
          + json.dumps({"text": "world", "chunk_index": 1}) + "\n"
      )
      result = await get_chunks("papers/sample")
      assert len(result) == 2
      assert result[0]["text"] == "hello"
      get_settings.cache_clear()


  async def test_get_manifest_returns_none_for_missing(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_manifest("papers/no-such-doc")
      assert result is None
      get_settings.cache_clear()


  async def test_get_manifest_finds_by_doc_id(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      manifest_data = {"doc_id": "papers/lfp-001", "source_path": "raw/papers/lfp-001.md",
                       "content_hash": "sha256:abc", "doc_type": "paper",
                       "source_connector": "arxiv", "fetched_at": "2026-01-01T00:00:00Z",
                       "last_processed": "2026-01-01T00:00:00Z", "stages_completed": [],
                       "error": None, "title": None, "authors": [], "doi": None, "arxiv_id": None}
      (raw_dir / "papers" / "lfp-001.manifest.json").write_text(json.dumps(manifest_data))
      result = await get_manifest("papers/lfp-001")
      assert result is not None
      assert result["doc_id"] == "papers/lfp-001"
      get_settings.cache_clear()


  async def test_save_manifest_writes_sidecar(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      source = raw_dir / "papers" / "lfp-001.md"
      source.write_text("content")
      manifest_data = {"doc_id": "papers/lfp-001", "source_path": str(source),
                       "content_hash": "sha256:abc", "doc_type": "paper",
                       "source_connector": "arxiv", "fetched_at": "2026-01-01T00:00:00Z",
                       "last_processed": "2026-01-01T00:00:00Z", "stages_completed": [],
                       "error": None, "title": None, "authors": [], "doi": None, "arxiv_id": None}
      await save_manifest(manifest_data)
      sidecar = raw_dir / "papers" / "lfp-001.manifest.json"
      assert sidecar.exists()
      saved = json.loads(sidecar.read_text())
      assert saved["doc_id"] == "papers/lfp-001"
      get_settings.cache_clear()


  async def test_save_export_writes_json(exports_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result_data = {
          "doc_id": "papers/lfp-001",
          "entities": [],
          "relations": [],
          "chunks_processed": 0,
          "extraction_model": "claude-haiku-4-5-20251001",
          "extracted_at": "2026-01-01T00:00:00Z",
      }
      await save_export(result_data)
      out = exports_dir / "papers-lfp-001.json"
      assert out.exists()
      assert json.loads(out.read_text())["doc_id"] == "papers/lfp-001"
      get_settings.cache_clear()


  async def test_list_pending_docs_finds_missing_stage(raw_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      manifest_data = {"doc_id": "papers/lfp-001", "source_path": "raw/papers/lfp-001.md",
                       "content_hash": "sha256:abc", "doc_type": "paper",
                       "source_connector": "arxiv", "fetched_at": "2026-01-01T00:00:00Z",
                       "last_processed": "2026-01-01T00:00:00Z", "stages_completed": ["ingested"],
                       "error": None, "title": None, "authors": [], "doi": None, "arxiv_id": None}
      (raw_dir / "papers" / "lfp-001.manifest.json").write_text(json.dumps(manifest_data))
      result = await list_pending_docs("extracted")
      assert "papers/lfp-001" in result
      get_settings.cache_clear()
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run: `uv run pytest tests/mcp/test_corpus_io.py -v`
  Expected: ImportError or ModuleNotFoundError (module doesn't exist yet).

- [ ] **Step 3: Implement corpus_io.py**

  Create `src/llm_rag/mcp/corpus_io.py`:

  ```python
  from __future__ import annotations

  import json
  from pathlib import Path

  from mcp.server.fastmcp import FastMCP

  from llm_rag.config import get_settings

  app = FastMCP("corpus-io")


  @app.tool()
  async def get_chunks(doc_id: str) -> list[dict]:
      """Read chunks JSONL for a document. Returns [] if not found."""
      settings = get_settings()
      safe_id = doc_id.replace("/", "-")
      chunks_file = settings.retrieval_dir / "chunks" / f"{safe_id}.jsonl"
      if not chunks_file.exists():
          return []
      lines = chunks_file.read_text().splitlines()
      return [json.loads(line) for line in lines if line.strip()]


  @app.tool()
  async def get_manifest(doc_id: str) -> dict | None:
      """Find and return a document manifest by doc_id. Returns None if not found."""
      settings = get_settings()
      for manifest_path in settings.raw_dir.rglob("*.manifest.json"):
          data = json.loads(manifest_path.read_text())
          if data.get("doc_id") == doc_id:
              return data
      return None


  @app.tool()
  async def save_manifest(manifest: dict) -> None:
      """Write a manifest dict to its sidecar location next to the source file."""
      from llm_rag.schemas.provenance import DocumentManifest
      from llm_rag.pipeline.manifest import save_manifest as _save
      dm = DocumentManifest.model_validate(manifest)
      _save(dm)


  @app.tool()
  async def save_export(result: dict) -> None:
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
          data = json.loads(manifest_path.read_text())
          stages: list[str] = data.get("stages_completed", [])
          if missing_stage not in stages:
              doc_id = data.get("doc_id", "")
              if doc_id:
                  pending.append(doc_id)
      return pending


  def main() -> None:
      app.run()
  ```

- [ ] **Step 4: Run tests to verify they pass**

  Run: `uv run pytest tests/mcp/test_corpus_io.py -v`
  Expected: all 5 tests PASS.

- [ ] **Step 5: Verify entrypoint starts**

  Run: `timeout 2 uv run llm-rag-corpus-io || true`
  Expected: no ImportError (may print MCP startup output or time out — both are fine).

- [ ] **Step 6: Commit**

  ```bash
  git add src/llm_rag/mcp/corpus_io.py tests/mcp/test_corpus_io.py
  git commit -m "feat: add corpus-io MCP server with chunk/manifest/export tools"
  ```

---

## Task 4: wiki-io MCP server

**Files:**
- Create: `src/llm_rag/mcp/wiki_io.py`
- Create: `tests/mcp/test_wiki_io.py`

- [ ] **Step 1: Write the failing tests**

  Create `tests/mcp/test_wiki_io.py`:

  ```python
  from __future__ import annotations

  from pathlib import Path

  import pytest

  from llm_rag.mcp.wiki_io import create_page, get_template, list_pages, read_page, write_auto_sections


  @pytest.fixture()
  def wiki_dir(tmp_path: Path) -> Path:
      d = tmp_path / "wiki"
      d.mkdir()
      return d


  @pytest.fixture()
  def templates_dir(tmp_path: Path) -> Path:
      d = tmp_path / "config" / "page-templates"
      d.mkdir(parents=True)
      return d


  async def test_read_page_returns_content(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      (wiki_dir / "materials").mkdir()
      (wiki_dir / "materials" / "lfp.md").write_text("# LFP\nsome content")
      result = await read_page("materials/lfp.md")
      assert "LFP" in result
      get_settings.cache_clear()


  async def test_read_page_raises_for_missing(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      with pytest.raises(FileNotFoundError):
          await read_page("materials/no-such.md")
      get_settings.cache_clear()


  async def test_list_pages_returns_relative_paths(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      (wiki_dir / "materials").mkdir()
      (wiki_dir / "materials" / "lfp.md").write_text("x")
      (wiki_dir / "materials" / "nmc.md").write_text("x")
      result = await list_pages("materials")
      assert "materials/lfp.md" in result
      assert "materials/nmc.md" in result
      get_settings.cache_clear()


  async def test_get_template_returns_content(templates_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      (templates_dir / "material.md").write_text("# {{ canonical_name }}")
      result = await get_template("material")
      assert "canonical_name" in result
      get_settings.cache_clear()


  async def test_write_auto_sections_updates_fenced_content(wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      (wiki_dir / "materials").mkdir()
      page = wiki_dir / "materials" / "lfp.md"
      page.write_text(
          "# LFP\n"
          "<!-- auto-start: evidence -->\nold content\n<!-- auto-end: evidence -->\n"
      )
      await write_auto_sections("materials/lfp.md", {"evidence": "| new | table |"})
      assert "new | table" in page.read_text()
      assert "old content" not in page.read_text()
      get_settings.cache_clear()


  async def test_create_page_writes_template(templates_dir: Path, wiki_dir: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      (templates_dir / "material.md").write_text("# {{ canonical_name }}\n{{ entity_id }}")
      await create_page("materials/new-material.md", "material", {"canonical_name": "NewMat", "entity_id": "material:newmat"})
      created = wiki_dir / "materials" / "new-material.md"
      assert created.exists()
      assert "NewMat" in created.read_text()
      get_settings.cache_clear()
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run: `uv run pytest tests/mcp/test_wiki_io.py -v`
  Expected: ImportError (module doesn't exist yet).

- [ ] **Step 3: Implement wiki_io.py**

  Create `src/llm_rag/mcp/wiki_io.py`:

  ```python
  from __future__ import annotations

  from pathlib import Path

  from mcp.server.fastmcp import FastMCP

  from llm_rag.config import get_settings

  app = FastMCP("wiki-io")


  @app.tool()
  async def read_page(relative_path: str) -> str:
      """Return raw markdown of a wiki page. Raises FileNotFoundError if missing."""
      settings = get_settings()
      path = settings.wiki_dir / relative_path
      if not path.exists():
          raise FileNotFoundError(f"Wiki page not found: {relative_path}")
      return path.read_text()


  @app.tool()
  async def write_auto_sections(relative_path: str, sections: dict) -> None:
      """Rewrite auto-fenced sections in a wiki page. Human sections are preserved."""
      from llm_rag.wiki.writer import update_auto_sections
      settings = get_settings()
      path = settings.wiki_dir / relative_path
      update_auto_sections(path, {k: str(v) for k, v in sections.items()})


  @app.tool()
  async def list_pages(subdir: str = "") -> list[str]:
      """List all .md files under wiki/ (or a subdir). Returns paths relative to wiki/."""
      settings = get_settings()
      base = settings.wiki_dir / subdir if subdir else settings.wiki_dir
      if not base.exists():
          return []
      return [str(p.relative_to(settings.wiki_dir)) for p in base.rglob("*.md")]


  @app.tool()
  async def get_template(page_type: str) -> str:
      """Return the Jinja-style template for a wiki page type."""
      settings = get_settings()
      template_path = settings.config_dir / "page-templates" / f"{page_type}.md"
      if not template_path.exists():
          raise FileNotFoundError(f"No template for page type: {page_type}")
      return template_path.read_text()


  @app.tool()
  async def create_page(relative_path: str, page_type: str, substitutions: dict) -> None:
      """Instantiate a page template with substitutions and write it. No-op if page exists."""
      from llm_rag.wiki.writer import create_page as _create
      settings = get_settings()
      template_path = settings.config_dir / "page-templates" / f"{page_type}.md"
      template = template_path.read_text()
      path = settings.wiki_dir / relative_path
      _create(path, template, {k: str(v) for k, v in substitutions.items()})


  def main() -> None:
      app.run()
  ```

- [ ] **Step 4: Run tests to verify they pass**

  Run: `uv run pytest tests/mcp/test_wiki_io.py -v`
  Expected: all 6 tests PASS.

- [ ] **Step 5: Verify entrypoint starts**

  Run: `timeout 2 uv run llm-rag-wiki-io || true`
  Expected: no ImportError.

- [ ] **Step 6: Commit**

  ```bash
  git add src/llm_rag/mcp/wiki_io.py tests/mcp/test_wiki_io.py
  git commit -m "feat: add wiki-io MCP server with page read/write tools"
  ```

---

## Task 5: graph-io MCP server

**Files:**
- Create: `src/llm_rag/mcp/graph_io.py`
- Create: `tests/mcp/test_graph_io.py`

- [ ] **Step 1: Write the failing tests**

  Create `tests/mcp/test_graph_io.py`:

  ```python
  from __future__ import annotations

  import json
  from pathlib import Path

  import networkx as nx
  import pytest

  from llm_rag.mcp.graph_io import get_canonical, get_entity, get_neighbors, list_entities


  @pytest.fixture()
  def graph_snapshot(tmp_path: Path) -> Path:
      snapshots = tmp_path / "graph" / "snapshots"
      snapshots.mkdir(parents=True)
      g: nx.MultiDiGraph = nx.MultiDiGraph()
      g.add_node("material:lfp", entity_type="Material", canonical_name="LFP")
      g.add_node("mechanism:sei", entity_type="FailureMechanism", canonical_name="SEI")
      g.add_edge("mechanism:sei", "material:lfp", key="rel-001", relation_type="AFFECTS", weight=1.0)
      snapshot = snapshots / "latest.graphml"
      nx.write_graphml(g, str(snapshot))
      return tmp_path


  @pytest.fixture()
  def norm_yaml(tmp_path: Path) -> Path:
      config = tmp_path / "config"
      config.mkdir()
      (config / "entity-normalization.yaml").write_text(
          "materials:\n"
          "  LFP:\n"
          "    entity_id: 'material:lfp'\n"
          "    aliases:\n"
          "      - LiFePO4\n"
          "      - lithium iron phosphate\n"
      )
      return tmp_path


  async def test_get_entity_returns_node_data(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_entity("material:lfp")
      assert result is not None
      assert result["entity_id"] == "material:lfp"
      assert result["canonical_name"] == "LFP"
      get_settings.cache_clear()


  async def test_get_entity_returns_none_for_missing(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_entity("material:no-such")
      assert result is None
      get_settings.cache_clear()


  async def test_list_entities_returns_all(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await list_entities()
      ids = [e["entity_id"] for e in result]
      assert "material:lfp" in ids
      assert "mechanism:sei" in ids
      get_settings.cache_clear()


  async def test_list_entities_filtered_by_type(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await list_entities("Material")
      assert all(e["entity_type"] == "Material" for e in result)
      get_settings.cache_clear()


  async def test_get_neighbors_returns_adjacent(graph_snapshot: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(graph_snapshot))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_neighbors("mechanism:sei")
      assert "material:lfp" in result
      get_settings.cache_clear()


  async def test_get_canonical_resolves_alias(norm_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(norm_yaml))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_canonical("LiFePO4")
      assert result == "material:lfp"
      get_settings.cache_clear()


  async def test_get_canonical_returns_none_for_unknown(norm_yaml: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(norm_yaml))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      result = await get_canonical("no-such-alias")
      assert result is None
      get_settings.cache_clear()
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run: `uv run pytest tests/mcp/test_graph_io.py -v`
  Expected: ImportError (module doesn't exist yet).

- [ ] **Step 3: Implement graph_io.py**

  Create `src/llm_rag/mcp/graph_io.py`:

  ```python
  from __future__ import annotations

  from pathlib import Path
  from typing import Any

  import networkx as nx
  import yaml
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
  async def get_entity(entity_id: str) -> dict | None:
      """Return node attributes for entity_id, or None if not in the graph."""
      g = _load_graph()
      if not g.has_node(entity_id):
          return None
      attrs: dict[str, Any] = dict(g.nodes[entity_id])
      attrs["entity_id"] = entity_id
      return attrs


  @app.tool()
  async def list_entities(entity_type: str = "") -> list[dict]:
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


  @app.tool()
  async def merge_extraction(export_path: str) -> None:
      """Load an ExtractionResult JSON and merge its entities/relations into the live graph."""
      from llm_rag.schemas.entities import ExtractionResult
      from llm_rag.graph.store import GraphStore
      settings = get_settings()
      snapshot = settings.graph_dir / "snapshots" / "latest.graphml"
      result = ExtractionResult.model_validate_json(Path(export_path).read_text())
      store = GraphStore(snapshot)
      store.load()
      for entity in result.entities:
          store.add_entity(entity)
      for relation in result.relations:
          store.add_relation(relation)
      store.save()


  @app.tool()
  async def get_neighbors(entity_id: str, depth: int = 1) -> list[str]:
      """Return entity IDs reachable from entity_id within depth hops (out-edges only)."""
      g = _load_graph()
      if not g.has_node(entity_id):
          return []
      if depth <= 1:
          return list(g.neighbors(entity_id))
      visited: set[str] = {entity_id}
      frontier: set[str] = {entity_id}
      for _ in range(depth):
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
      settings = get_settings()
      norm_path = settings.config_dir / "entity-normalization.yaml"
      if not norm_path.exists():
          return None
      data = yaml.safe_load(norm_path.read_text())
      for _section in data.values():
          if not isinstance(_section, dict):
              continue
          for _entry in _section.values():
              if not isinstance(_entry, dict):
                  continue
              if alias in _entry.get("aliases", []):
                  return str(_entry["entity_id"])
      return None


  def main() -> None:
      app.run()
  ```

- [ ] **Step 4: Run tests to verify they pass**

  Run: `uv run pytest tests/mcp/test_graph_io.py -v`
  Expected: all 7 tests PASS.

- [ ] **Step 5: Verify entrypoint starts**

  Run: `timeout 2 uv run llm-rag-graph-io || true`
  Expected: no ImportError.

- [ ] **Step 6: Commit**

  ```bash
  git add src/llm_rag/mcp/graph_io.py tests/mcp/test_graph_io.py
  git commit -m "feat: add graph-io MCP server with entity/relation/normalization tools"
  ```

---

## Task 6: MCPPool

**Files:**
- Create: `src/llm_rag/mcp/pool.py`

> **Note:** MCPPool manages `MCPServerStdio` instances from the claude-agent-sdk. The exact import path and API for `MCPServerStdio` must be confirmed from SDK docs before implementing. Common patterns: `from anthropic.mcp import MCPServerStdio` or `from claude_agent import MCPServerStdio`. The structure below is correct regardless of the import path.

- [ ] **Step 1: Confirm MCPServerStdio import path**

  In a Python REPL after `uv sync`:
  ```python
  # Try one of these — use whichever works:
  from anthropic.mcp import MCPServerStdio
  # or
  from claude_agent import MCPServerStdio
  ```

  Check SDK docs/changelog if neither works.

- [ ] **Step 2: Implement pool.py**

  Create `src/llm_rag/mcp/pool.py` (replace `YOUR_IMPORT` with the confirmed import):

  ```python
  from __future__ import annotations

  import asyncio
  from dataclasses import dataclass, field
  from typing import Any

  # Replace with confirmed import — e.g.:
  # from anthropic.mcp import MCPServerStdio
  # from claude_agent import MCPServerStdio
  from YOUR_MODULE import MCPServerStdio  # type: ignore[import]


  @dataclass
  class MCPServerConfig:
      name: str
      command: list[str]


  DEFAULT_SERVERS: list[MCPServerConfig] = [
      MCPServerConfig("corpus-io", ["python", "-m", "llm_rag.mcp.corpus_io"]),
      MCPServerConfig("wiki-io", ["python", "-m", "llm_rag.mcp.wiki_io"]),
      MCPServerConfig("graph-io", ["python", "-m", "llm_rag.mcp.graph_io"]),
  ]


  class MCPPool:
      """Async context manager that owns long-lived MCP server connections."""

      def __init__(self, servers: list[MCPServerConfig] | None = None) -> None:
          self._configs: dict[str, MCPServerConfig] = {
              s.name: s for s in (servers or DEFAULT_SERVERS)
          }
          self._connections: dict[str, MCPServerStdio] = {}

      async def __aenter__(self) -> MCPPool:
          for config in self._configs.values():
              conn = MCPServerStdio(command=config.command)
              await conn.__aenter__()
              self._connections[config.name] = conn
          return self

      async def __aexit__(self, *_: Any) -> None:
          for conn in self._connections.values():
              try:
                  await conn.__aexit__(None, None, None)
              except Exception:
                  pass
          self._connections.clear()

      def get(self, name: str) -> MCPServerStdio:
          """Return the live connection for name. Raises KeyError if not registered."""
          if name not in self._connections:
              raise KeyError(f"MCP server '{name}' not in pool. Available: {list(self._configs)}")
          return self._connections[name]
  ```

  > **Restart policy note:** Full crash-detection and restart is omitted in SP1 — if a server crashes, the next tool call will raise an exception that propagates to the caller. SP3 (supervisor) can add restart logic when the long-lived loop is wired up, since that is when crash recovery becomes important.

- [ ] **Step 3: Verify import**

  Run: `uv run python -c "from llm_rag.mcp.pool import MCPPool, MCPServerConfig; print('ok')"`
  Expected: `ok`

- [ ] **Step 4: Commit**

  ```bash
  git add src/llm_rag/mcp/pool.py
  git commit -m "feat: add MCPPool long-lived process manager"
  ```

---

## Task 7: AgentDefinition and run_agent()

**Files:**
- Create: `src/llm_rag/agent_runner.py`
- Create: `tests/test_agent_runner.py`

> **Note:** The exact `Agent` class import and constructor signature must be confirmed from the claude-agent-sdk docs before implementing. Common patterns: `from claude_agent import Agent` or `from anthropic.agent import Agent`. The agent is constructed with `model`, `system_prompt`, and `mcp_servers` kwargs.

- [ ] **Step 1: Write the failing tests**

  Create `tests/test_agent_runner.py`:

  ```python
  from __future__ import annotations

  import os
  from pathlib import Path

  import pytest

  from llm_rag.agent_runner import AgentDefinition


  def test_agent_definition_defaults() -> None:
      defn = AgentDefinition(
          name="extraction",
          model="claude-haiku-4-5-20251001",
          mcp_servers=["corpus-io"],
      )
      assert defn.max_tokens == 8192
      assert defn.name == "extraction"


  def test_agent_definition_prompt_path_derived(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()
      defn = AgentDefinition(
          name="extraction",
          model="claude-haiku-4-5-20251001",
          mcp_servers=["corpus-io"],
      )
      settings = get_settings()
      expected = settings.agents_dir / "prompts" / "extraction.md"
      assert defn.prompt_path(settings) == expected
      get_settings.cache_clear()


  @pytest.mark.skipif(not os.getenv("ANTHROPIC_API_KEY"), reason="requires ANTHROPIC_API_KEY")
  async def test_run_agent_smoke(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
      """Smoke test: runner constructs agent, calls it, returns non-empty string."""
      monkeypatch.setenv("ROOT_DIR", str(tmp_path))
      from llm_rag.config import get_settings
      get_settings.cache_clear()

      # Write a minimal prompt
      prompts_dir = tmp_path / "agents" / "prompts"
      prompts_dir.mkdir(parents=True)
      (prompts_dir / "smoke.md").write_text("You are a helpful assistant. Answer in one word.")

      from llm_rag.agent_runner import AgentDefinition, run_agent
      from llm_rag.mcp.pool import MCPPool

      defn = AgentDefinition(name="smoke", model="claude-haiku-4-5-20251001", mcp_servers=[])
      settings = get_settings()

      async with MCPPool(servers=[]) as pool:
          result = await run_agent(defn, "Say hello.", settings, pool)

      assert isinstance(result, str)
      assert len(result) > 0
      get_settings.cache_clear()
  ```

- [ ] **Step 2: Run tests to verify they fail**

  Run: `uv run pytest tests/test_agent_runner.py -v -k "not smoke"`
  Expected: ImportError (module doesn't exist yet).

- [ ] **Step 3: Confirm Agent import path from SDK docs**

  In a Python REPL:
  ```python
  # Try one of these:
  from claude_agent import Agent
  # or
  from anthropic.agent import Agent
  ```

- [ ] **Step 4: Implement agent_runner.py**

  Create `src/llm_rag/agent_runner.py` (replace `YOUR_MODULE` with confirmed import):

  ```python
  from __future__ import annotations

  from dataclasses import dataclass
  from pathlib import Path

  # Replace with confirmed import — e.g.:
  # from claude_agent import Agent
  # from anthropic.agent import Agent
  from YOUR_MODULE import Agent  # type: ignore[import]

  from llm_rag.config import Settings
  from llm_rag.mcp.pool import MCPPool


  @dataclass
  class AgentDefinition:
      name: str
      model: str
      mcp_servers: list[str]
      max_tokens: int = 8192

      def prompt_path(self, settings: Settings) -> Path:
          return settings.agents_dir / "prompts" / f"{self.name}.md"


  async def run_agent(
      definition: AgentDefinition,
      user_message: str,
      settings: Settings,
      mcp_pool: MCPPool,
  ) -> str:
      """
      Load system prompt, construct SDK Agent with MCP connections from pool,
      run with user_message, return final text response.
      """
      prompt_path = definition.prompt_path(settings)
      system_prompt = prompt_path.read_text()

      connections = [mcp_pool.get(name) for name in definition.mcp_servers]

      agent = Agent(
          model=definition.model,
          system_prompt=system_prompt,
          mcp_servers=connections,
          max_tokens=definition.max_tokens,
      )

      result = await agent.run(user_message)
      return str(result)
  ```

  > **API note:** The exact `Agent` constructor kwargs and `agent.run()` return type depend on the SDK version. Common variations: `system_prompt` may be called `system`; `run()` may return a string directly or an object with a `.text` attribute. Adjust to match the SDK's actual API.

- [ ] **Step 5: Run unit tests (no API key required)**

  Run: `uv run pytest tests/test_agent_runner.py -v -k "not smoke"`
  Expected: 2 tests PASS.

- [ ] **Step 6: Run smoke test if API key is set**

  Run: `uv run pytest tests/test_agent_runner.py -v -k smoke`
  Expected: PASS if `ANTHROPIC_API_KEY` is set; SKIP otherwise.

- [ ] **Step 7: Commit**

  ```bash
  git add src/llm_rag/agent_runner.py tests/test_agent_runner.py
  git commit -m "feat: add AgentDefinition and run_agent() shared subagent runner"
  ```

---

## Task 8: Delete agents/tools/ and final verification

**Files:**
- Delete: `agents/tools/` (empty directory)

- [ ] **Step 1: Remove empty directory**

  Run: `rm -rf agents/tools/`

- [ ] **Step 2: Run full MCP test suite**

  Run: `uv run pytest tests/mcp/ tests/test_agent_runner.py -v -k "not smoke"`
  Expected: all tests PASS (20+ tests).

- [ ] **Step 3: Run mypy**

  Run: `uv run mypy src/`
  Expected: no new errors. (Ignore any pre-existing errors on pipeline/ or supervisor/ from prior plans.)

- [ ] **Step 4: Run ruff**

  Run: `uv run ruff check src/ tests/`
  Expected: no errors. Fix any with `uv run ruff check src/ tests/ --fix`.

- [ ] **Step 5: Verify all three entrypoints start**

  Run:
  ```bash
  timeout 2 uv run llm-rag-corpus-io || true
  timeout 2 uv run llm-rag-wiki-io || true
  timeout 2 uv run llm-rag-graph-io || true
  ```
  Expected: each prints MCP startup output or times out cleanly — no ImportError.

- [ ] **Step 6: Final commit**

  ```bash
  git add -A
  git commit -m "chore: remove empty agents/tools/ directory, SP1 complete"
  ```

---

## Success Criteria Checklist

- [ ] All 18+ MCP tool tests pass with no subprocess or API calls
- [ ] `llm-rag-corpus-io`, `llm-rag-wiki-io`, `llm-rag-graph-io` all start without error
- [ ] `uv run mypy src/` — no new errors introduced by SP1 files
- [ ] `AgentDefinition` unit tests pass
- [ ] Smoke test passes (or is skipped cleanly when API key absent)
- [ ] `agents/tools/` directory is gone
