from __future__ import annotations

import logging
import re
from typing import Any

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ValidationError

from llm_rag.agent_runner import ToolResultContractError
from llm_rag.config import get_settings

logger = logging.getLogger(__name__)

app = FastMCP("wiki-io")

# Section name convention: lowercase, hyphen-separated
_SECTION_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$")


class ProvenanceEntry(BaseModel):
    """A single provenance record for rendering into wiki pages."""

    source_doc_id: str = Field(min_length=1)
    chunk_id: str = Field(default="")
    confidence: float = Field(ge=0.0, le=1.0)
    extracted_at: str = Field(min_length=1)


class WikiSectionsInput(BaseModel):
    """Validates the sections dict passed to write_auto_sections."""

    sections: dict[str, str] = Field(min_length=1)


class WikiCreatePageInput(BaseModel):
    """Validates inputs to create_page."""

    relative_path: str = Field(min_length=1)
    page_type: str = Field(min_length=1)
    substitutions: dict[str, str] = Field(default_factory=dict)


def _validate_section_names(sections: dict[str, Any]) -> None:
    """Raise ToolResultContractError if any section name violates naming convention."""
    for name in sections:
        if not _SECTION_NAME_RE.match(name):
            raise ToolResultContractError(
                tool_name="write_auto_sections",
                expected_schema="WikiSectionsInput",
                details=(
                    f"Section name {name!r} violates naming convention: "
                    "must be lowercase, hyphen-separated (e.g. 'open-questions')"
                ),
                raw_result=name,
            )


@app.tool()
async def read_page(relative_path: str) -> str:
    """Return raw markdown of a wiki page. Raises FileNotFoundError if missing."""
    settings = get_settings()
    path = settings.wiki_dir / relative_path
    if not path.exists():
        raise FileNotFoundError(f"Wiki page not found: {relative_path}")
    return path.read_text()


@app.tool()
async def write_auto_sections(relative_path: str, sections: dict[str, Any]) -> None:
    """Rewrite auto-fenced sections in a wiki page. Human sections are preserved."""
    from llm_rag.wiki.writer import update_auto_sections

    if not relative_path or not relative_path.strip():
        raise ToolResultContractError(
            tool_name="write_auto_sections",
            expected_schema="WikiSectionsInput",
            details="relative_path must be a non-empty string",
        )

    if not sections:
        raise ToolResultContractError(
            tool_name="write_auto_sections",
            expected_schema="WikiSectionsInput",
            details="sections dict must not be empty",
        )

    _validate_section_names(sections)

    try:
        WikiSectionsInput(sections={k: str(v) for k, v in sections.items()})
    except ValidationError as exc:
        raise ToolResultContractError(
            tool_name="write_auto_sections",
            expected_schema="WikiSectionsInput",
            details=str(exc),
            raw_result=sections,
        ) from exc

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
    """Return the template for a wiki page type. Falls back to _fallback.md if missing."""
    settings = get_settings()
    template_path = settings.config_dir / "page-templates" / f"{page_type}.md"
    if not template_path.exists():
        fallback_path = settings.config_dir / "page-templates" / "_fallback.md"
        if not fallback_path.exists():
            raise FileNotFoundError(f"No template for page type: {page_type}")
        logger.warning(
            "No dedicated template for page type %r; using fallback template",
            page_type,
        )
        return fallback_path.read_text()
    return template_path.read_text()


@app.tool()
async def create_page(relative_path: str, page_type: str, substitutions: dict[str, Any]) -> None:
    """Instantiate a page template with substitutions and write it. No-op if page exists."""
    from llm_rag.wiki.writer import create_page as _create

    try:
        validated = WikiCreatePageInput(
            relative_path=relative_path,
            page_type=page_type,
            substitutions={k: str(v) for k, v in substitutions.items()},
        )
    except ValidationError as exc:
        raise ToolResultContractError(
            tool_name="create_page",
            expected_schema="WikiCreatePageInput",
            details=str(exc),
            raw_result={"relative_path": relative_path, "page_type": page_type},
        ) from exc

    settings = get_settings()
    template_path = settings.config_dir / "page-templates" / f"{validated.page_type}.md"
    if not template_path.exists():
        fallback_path = settings.config_dir / "page-templates" / "_fallback.md"
        if not fallback_path.exists():
            raise ToolResultContractError(
                tool_name="create_page",
                expected_schema="WikiCreatePageInput",
                details=f"Unknown page_type {page_type!r} and no fallback template available",
                raw_result=page_type,
            )
        logger.warning(
            "No dedicated template for page type %r; using fallback template",
            page_type,
        )
        template_path = fallback_path

    template = template_path.read_text()
    path = settings.wiki_dir / validated.relative_path
    _create(path, template, validated.substitutions)


def render_provenance(entries: list[ProvenanceEntry]) -> str:
    """Render a list of provenance entries as a markdown table."""
    if not entries:
        return "_No provenance records._"
    lines = [
        "| Source Document | Chunk | Confidence | Extracted |",
        "|----------------|-------|------------|-----------|",
    ]
    for e in entries:
        chunk_display = e.chunk_id if e.chunk_id else "—"
        lines.append(
            f"| {e.source_doc_id} | {chunk_display} | {e.confidence:.2f} | {e.extracted_at} |"
        )
    return "\n".join(lines)


@app.tool()
async def write_provenance(
    relative_path: str, provenance: list[dict[str, Any]]
) -> None:
    """Write provenance records into the auto-fenced provenance section of a wiki page.

    Each entry in provenance should have: source_doc_id, chunk_id, confidence, extracted_at.
    """
    if not relative_path or not relative_path.strip():
        raise ToolResultContractError(
            tool_name="write_provenance",
            expected_schema="ProvenanceEntry[]",
            details="relative_path must be a non-empty string",
        )

    try:
        entries = [ProvenanceEntry(**p) for p in provenance]
    except ValidationError as exc:
        raise ToolResultContractError(
            tool_name="write_provenance",
            expected_schema="ProvenanceEntry[]",
            details=str(exc),
            raw_result=provenance,
        ) from exc

    content = render_provenance(entries)
    await write_auto_sections(relative_path, {"provenance": content})


@app.tool()
async def materialize_page(
    entity_id: str,
    entity_type: str,
    canonical_name: str,
    relative_path: str,
    claims_json: str,
    evidence_json: str,
) -> str:
    """Build a wiki page deterministically from claims + evidence.

    Generates auto-sections from the provided ClaimCollection and EvidenceStore.
    Human-editable sections are preserved from the existing page on disk.
    Returns the full page markdown.
    """
    from llm_rag.evidence.models import EvidenceStore
    from llm_rag.knowledge.models import ClaimCollection
    from llm_rag.wiki.materializer import WikiMaterializer

    settings = get_settings()

    try:
        claims = ClaimCollection.model_validate_json(claims_json)
    except ValidationError as exc:
        raise ToolResultContractError(
            tool_name="materialize_page",
            expected_schema="ClaimCollection",
            details=str(exc),
            raw_result=claims_json[:200],
        ) from exc

    try:
        evidence = EvidenceStore.model_validate_json(evidence_json)
    except ValidationError as exc:
        raise ToolResultContractError(
            tool_name="materialize_page",
            expected_schema="EvidenceStore",
            details=str(exc),
            raw_result=evidence_json[:200],
        ) from exc

    materializer = WikiMaterializer(
        wiki_dir=settings.wiki_dir,
        template_dir=settings.config_dir / "page-templates",
    )
    return materializer.build_wiki_page(
        entity_id=entity_id,
        entity_type=entity_type,
        canonical_name=canonical_name,
        claims=claims,
        evidence=evidence,
        relative_path=relative_path,
    )


def main() -> None:
    app.run()
