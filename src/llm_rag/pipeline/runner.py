from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ValidationError

from llm_rag.agent_runner import AgentDefinition, run_agent
from llm_rag.config import Settings, get_settings
from llm_rag.mcp.pool import MCPPool
from llm_rag.pipeline.contracts import (
    ExtractedEntity,
    ExtractedRelation,
    GraphPatch,
    SourceDocument,
    WikiPageDraft,
)
from llm_rag.pipeline.manifest import (
    create_manifest,
    load_manifest,
    mark_stage_failed,
    needs_processing,
    save_manifest,
)
from llm_rag.schemas.provenance import DocType, DocumentManifest, ProcessingStage
from llm_rag.utils.retry import is_transient

logger = logging.getLogger(__name__)


class StageOutputValidationError(Exception):
    """Raised when a pipeline stage produces output that fails contract validation."""

    def __init__(self, stage: ProcessingStage, details: str) -> None:
        self.stage = stage
        self.details = details
        super().__init__(f"Stage {stage.value} output validation failed: {details}")


# Maps each processing stage to the contract model(s) expected in its output.
# A stage may produce a single object or a list; the value is the model class.
_STAGE_CONTRACTS: dict[ProcessingStage, type[BaseModel] | list[type[BaseModel]]] = {
    ProcessingStage.INGESTED: SourceDocument,
    ProcessingStage.EXTRACTED: [ExtractedEntity, ExtractedRelation],
    ProcessingStage.NORMALIZED: [ExtractedEntity],
    ProcessingStage.WIKI_COMPILED: WikiPageDraft,
    ProcessingStage.GRAPH_UPDATED: GraphPatch,
}

_DOC_TYPE_BY_PARENT: dict[str, DocType] = {
    "paper": DocType.PAPER,
    "papers": DocType.PAPER,
    "report": DocType.REPORT,
    "reports": DocType.REPORT,
    "meeting": DocType.MEETING,
    "meetings": DocType.MEETING,
    "sop": DocType.SOP,
    "sops": DocType.SOP,
}


def _extract_json(text: str) -> str | None:
    """Extract JSON from agent output, handling optional markdown fences."""
    stripped = text.strip()

    # Try stripping markdown code fences (```json ... ``` or ``` ... ```)
    if stripped.startswith("```"):
        lines = stripped.split("\n")
        # Remove first line (```json or ```) and last line (```)
        if lines[-1].strip() == "```":
            inner = "\n".join(lines[1:-1]).strip()
            if inner:
                return inner

    # Try as raw JSON
    if stripped.startswith(("{", "[")):
        return stripped

    return None


def _matches_any_model(data: dict[str, Any], models: list[type[BaseModel]]) -> bool:
    """Return True if data validates against any of the given models."""
    for model in models:
        try:
            model.model_validate(data)
            return True
        except ValidationError:
            continue
    return False


class DeadLetterError(Exception):
    """Raised when a stage exhausts all retries and is dead-lettered."""

    def __init__(self, stage: ProcessingStage, attempts: int, last_error: str) -> None:
        self.stage = stage
        self.attempts = attempts
        self.last_error = last_error
        super().__init__(
            f"Stage {stage.value} dead-lettered after {attempts} attempts: {last_error}"
        )


class PipelineRunner:
    MAX_STAGE_ATTEMPTS = 3
    RETRY_BASE_DELAY = 2.0

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings: Settings = settings or get_settings()
        self._pool: MCPPool | None = None
        self._ingestion = AgentDefinition(
            name="ingestion",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io"],
            max_tokens=4096,
        )
        self._extraction = AgentDefinition(
            name="extraction-paper",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io"],
            max_tokens=8192,
        )
        self._normalization = AgentDefinition(
            name="normalization",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io", "graph-io"],
            max_tokens=8192,
        )
        self._wiki_compiler = AgentDefinition(
            name="wiki_compiler",
            model=self.settings.model_wiki_compilation,
            mcp_servers=["corpus-io", "wiki-io"],
            max_tokens=8192,
        )
        self._graph_curator = AgentDefinition(
            name="graph_curator",
            model=self.settings.model_bulk_extraction,
            mcp_servers=["corpus-io", "graph-io"],
            max_tokens=4096,
        )

    async def __aenter__(self) -> PipelineRunner:
        self._pool = MCPPool()
        await self._pool.__aenter__()
        return self

    async def __aexit__(self, *args: Any) -> None:
        if self._pool is not None:
            await self._pool.__aexit__(*args)
            self._pool = None

    async def run(self, source_path: Path, force: bool = False) -> DocumentManifest:
        assert self._pool is not None, "Use PipelineRunner as async context manager"
        manifest = load_manifest(source_path) or create_manifest(
            source_path,
            doc_id=self._derive_doc_id(source_path),
            doc_type=self._infer_doc_type(source_path),
            source_connector="manual",
        )
        doc_id = manifest.doc_id
        extraction_agent = self._select_extraction_agent(manifest.doc_type)

        stages = [
            (ProcessingStage.INGESTED, self._ingestion,
             f"Ingest doc_id={doc_id}, source_path={source_path},"
             f" doc_type={manifest.doc_type},"
             f" source_connector={manifest.source_connector}"),
            (ProcessingStage.EXTRACTED, extraction_agent,
             f"Extract entities and relations from doc_id={doc_id}"),
            (ProcessingStage.NORMALIZED, self._normalization,
             f"Normalize entities in doc_id={doc_id}"),
            (ProcessingStage.WIKI_COMPILED, self._wiki_compiler,
             f"Compile wiki pages for doc_id={doc_id}"),
            (ProcessingStage.GRAPH_UPDATED, self._graph_curator,
             f"Update knowledge graph for doc_id={doc_id}"),
        ]

        for stage, agent_def, prompt in stages:
            if not (force or needs_processing(source_path, stage)):
                continue

            manifest = await self._run_stage_with_retry(
                stage, agent_def, prompt, source_path, manifest
            )

        return manifest

    def _select_extraction_agent(self, doc_type: DocType) -> AgentDefinition:
        prompt_name = {
            DocType.PAPER: "extraction-paper",
            DocType.SOP: "extraction-sop",
            DocType.MEETING: "extraction-meeting",
            DocType.REPORT: "extraction-report",
            DocType.UNKNOWN: "extraction-paper",
        }[doc_type]
        return AgentDefinition(
            name=prompt_name,
            model=self._extraction.model,
            mcp_servers=list(self._extraction.mcp_servers),
            max_tokens=self._extraction.max_tokens,
        )

    async def _run_stage_with_retry(
        self,
        stage: ProcessingStage,
        agent_def: AgentDefinition,
        prompt: str,
        source_path: Path,
        manifest: DocumentManifest,
    ) -> DocumentManifest:
        """Run a single pipeline stage with retry and dead-letter handling.

        Retries transient failures up to MAX_STAGE_ATTEMPTS times with exponential
        backoff. Non-transient failures (including validation errors) fail immediately.
        After exhausting retries, the stage is marked as dead-lettered in the manifest.
        """
        import asyncio

        last_exc: Exception | None = None

        for attempt in range(1, self.MAX_STAGE_ATTEMPTS + 1):
            try:
                output = await run_agent(agent_def, prompt, self.settings, self._pool)
                self._validate_stage_output(stage, output)

                # Success — reload manifest (agent may have updated it via MCP)
                _reloaded = load_manifest(source_path)
                return _reloaded if _reloaded is not None else manifest

            except StageOutputValidationError as exc:
                # Validation errors are not transient — fail immediately
                manifest = manifest.model_copy(
                    update={"error": f"Stage {stage.value} validation failed: {exc.details}"}
                )
                save_manifest(manifest)
                raise

            except Exception as exc:
                last_exc = exc
                if not is_transient(exc):
                    # Non-transient error — dead-letter immediately
                    manifest = mark_stage_failed(
                        manifest, stage, attempt, str(exc)
                    )
                    save_manifest(manifest)
                    raise DeadLetterError(stage, attempt, str(exc)) from exc

                if attempt == self.MAX_STAGE_ATTEMPTS:
                    break

                delay = min(
                    self.RETRY_BASE_DELAY * (2 ** (attempt - 1)),
                    60.0,
                )
                logger.warning(
                    "Stage %s attempt %d/%d failed (%s), retrying in %.1fs",
                    stage.value,
                    attempt,
                    self.MAX_STAGE_ATTEMPTS,
                    exc,
                    delay,
                )
                await asyncio.sleep(delay)

        # All retries exhausted — dead-letter
        error_msg = str(last_exc) if last_exc else "Unknown error"
        manifest = mark_stage_failed(
            manifest, stage, self.MAX_STAGE_ATTEMPTS, error_msg
        )
        save_manifest(manifest)
        raise DeadLetterError(stage, self.MAX_STAGE_ATTEMPTS, error_msg) from last_exc

    @staticmethod
    def _validate_stage_output(stage: ProcessingStage, output: str) -> None:
        """Validate that agent output conforms to the expected contract model(s).

        Attempts to parse the output as JSON and validate against the contract
        model for the given stage. Raises StageOutputValidationError on failure.
        """
        if not output or not output.strip():
            raise StageOutputValidationError(stage, "Agent produced empty output")

        contract = _STAGE_CONTRACTS.get(stage)
        if contract is None:
            return  # No contract defined for this stage — skip validation

        # Try to extract JSON from the output (agent may wrap it in markdown fences)
        json_str = _extract_json(output)
        if json_str is None:
            raise StageOutputValidationError(
                stage, "Agent output does not contain valid JSON"
            )

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as exc:
            raise StageOutputValidationError(
                stage, f"Invalid JSON in agent output: {exc}"
            ) from exc

        # Determine which models to try; a list means any of them is acceptable
        models = contract if isinstance(contract, list) else [contract]

        if isinstance(data, list):
            # Validate each item against any of the accepted models
            for i, item in enumerate(data):
                if not _matches_any_model(item, models):
                    raise StageOutputValidationError(
                        stage,
                        f"Item {i} does not conform to any expected contract: "
                        f"{[m.__name__ for m in models]}",
                    )
        else:
            if not _matches_any_model(data, models):
                raise StageOutputValidationError(
                    stage,
                    f"Output does not conform to any expected contract: "
                    f"{[m.__name__ for m in models]}",
                )

    def _derive_doc_id(self, source_path: Path) -> str:
        try:
            rel = source_path.relative_to(self.settings.raw_dir)
            return str(rel.with_suffix(""))
        except ValueError:
            return source_path.stem

    def _infer_doc_type(self, source_path: Path) -> DocType:
        parent = source_path.parent.name
        return _DOC_TYPE_BY_PARENT.get(parent.lower(), DocType.UNKNOWN)
